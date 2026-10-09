import * as cdk from "aws-cdk-lib";
import { AquaAgentStack } from "./stack";
const app = new cdk.App();
new AquaAgentStack(app, "AquaAgent", {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region:
      app.node.tryGetContext("region") ||
      process.env.CDK_DEFAULT_REGION ||
      "ap-south-1",
  },
});
