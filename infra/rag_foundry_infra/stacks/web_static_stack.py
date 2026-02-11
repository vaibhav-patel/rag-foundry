"""S3 + CloudFront for the admin SPA (placeholder index until `web` is built in CI)."""

from __future__ import annotations

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct


class WebStaticStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        site_bucket = s3.Bucket(
            self,
            "WebBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        bucket_origin = origins.S3BucketOrigin.with_origin_access_identity(site_bucket)

        dist = cloudfront.Distribution(
            self,
            "WebDistribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=bucket_origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
        )

        placeholder_html = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>rag-foundry</title></head><body><h1>rag-foundry</h1>"
            "<p>Deploy Vite build via CI to replace this placeholder.</p></body></html>"
        )
        s3deploy.BucketDeployment(
            self,
            "DeployWebPlaceholder",
            sources=[s3deploy.Source.data("index.html", placeholder_html)],
            destination_bucket=site_bucket,
            distribution=dist,
            distribution_paths=["/*"],
        )

        CfnOutput(self, "WebDistributionUrl", value=f"https://{dist.distribution_domain_name}")
        CfnOutput(self, "WebBucketName", value=site_bucket.bucket_name)
