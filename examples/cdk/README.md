# Live Redshift validation environment

This Python CDK application creates a temporary Amazon Redshift Serverless
environment for manual investigation before release. Deployment is never part
of ordinary CI. The human operator owns both `cdk deploy` and `cdk destroy`.

## Prerequisites

- AWS CLI v2 authenticated to the intended personal AWS account.
- AWS CDK CLI v2 and Node.js installed.
- `uv` and Python 3.12 or later.
- A Region supported by this app's 4-RPU allowlist.
- VPC Block Public Access configured to permit a public workgroup in the
  dedicated VPC.
- Current Redshift Serverless compute and managed-storage pricing reviewed
  before deployment: <https://aws.amazon.com/redshift/pricing/>.

Confirm the target before creating anything:

```powershell
aws sts get-caller-identity
aws configure get region
Push-Location examples/cdk
uv sync --locked --all-groups
cdk bootstrap
Pop-Location
```

`CDKToolkit` is a retained, account/Region-level prerequisite. It can contain
S3, ECR, and IAM resources and is not removed with this validation stack.

## Deploy

Choose a temporary password that satisfies Redshift's password rules and an
expiration date that identifies when this environment should no longer exist:

```powershell
$env:DB_PASSWORD = Read-Host 'Temporary Redshift password'
$env:REDSHIFT_LIVE_EXPIRES_AT = 'YYYY-MM-DD'
Push-Location examples/cdk
cdk deploy
Pop-Location
```

The app obtains the current public IPv4 address during synthesis and permits
only that `/32` on TCP 5439. Rerun `cdk deploy` if the public address changes.
The password is not a CloudFormation output, but it is embedded in the local
`cdk.out/` assembly and the deployed CloudFormation template. Treat both as
temporary sensitive data and never upload or commit them.

Deployment outputs contain the endpoint address, port, database, username,
namespace, workgroup, and accepted CIDR. They never contain the password.

## Connect and investigate

`examples/proj1/config/settings.py` already reads `DATABASE_URL` from the
environment or an `ENV_FILE`. From the repository root, substitute the
non-secret deployment outputs:

```powershell
$encodedPassword = [uri]::EscapeDataString($env:DB_PASSWORD)
$env:DATABASE_URL = "redshift://validation_admin:${encodedPassword}@<endpoint>:5439/validation"
$env:SECRET_KEY = 'temporary-live-validation-key'
uv run --with django-environ python examples/proj1/manage.py check
```

The same values may be placed in an ignored `.env` file. Never commit that
file. There is deliberately no required validation command: a human or AI
agent may run the Django commands, ORM probes, SQL inspection, or reproduction
scripts relevant to the current investigation. Record the exact commands and
sanitized results in the live-validation PR checklist.

All validation data must remain in this disposable namespace. Clean up objects
created by a probe when practical, and do not hide cleanup failures.

## Destroy and verify

Destroy is required after success, failure, or an interrupted investigation:

```powershell
cd examples/cdk
cdk destroy
```

Use the names printed by deploy to confirm removal. Both commands must report
not found:

```powershell
aws redshift-serverless get-workgroup --workgroup-name django-redshift-live-workgroup
aws redshift-serverless get-namespace --namespace-name django-redshift-live-namespace
```

Also inspect Serverless snapshots and the CloudFormation console for retained
resources. A changed public IP requires another `cdk deploy`. If VPC Block
Public Access rejects creation, inspect the account policy rather than
weakening it in this app. An interrupted deploy, failed validation, or failed
destroy still requires `cdk destroy`; retained resources are a release blocker
and require manual cleanup.
After removal, delete the local assembly and clear credentials:

```powershell
Remove-Item -Recurse -Force examples/cdk/cdk.out
Remove-Item Env:DB_PASSWORD -ErrorAction SilentlyContinue
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:REDSHIFT_LIVE_EXPIRES_AT -ErrorAction SilentlyContinue
```

The usage limit turns off user queries after 8 RPU-hours per day, and the
workgroup maximum is 8 RPU. These controls limit cost but do not replace prompt
destruction.
