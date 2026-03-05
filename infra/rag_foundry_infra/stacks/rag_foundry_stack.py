"""Core rag-foundry infrastructure: VPC, data stores, auth, HTTP API, ingest, OpenSearch."""

from __future__ import annotations

import json
import os
from pathlib import Path

from aws_cdk import (
    BundlingOptions,
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_authorizers as apigwv2_auth
from aws_cdk import aws_apigatewayv2_integrations as apigwv2_int
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_opensearchserverless as aoss
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sqs as sqs
from aws_cdk import aws_ssm as ssm
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from constructs import Construct

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _bundled_lambda_code(repo_root: Path, rel_lambda_dir: str) -> lambda_.Code:
    """Install requirements.txt alongside *.py into the Lambda asset (Docker bundling).

    Set ``RAG_FOUNDRY_SYNTH_SKIP_LAMBDA_BUNDLING=1`` to stage source only (e.g. infra unit tests
    without Docker). Production synth must leave this unset.
    """
    asset_path = repo_root / rel_lambda_dir
    path_str = str(asset_path)
    skip = os.environ.get("RAG_FOUNDRY_SYNTH_SKIP_LAMBDA_BUNDLING", "").lower() in (
        "1",
        "true",
        "yes",
    )
    if skip:
        return lambda_.Code.from_asset(path_str)
    return lambda_.Code.from_asset(
        path_str,
        bundling=BundlingOptions(
            image=lambda_.Runtime.PYTHON_3_12.bundling_image,
            command=[
                "bash",
                "-c",
                "pip install --no-cache-dir -r requirements.txt -t /asset-output "
                "&& cp -v ./*.py /asset-output/ "
                '&& for f in ./*.json; do [ -f "$f" ] && cp -v "$f" /asset-output/; done',
            ],
        ),
    )


class RagFoundryStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        data_key = kms.Key(
            self,
            "DataKey",
            description="rag-foundry application data encryption",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        raw_bucket = s3.Bucket(
            self,
            "RawDocs",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=data_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
        )
        artifacts_bucket = s3.Bucket(
            self,
            "Artifacts",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=data_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        table = dynamodb.Table(
            self,
            "Catalog",
            partition_key=dynamodb.Attribute(name="PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )
        table.add_global_secondary_index(
            index_name="GSI1",
            partition_key=dynamodb.Attribute(name="GSI1PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="GSI1SK", type=dynamodb.AttributeType.STRING),
        )

        dlq = sqs.Queue(self, "IngestDLQ", retention_period=Duration.days(14))
        ops_topic = sns.Topic(self, "OpsTopic", display_name="rag-foundry-ops")

        user_pool = cognito.UserPool(
            self,
            "UserPool",
            user_pool_name="rag-foundry-users",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            removal_policy=RemovalPolicy.RETAIN,
        )
        app_client = user_pool.add_client(
            "WebClient",
            auth_flows=cognito.AuthFlow(user_password=True, user_srp=True),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.PROFILE,
                ],
                callback_urls=["http://localhost:5173/callback"],
                logout_urls=["http://localhost:5173/"],
            ),
            supported_identity_providers=[cognito.UserPoolClientIdentityProvider.COGNITO],
        )

        api_logs = logs.LogGroup(
            self,
            "ControlPlaneLogs",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=RemovalPolicy.DESTROY,
        )
        api_lambda = lambda_.Function(
            self,
            "ControlPlaneFn",
            runtime=lambda_.Runtime.PYTHON_3_12,  # Lambda runtime (not local Python version)
            handler="handler.handler",
            code=_bundled_lambda_code(_REPO_ROOT, "services/control_plane/lambda"),
            timeout=Duration.seconds(29),
            memory_size=512,
            environment={
                "TABLE_NAME": table.table_name,
                "RAW_BUCKET": raw_bucket.bucket_name,
                "ARTIFACTS_BUCKET": artifacts_bucket.bucket_name,
                "BUILD_VERSION": "0.1.0",
            },
            log_group=api_logs,
        )
        table.grant_read_write_data(api_lambda)
        raw_bucket.grant_read_write(api_lambda)
        artifacts_bucket.grant_read_write(api_lambda)

        worker_logs = logs.LogGroup(
            self,
            "WorkerLogs",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=RemovalPolicy.DESTROY,
        )
        worker_lambda = lambda_.Function(
            self,
            "WorkerFn",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_bundled_lambda_code(_REPO_ROOT, "services/workers/lambda_stub"),
            timeout=Duration.minutes(5),
            memory_size=1024,
            environment={
                "RAW_BUCKET": raw_bucket.bucket_name,
                "TABLE_NAME": table.table_name,
            },
            log_group=worker_logs,
        )
        raw_bucket.grant_read_write(worker_lambda)
        table.grant_read_write_data(worker_lambda)

        validate = sfn.Pass(self, "ValidateInput")
        ingest = tasks.LambdaInvoke(
            self,
            "IngestWorker",
            lambda_function=worker_lambda,
            payload_response_only=True,
        )
        finalize = sfn.Pass(self, "Finalize")
        definition = validate.next(ingest).next(finalize)
        state_machine = sfn.StateMachine(
            self,
            "IngestPipeline",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.hours(2),
            tracing_enabled=True,
        )
        state_machine.grant_start_execution(api_lambda)
        api_lambda.add_environment("STATE_MACHINE_ARN", state_machine.state_machine_arn)

        collection_name = f"rf-{self.account}-{self.region}"[:28].replace("_", "")

        enc_policy = aoss.CfnSecurityPolicy(
            self,
            "EncryptionPolicy",
            name=f"{collection_name}-enc",
            type="encryption",
            policy=json.dumps(
                {
                    "Rules": [
                        {
                            "Resource": ["collection/*"],
                            "ResourceType": "collection",
                        }
                    ],
                    "AWSOwnedKey": True,
                },
                separators=(",", ":"),
            ),
        )
        net_policy = aoss.CfnSecurityPolicy(
            self,
            "NetworkPolicy",
            name=f"{collection_name}-net",
            type="network",
            policy=json.dumps(
                [
                    {
                        "Rules": [
                            {
                                "Resource": ["collection/*"],
                                "ResourceType": "collection",
                            }
                        ],
                        "AllowFromPublic": True,
                    }
                ],
                separators=(",", ":"),
            ),
        )
        collection = aoss.CfnCollection(
            self,
            "VectorCollection",
            name=collection_name,
            type="VECTORSEARCH",
        )
        collection.add_dependency(enc_policy)
        collection.add_dependency(net_policy)

        index_data_perms = [
            "aoss:CreateIndex",
            "aoss:DeleteIndex",
            "aoss:UpdateIndex",
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
            "aoss:WriteDocument",
        ]
        collection_meta_perms = [
            "aoss:DescribeCollectionItems",
        ]
        data_policy_doc = [
            {
                "Rules": [
                    {
                        "ResourceType": "index",
                        "Resource": [f"index/{collection_name}/*"],
                        "Permission": index_data_perms,
                    },
                    {
                        "ResourceType": "collection",
                        "Resource": [f"collection/{collection_name}"],
                        "Permission": collection_meta_perms,
                    },
                ],
                "Principal": [
                    api_lambda.role.role_arn,
                    worker_lambda.role.role_arn,
                ],
            }
        ]
        data_policy_name = f"{collection_name}-data"
        data_policy = aoss.CfnAccessPolicy(
            self,
            "DataAccessPolicy",
            name=data_policy_name,
            type="data",
            policy=json.dumps(data_policy_doc, separators=(",", ":")),
        )
        data_policy.add_dependency(collection)

        index_name_default = "rag-foundry-chunks"
        api_lambda.add_environment("OPENSEARCH_COLLECTION_NAME", collection_name)
        worker_lambda.add_environment("OPENSEARCH_COLLECTION_NAME", collection_name)
        api_lambda.add_environment("OPENSEARCH_INDEX_NAME", index_name_default)
        worker_lambda.add_environment("OPENSEARCH_INDEX_NAME", index_name_default)
        collection_endpoint = collection.attr_collection_endpoint
        api_lambda.add_environment("OPENSEARCH_ENDPOINT", collection_endpoint)
        worker_lambda.add_environment("OPENSEARCH_ENDPOINT", collection_endpoint)

        # OpenSearch Serverless: identity HTTP data-plane policy for this collection + indices.
        account = self.account
        region = self.region
        aoss_collection_arn = f"arn:aws:aoss:{region}:{account}:collection/{collection_name}"
        aoss_index_arn = f"arn:aws:aoss:{region}:{account}:index/{collection_name}/*"
        aoss_data_actions = [
            "aoss:ReadDocument",
            "aoss:WriteDocument",
            "aoss:CreateIndex",
            "aoss:UpdateIndex",
            "aoss:DeleteIndex",
            "aoss:DescribeIndex",
            "aoss:DescribeCollectionItems",
        ]
        for fn in (api_lambda, worker_lambda):
            fn.add_to_role_policy(
                iam.PolicyStatement(
                    actions=aoss_data_actions,
                    resources=[aoss_collection_arn, aoss_index_arn],
                )
            )
        worker_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v1",
                    f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v2:0",
                ],
            )
        )

        jwt_authorizer = apigwv2_auth.HttpJwtAuthorizer(
            "JwtAuthorizer",
            jwt_audience=[app_client.user_pool_client_id],
            jwt_issuer=f"https://cognito-idp.{self.region}.amazonaws.com/{user_pool.user_pool_id}",
        )

        integration = apigwv2_int.HttpLambdaIntegration("ApiIntegration", api_lambda)
        http_api = apigwv2.HttpApi(
            self,
            "HttpApi",
            api_name="rag-foundry-control-plane",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=["http://localhost:5173"],
                allow_methods=[apigwv2.CorsHttpMethod.ANY],
                allow_headers=["authorization", "content-type"],
                max_age=Duration.days(1),
            ),
        )
        http_api.add_routes(
            path="/v1/health",
            methods=[apigwv2.HttpMethod.GET],
            integration=integration,
        )
        http_api.add_routes(
            path="/v1/{proxy+}",
            methods=[apigwv2.HttpMethod.ANY],
            integration=integration,
            authorizer=jwt_authorizer,
        )

        ssm.StringParameter(
            self,
            "ParamApiUrl",
            parameter_name="/rag-foundry/control-plane/http-api-url",
            string_value=http_api.api_endpoint,
        )

        CfnOutput(self, "HttpApiUrl", value=http_api.api_endpoint)
        CfnOutput(self, "UserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=app_client.user_pool_client_id)
        CfnOutput(self, "CollectionName", value=collection_name)
        CfnOutput(self, "CollectionEndpoint", value=collection_endpoint)
        CfnOutput(self, "OpensearchChunkIndexName", value=index_name_default)
        CfnOutput(self, "AossDataAccessPolicyName", value=data_policy_name)
        CfnOutput(self, "AossIndexResourcePattern", value=f"index/{collection_name}/*")

        # DLQ alarm stub (metric on state machine or SQS - simple queue depth)
        from aws_cdk import aws_cloudwatch as cw
        from aws_cdk import aws_cloudwatch_actions as cw_actions

        alarm = cw.Alarm(
            self,
            "DlqAlarm",
            metric=dlq.metric_approximate_number_of_messages_visible(),
            threshold=1,
            evaluation_periods=1,
            alarm_description="Ingest DLQ has messages",
        )
        alarm.add_alarm_action(cw_actions.SnsAction(ops_topic))

        dashboard = cw.Dashboard(
            self,
            "RagFoundryDashboard",
            dashboard_name="rag-foundry-dev",
        )
        dashboard.add_widgets(
            cw.TextWidget(
                markdown="# rag-foundry\nControl plane and worker Lambda invocations / errors.",
            ),
            cw.GraphWidget(
                title="Lambda invocations",
                left=[
                    api_lambda.metric_invocations(),
                    worker_lambda.metric_invocations(),
                ],
                width=12,
            ),
            cw.GraphWidget(
                title="Lambda errors",
                left=[
                    api_lambda.metric_errors(),
                    worker_lambda.metric_errors(),
                ],
                width=12,
            ),
        )
