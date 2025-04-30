import aws_cdk as cdk
from aws_cdk.assertions import Template

from rag_foundry_infra.stacks.rag_foundry_stack import RagFoundryStack


def test_stack_synth():
    app = cdk.App()
    stack = RagFoundryStack(
        app,
        "TestStack",
        env=cdk.Environment(account="123456789012", region="us-east-1"),
    )
    Template.from_stack(stack)
