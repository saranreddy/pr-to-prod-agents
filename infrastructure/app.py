"""CDK app entry point."""

import aws_cdk as cdk

from cdk_stack import PrToProdAgentStack

app = cdk.App()

PrToProdAgentStack(
    app,
    "PrToProdAgentStack",
    env=cdk.Environment(
        account=app.node.try_get_context("account"),
        region=app.node.try_get_context("region") or "us-east-1",
    ),
    description="Infrastructure for PR-to-Production Agent Team",
)

app.synth()
