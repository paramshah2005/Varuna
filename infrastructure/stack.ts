import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as apigw from "aws-cdk-lib/aws-apigatewayv2";
import {
  HttpLambdaIntegration,
  WebSocketLambdaIntegration,
} from "aws-cdk-lib/aws-apigatewayv2-integrations";
import {
  HttpJwtAuthorizer,
  WebSocketLambdaAuthorizer,
} from "aws-cdk-lib/aws-apigatewayv2-authorizers";
import * as sfn from "aws-cdk-lib/aws-stepfunctions";
import * as tasks from "aws-cdk-lib/aws-stepfunctions-tasks";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import * as secrets from "aws-cdk-lib/aws-secretsmanager";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import * as amplify from "aws-cdk-lib/aws-amplify";
import * as path from "node:path";

export class AquaAgentStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);
    const table = new dynamodb.Table(this, "State", {
      partitionKey: { name: "pk", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "sk", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: "expires_at",
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });
    const bucket = new s3.Bucket(this, "Evidence", {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      versioned: true,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      lifecycleRules: [{ noncurrentVersionExpiration: cdk.Duration.days(30) }],
    });
    const userPool = new cognito.UserPool(this, "Operators", {
      selfSignUpEnabled: false,
      signInAliases: { email: true },
      passwordPolicy: {
        minLength: 12,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
      },
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });
    const secretName =
      this.node.tryGetContext("groqSecret") || "aquaagent/groq";
    const groqSecret = secrets.Secret.fromSecretNameV2(
      this,
      "GroqSecret",
      secretName,
    );
    const shared = {
      TABLE_NAME: table.tableName,
      BUCKET_NAME: bucket.bucketName,
    };
    const makeFunction = (
      name: string,
      handler: string,
      extra: Record<string, string> = {},
      objects = true,
    ) => {
      const fn = new lambda.Function(this, name, {
        runtime: lambda.Runtime.PYTHON_3_12,
        architecture: lambda.Architecture.X86_64,
        handler,
        code: lambda.Code.fromAsset(path.join(__dirname, "../backend/package")),
        memorySize: 1024,
        timeout: cdk.Duration.seconds(120),
        environment: { ...shared, ...extra },
        logGroup: new logs.LogGroup(this, `${name}Logs`, {
          retention: logs.RetentionDays.ONE_WEEK,
          removalPolicy: cdk.RemovalPolicy.DESTROY,
        }),
        tracing: lambda.Tracing.ACTIVE,
      });
      table.grantReadWriteData(fn);
      if (objects) bucket.grantReadWrite(fn);
      new cloudwatch.Alarm(this, `${name}Errors`, {
        metric: fn.metricErrors({ period: cdk.Duration.minutes(5) }),
        threshold: 3,
        evaluationPeriods: 1,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      });
      return fn;
    };
    const apiFunction = makeFunction("Api", "backend.api.handler.handler");
    const simulationFunction = makeFunction(
      "Simulation",
      "backend.workflows.jobs.handler",
    );
    const agentFunction = makeFunction(
      "Agents",
      "backend.workflows.jobs.handler",
      {
        GROQ_SECRET_NAME: secretName,
        GROQ_MODEL:
          this.node.tryGetContext("groqModel") || "openai/gpt-oss-20b",
      },
    );
    groqSecret.grantRead(agentFunction);
    const verifierFunction = makeFunction(
      "Verifier",
      "backend.workflows.jobs.handler",
    );
    const progressFunction = makeFunction(
      "Progress",
      "backend.api.websocket.publisher",
      {},
      false,
    );
    const wsHandler = makeFunction(
      "WebSocketHandler",
      "backend.api.websocket.handler",
      {},
      false,
    );
    const wsAuth = makeFunction(
      "WebSocketAuthorizer",
      "backend.api.websocket.authorizer",
      {},
      false,
    );
    const ws = new apigw.WebSocketApi(this, "RunUpdates", {
      connectRouteOptions: {
        integration: new WebSocketLambdaIntegration("Connect", wsHandler),
        authorizer: new WebSocketLambdaAuthorizer("ConnectionTicket", wsAuth, {
          identitySource: ["route.request.querystring.ticket"],
        }),
      },
      disconnectRouteOptions: {
        integration: new WebSocketLambdaIntegration("Disconnect", wsHandler),
      },
    });
    ws.addRoute("subscribe", {
      integration: new WebSocketLambdaIntegration("Subscribe", wsHandler),
    });
    const wsStage = new apigw.WebSocketStage(this, "UpdatesStage", {
      webSocketApi: ws,
      stageName: "live",
      autoDeploy: true,
    });
    progressFunction.addEnvironment(
      "WEBSOCKET_MANAGEMENT_URL",
      wsStage.callbackUrl,
    );
    ws.grantManageConnections(progressFunction);
    for (const fn of [
      apiFunction,
      simulationFunction,
      agentFunction,
      verifierFunction,
    ]) {
      fn.addEnvironment("PUBLISHER_FUNCTION", progressFunction.functionName);
      progressFunction.grantInvoke(fn);
    }
    const workflowLogs = new logs.LogGroup(this, "WorkflowLogs", {
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    const invoke = (name: string, fn: lambda.IFunction, phase: string) =>
      new tasks.LambdaInvoke(this, name, {
        lambdaFunction: fn,
        payload: sfn.TaskInput.fromObject({
          run_id: sfn.JsonPath.stringAt("$.run_id"),
          phase,
        }),
        payloadResponseOnly: true,
        resultPath: "$.job",
      }).addRetry({
        errors: [
          "Lambda.ServiceException",
          "Lambda.AWSLambdaException",
          "Lambda.SdkClientException",
          "States.TaskFailed",
        ],
        interval: cdk.Duration.seconds(2),
        backoffRate: 2,
        maxAttempts: 2,
      });
    const baseline = invoke("Compute baseline", simulationFunction, "baseline");
    const investigate = invoke("Investigate and plan", agentFunction, "agents");
    const prepare = new tasks.LambdaInvoke(this, "Wait for operator", {
      lambdaFunction: verifierFunction,
      integrationPattern: sfn.IntegrationPattern.WAIT_FOR_TASK_TOKEN,
      payload: sfn.TaskInput.fromObject({
        run_id: sfn.JsonPath.stringAt("$.run_id"),
        phase: "wait",
        task_token: sfn.JsonPath.taskToken,
      }),
      resultPath: "$.approval",
      taskTimeout: sfn.Timeout.duration(cdk.Duration.hours(24)),
    });
    const approved = invoke(
      "Simulate approved actions",
      verifierFunction,
      "apply",
    );
    const report = invoke("Save evidence", verifierFunction, "report");
    const rejected = invoke(
      "Save rejection evidence",
      verifierFunction,
      "report",
    );
    const infeasible = invoke(
      "Save infeasibility evidence",
      verifierFunction,
      "report",
    );
    const failure = new tasks.LambdaInvoke(this, "Persist workflow failure", {
      lambdaFunction: verifierFunction,
      payload: sfn.TaskInput.fromObject({
        run_id: sfn.JsonPath.stringAt("$.run_id"),
        phase: "failure",
      }),
      payloadResponseOnly: true,
    }).next(new sfn.Fail(this, "Run failed"));
    for (const task of [
      baseline,
      investigate,
      prepare,
      approved,
      report,
      rejected,
      infeasible,
    ])
      task.addCatch(failure, { resultPath: "$.workflow_error" });
    const decision = new sfn.Choice(this, "Approved exact plan?")
      .when(
        sfn.Condition.stringEquals("$.approval.decision", "approve"),
        approved.next(report),
      )
      .otherwise(rejected);
    const feasible = new sfn.Choice(this, "Plan feasible?")
      .when(
        sfn.Condition.booleanEquals("$.job.feasible", true),
        prepare.next(decision),
      )
      .otherwise(infeasible);
    const machine = new sfn.StateMachine(this, "RunWorkflow", {
      definitionBody: sfn.DefinitionBody.fromChainable(
        baseline.next(investigate).next(feasible),
      ),
      stateMachineType: sfn.StateMachineType.STANDARD,
      timeout: cdk.Duration.hours(25),
      logs: {
        destination: workflowLogs,
        level: sfn.LogLevel.ERROR,
        includeExecutionData: false,
      },
      tracingEnabled: true,
    });
    machine.grantStartExecution(apiFunction);
    apiFunction.addEnvironment("STATE_MACHINE_ARN", machine.stateMachineArn);
    apiFunction.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["states:SendTaskSuccess", "states:SendTaskFailure"],
        resources: ["*"],
      }),
    );
    apiFunction.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["states:GetExecutionHistory", "states:DescribeExecution"],
        resources: [
          cdk.Stack.of(this).formatArn({
            service: "states",
            resource: "execution",
            resourceName: `${machine.stateMachineName}:*`,
            arnFormat: cdk.ArnFormat.COLON_RESOURCE_NAME,
          }),
        ],
      }),
    );
    const repository = this.node.tryGetContext("repository") as
      string | undefined;
    const repoSecret = this.node.tryGetContext("repositoryTokenSecret") as
      string | undefined;
    const app = new amplify.CfnApp(this, "Hosting", {
      name: "aquaagent",
      platform: "WEB",
      repository,
      accessToken: repoSecret
        ? cdk.SecretValue.secretsManager(repoSecret, {
            jsonField: "token",
          }).unsafeUnwrap()
        : undefined,
      buildSpec:
        'version: 1\napplications:\n  - appRoot: frontend\n    frontend:\n      phases:\n        preBuild:\n          commands:\n            - nvm use 22\n            - npm ci\n        build:\n          commands:\n            - npm run build\n      artifacts:\n        baseDirectory: dist\n        files:\n          - "**/*"\n      cache:\n        paths:\n          - node_modules/**/*\n',
      customRules: [
        {
          source:
            "</^[^.]+$|\\.(?!(css|gif|ico|jpg|js|png|txt|svg|woff|woff2|ttf|map|json|webp)$)([^.]+$)/>",
          target: "/index.html",
          status: "200",
        },
      ],
    });
    const origin =
      this.node.tryGetContext("frontendOrigin") ||
      `https://main.${app.attrDefaultDomain}`;
    const client = userPool.addClient("WebOperator", {
      generateSecret: false,
      authFlows: { userSrp: true },
      oAuth: {
        flows: { authorizationCodeGrant: true },
        scopes: [
          cognito.OAuthScope.OPENID,
          cognito.OAuthScope.EMAIL,
          cognito.OAuthScope.PROFILE,
        ],
        callbackUrls: [origin],
        logoutUrls: [origin],
      },
      preventUserExistenceErrors: true,
    });
    const domain = userPool.addDomain("Login", {
      cognitoDomain: {
        domainPrefix: `aquaagent-${this.account}-${this.region}`,
      },
    });
    const authorizer = new HttpJwtAuthorizer(
      "OperatorJwt",
      userPool.userPoolProviderUrl,
      { jwtAudience: [client.userPoolClientId] },
    );
    const http = new apigw.HttpApi(this, "HttpApi", {
      corsPreflight: {
        allowOrigins: [origin],
        allowHeaders: ["Authorization", "Content-Type", "Idempotency-Key"],
        allowMethods: [
          apigw.CorsHttpMethod.GET,
          apigw.CorsHttpMethod.POST,
          apigw.CorsHttpMethod.OPTIONS,
        ],
      },
      defaultAuthorizer: authorizer,
    });
    http.addRoutes({
      path: "/public/{proxy+}",
      methods: [apigw.HttpMethod.GET, apigw.HttpMethod.POST],
      integration: new HttpLambdaIntegration("Public", apiFunction),
      authorizer: new apigw.HttpNoneAuthorizer(),
    });
    http.addRoutes({
      path: "/{proxy+}",
      methods: [apigw.HttpMethod.GET, apigw.HttpMethod.POST],
      integration: new HttpLambdaIntegration("Protected", apiFunction),
      authorizer,
      authorizationScopes: ["openid"],
    });
    const vars = [
      { name: "VITE_API_URL", value: http.apiEndpoint },
      { name: "VITE_WS_URL", value: wsStage.url },
      { name: "VITE_COGNITO_CLIENT_ID", value: client.userPoolClientId },
      { name: "VITE_COGNITO_DOMAIN", value: domain.baseUrl() },
      { name: "VITE_REDIRECT_URI", value: origin },
      { name: "AMPLIFY_MONOREPO_APP_ROOT", value: "frontend" },
    ];
    new amplify.CfnBranch(this, "MainBranch", {
      appId: app.attrAppId,
      branchName: "main",
      enableAutoBuild: Boolean(repository),
      environmentVariables: vars,
      framework: "React",
      stage: "PRODUCTION",
    });
    new cloudwatch.Alarm(this, "WorkflowFailures", {
      metric: machine.metricFailed({ period: cdk.Duration.minutes(5) }),
      threshold: 1,
      evaluationPeriods: 1,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
    new cdk.CfnOutput(this, "HttpUrl", { value: http.apiEndpoint });
    new cdk.CfnOutput(this, "WebSocketUrl", { value: wsStage.url });
    new cdk.CfnOutput(this, "UserPoolId", { value: userPool.userPoolId });
    new cdk.CfnOutput(this, "UserPoolClientId", {
      value: client.userPoolClientId,
    });
    new cdk.CfnOutput(this, "CognitoDomain", { value: domain.baseUrl() });
    new cdk.CfnOutput(this, "AmplifyAppId", { value: app.attrAppId });
    new cdk.CfnOutput(this, "FrontendUrl", { value: origin });
    new cdk.CfnOutput(this, "EvidenceBucket", { value: bucket.bucketName });
    new cdk.CfnOutput(this, "StateTable", { value: table.tableName });
    new cdk.CfnOutput(this, "WorkflowArn", { value: machine.stateMachineArn });
  }
}
