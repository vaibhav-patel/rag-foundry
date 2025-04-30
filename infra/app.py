#!/usr/bin/env python3
import os

import aws_cdk as cdk

from rag_foundry_infra.stacks.rag_foundry_stack import RagFoundryStack


app = cdk.App()

account = os.environ.get("CDK_DEFAULT_ACCOUNT")
region = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
env = cdk.Environment(account=account, region=region)

RagFoundryStack(app, "RagFoundryStack", env=env)

app.synth()
