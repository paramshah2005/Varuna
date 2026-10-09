# AWS deployment

Cloud deployment is pending AWS authentication, target region confirmation, the Amplify Git connection, and storing the Groq credential in Secrets Manager. The source repository is https://github.com/paramshah2005/Varuna. A display/account name such as Yoovan is not an AWS CLI profile or account ID. Do not paste AWS access keys into chat. Configure access locally, preferably with an existing IAM Identity Center profile.

## Account preparation

1. Configure the desired profile locally and verify `aws sts get-caller-identity --profile <profile>`.
2. Confirm the target region. The CDK planning default is `ap-south-1`; override with `-c region=<region>` rather than inferring it from the account name.
3. In the AWS console, create a Secrets Manager secret such as `aquaagent/groq` containing JSON `{"api_key":"YOUR_KEY"}`. Enter the credential through the console or another protected channel. Its name is the only value needed by CDK. Rotate any key previously exposed in chat.
4. Connect https://github.com/paramshah2005/Varuna to Amplify after source publication. Amplify builds the `main` branch and `frontend` monorepo directory.
5. To automate the Amplify Git connection, provide a repository URL through CDK context and an existing secret containing a Git provider connection token as JSON `{"token":"YOUR_TOKEN"}`. The token is resolved server-side through a Secrets Manager dynamic reference. Alternatively connect the generated Amplify app to Git through the AWS console. No Git token belongs in project files or Vite variables.

## Package and provision

From the root:

```powershell
.venv/Scripts/python.exe scripts/package_backend.py
cd infrastructure
npm ci
npm run build
npx cdk synth --quiet -c region=<region> -c groqSecret=aquaagent/groq
npx cdk bootstrap --profile <profile> -c region=<region>
npx cdk deploy --profile <profile> -c region=<region> -c groqSecret=aquaagent/groq -c groqModel=openai/gpt-oss-20b -c repository=<git-url> -c repositoryTokenSecret=<existing-secret-name> --outputs-file outputs.json
```

Packaging downloads pinned Python 3.12 Linux x86-64 wheels into an ignored directory; it does not deploy them. Use a supported Python/Node environment and sufficient disk space. The stack intentionally imports an existing Groq secret and grants only the agent Lambda permission to read it. Cloud inference never reads a local key environment variable.

The Amplify app is created before Cognito callback/CORS configuration. Frontend variables are placed on the Amplify branch to avoid a CloudFormation dependency cycle. If a custom frontend domain is required, supply `-c frontendOrigin=https://<domain>` and configure that exact HTTPS domain in Amplify before testing login.

The branch environment includes API/WS URLs, Cognito client/domain, and redirect URL. Build settings are in root `amplify.yml` and the CDK stack. The SPA rewrite serves `index.html` for routes while preserving asset paths. Protected HTTP endpoints require a Cognito access token with `openid` scope. Public station discovery/routing endpoints cannot start or modify a run. Self-registration is disabled; create the operator through Cognito's admin flow and complete the normal invitation/password setup yourself.

## Required live verification

- Amplify must build from Git, serve HTTPS, and load `/public` directly through the SPA rewrite.
- Authenticate the operator, then test valid/expired/wrong-audience tokens and a second operator's denied access.
- Start a run and verify HTTP 202 arrives before the job completes; check actual Standard workflow history, retries, and callback wait.
- Verify DynamoDB scenario/run/version/event records and S3 snapshots/time series/reports. Reopen the saved run through the deployed app.
- Approve/reject exact plan versions. Attempt stale approval after an edit. Repeat the same idempotency key and confirm actions execute once.
- Open an authenticated WebSocket ticket, subscribe only to an owned run, reconnect using the last contiguous sequence, and test polling when WebSocket is unavailable. Expired tickets and wrong-owner subscription attempts must fail.
- Inject a bounded agent-job failure and verify persisted state is used after retry. Check Groq failures and actual remaining quota; fallback must remain labelled.
- Confirm Secrets Manager values never enter browser bundles, exported scenarios, workflow logs or reports. CloudWatch workflow logging excludes execution payloads so callback tokens remain server-side.
- Save actual deployment URLs, AWS run latency, provider calls/tokens, and balance residuals in `VERIFICATION.md` and `SUBMISSION.md` before claiming AWS use in a hackathon submission.

No local test or CDK synthesis proves these cloud operations. Costs are determined by the account's service usage and provider plan; this project does not assume free usage is unlimited.

## Cleanup

Run `npx cdk destroy --profile <profile> -c region=<region>`. The bucket, table and user pool are retained to preserve evidence and identities. Review their contents and remove them separately when authorized. The imported secrets remain intact. Remove Git connection tokens if they are no longer used, and verify account resources in the selected region.
