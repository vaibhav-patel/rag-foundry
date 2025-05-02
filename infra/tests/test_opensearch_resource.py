import aws_cdk as cdk
from aws_cdk.assertions import Template

from rag_foundry_infra.stacks.rag_foundry_stack import RagFoundryStack


def test_opensearch_collection_in_template():
    app = cdk.App()
    stack = RagFoundryStack(
        app,
        "T",
        env=cdk.Environment(account="123456789012", region="us-east-1"),
    )
    t = Template.from_stack(stack)
    t.resource_count_is("AWS::OpenSearchServerless::Collection", 1)
