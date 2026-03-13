import aws_cdk as cdk
from aws_cdk.assertions import Template

from rag_foundry_infra.stacks.rag_foundry_stack import RagFoundryStack


def test_rerank_lambda_arn_ssm_parameter_exists():
    app = cdk.App()
    stack = RagFoundryStack(
        app,
        "T",
        env=cdk.Environment(account="123456789012", region="us-east-1"),
    )
    t = Template.from_stack(stack)
    names = [
        r["Properties"]["Name"]
        for r in t.find_resources("AWS::SSM::Parameter").values()
        if "Properties" in r and "Name" in r["Properties"]
    ]
    assert "/rag-foundry/control-plane/rerank-lambda-arn" in names
