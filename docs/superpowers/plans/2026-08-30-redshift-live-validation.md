# Redshift Live Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a reproducible, disposable Amazon Redshift Serverless environment and a human-operated release-gate run of `examples/proj1` against the public backend.

**Architecture:** An isolated `uv` project under `examples/cdk/` owns a Python CDK stack and AWS-free synthesis tests. Its `cdk.json` fixes the Python app command, so a human runs plain `cdk deploy`; the app reads `DB_PASSWORD` and resolves the caller's public IPv4 at synthesis time. The stack creates a dedicated public-subnet VPC, a `/32`-restricted Serverless workgroup, and cost controls; the runbook maps its outputs and `DB_PASSWORD` into the `DATABASE_URL` already consumed by `examples/proj1/config/settings.py`.

**Tech Stack:** Python 3.12, `uv`, AWS CDK v2 for Python (`aws-cdk-lib`), pytest, AWS CLI v2, Django management commands, and Amazon Redshift Serverless. No TypeScript or JavaScript CDK application is used.

**Spec:** `docs/superpowers/specs/2026-08-30-redshift-live-validation-design.md`

## Global Constraints

- Base this stacked branch and PR on `redesign/06-activate-cleanup-release`.
- Use `uv` for the isolated live-validation environment and every Python command.
- Never deploy AWS resources from ordinary CI or an application test.
- Use username/password database authentication only; IAM, browser SSO, and provider authentication remain out of scope.
- Read `DB_PASSWORD` only from the process environment, set `AdminUserPassword`, and never print or output it.
- Accept only a single-host public IPv4 `/32`; never default to or permit `0.0.0.0/0`.
- Use three public subnets in distinct Availability Zones, an internet gateway, no NAT gateway, and no operator-managed Elastic IP.
- Expose only TCP 5439 from the accepted `/32`; require TLS in Django settings.
- Use base capacity 4 RPU only in a Region where Redshift Serverless supports it; fail preflight otherwise.
- Set a conservative maximum capacity and a daily `serverless-compute` usage limit with breach action `deactivate`.
- Create no final or manual snapshot. Destroy both workgroup and namespace, then verify that both are gone.
- Tag resources with `Purpose=django-redshift-backend-live-validation`.
- Keep all committed tests AWS-free. Commands that contact AWS are explicit operator actions only.
- Keep `examples/cdk/cdk.out/` ignored; it contains the synthesized password value and must be removed after destroy.

---

### Task 1: Isolated CDK Project and Contract Helpers

**Files:**
- Create: `examples/cdk/pyproject.toml`
- Create: `examples/cdk/uv.lock`
- Create: `examples/cdk/cdk.json`
- Create: `examples/cdk/app.py`
- Create: `examples/cdk/cdk_app/__init__.py`
- Create: `examples/cdk/cdk_app/config.py`
- Create: `examples/cdk/tests/test_config.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: Python 3.12, fixed environment value `DB_PASSWORD`, plus CDK's standard account and Region environment.
- Produces: `ValidationConfig.from_environment(environ: Mapping[str, str], *, allowed_cidr: str) -> ValidationConfig`, `validate_allowed_cidr(value: str) -> str`, and commands executed with `examples/cdk/` as their working directory.

- [x] **Step 1: Create the isolated project metadata**

Create `examples/cdk/pyproject.toml` with Python `>=3.12,<4`, dependencies `aws-cdk-lib>=2.220,<3` and `constructs>=10,<11`, and a `dev` dependency group containing `pytest>=8,<9`, `pytest-cov>=5,<7`, and `ruff>=0.6.2`. Configure pytest with `testpaths = ["tests"]` and Ruff with `target-version = "py312"`.

Add this exception to `.gitignore` so the isolated lock is committed:

```gitignore
!examples/cdk/uv.lock
```

Also add `examples/cdk/cdk.out/` explicitly to `.gitignore` and create
`examples/cdk/cdk.json`:

```json
{
  "app": "uv run python app.py"
}
```

- [x] **Step 2: Lock the isolated project**

Run:

```powershell
uv lock --project examples/cdk
uv run --project examples/cdk python -c "import aws_cdk; print(aws_cdk.__version__)"
```

Expected: dependency resolution succeeds and the installed CDK version prints.

- [x] **Step 3: Write failing configuration tests**

Create tests covering these exact cases:

```python
import pytest

from cdk_app.config import ValidationConfig, validate_allowed_cidr


@pytest.mark.parametrize("value", ["0.0.0.0/0", "203.0.113.0/24", "::1/128", "invalid"])
def test_allowed_cidr_requires_public_ipv4_host(value):
    with pytest.raises(ValueError, match="public IPv4 /32"):
        validate_allowed_cidr(value)


def test_environment_supplies_password():
    environ = {
        "DB_PASSWORD": "synthesis-only-value-A1",
        "CDK_DEFAULT_ACCOUNT": "123456789012",
        "CDK_DEFAULT_REGION": "ap-northeast-1",
    }
    config = ValidationConfig.from_environment(environ, allowed_cidr="8.8.8.8/32")
    assert config.allowed_cidr == "8.8.8.8/32"
    assert config.password == "synthesis-only-value-A1"
    assert config.base_capacity == 4
    assert config.max_capacity == 8
    assert config.daily_rpu_hours == 8
```

- [x] **Step 4: Run tests and confirm the module is absent**

Run: `uv run --directory examples/cdk python -m pytest tests/test_config.py -v`

Expected: collection fails because `cdk_app.config` does not exist.

- [x] **Step 5: Implement the immutable configuration object**

Implement `ValidationConfig` as a frozen dataclass. Require a non-empty `region`; use prefix `django-redshift-live`; and pin `base_capacity=4`, `max_capacity=8`, and `daily_rpu_hours=8`. Use `ipaddress.ip_network(value, strict=True)` and reject non-IPv4, non-global, or prefix lengths other than 32. Tests may use `8.8.8.8/32` as a syntactically global address for synthesis only; no test deploys or contacts that address.

- [x] **Step 6: Add the CDK entry point**

`app.py` must read the fixed `DB_PASSWORD` environment variable, resolve the public
IPv4 through an injectable standard-library function, construct
`ValidationConfig`, instantiate `LiveValidationStack`, and call `app.synth()`.
Use `CDK_DEFAULT_ACCOUNT` and `CDK_DEFAULT_REGION` through `cdk.Environment`.
Missing required values fail before synthesis and name only the missing
variable. Do not print the password.

- [x] **Step 7: Verify and commit**

Run:

```powershell
uv run --directory examples/cdk python -m pytest tests/test_config.py -q
uv run --directory examples/cdk ruff check .
```

Expected: tests and Ruff pass.

Commit:

```powershell
git add .gitignore examples/cdk
git commit -m "build: add isolated live validation project"
```

### Task 2: Network and Public-Access Safety Boundary

**Files:**
- Create: `examples/cdk/cdk_app/stack.py`
- Create: `examples/cdk/tests/test_network_stack.py`
- Modify: `examples/cdk/app.py`

**Interfaces:**
- Consumes: `ValidationConfig` from Task 1.
- Produces: `LiveValidationStack(scope, construct_id, *, config, env)` with one VPC, three public subnets, one internet gateway, zero NAT gateways, and one security group ingress rule.

- [x] **Step 1: Write failing synthesis tests**

Use `aws_cdk.assertions.Template.from_stack(stack)` and assert:

```python
template.resource_count_is("AWS::EC2::VPC", 1)
template.resource_count_is("AWS::EC2::Subnet", 3)
template.resource_count_is("AWS::EC2::NatGateway", 0)
template.resource_count_is("AWS::EC2::EIP", 0)
template.resource_count_is("AWS::EC2::SecurityGroup", 1)
template.has_resource_properties(
    "AWS::EC2::SecurityGroupIngress",
    {
        "CidrIp": "8.8.8.8/32",
        "FromPort": 5439,
        "ToPort": 5439,
        "IpProtocol": "tcp",
    },
)
```

Also inspect synthesized route tables and assert every subnet has a default route to the stack's internet gateway. Assert that no ingress rule contains `0.0.0.0/0`.

- [x] **Step 2: Run the focused test and verify failure**

Run: `uv run --directory examples/cdk python -m pytest tests/test_network_stack.py -v`

Expected: FAIL because `LiveValidationStack` is not defined.

- [x] **Step 3: Implement the minimum network stack**

Create a VPC with `nat_gateways=0`, `max_azs=3`, and one `PUBLIC` subnet configuration using a `/24` mask. Reject synthesis unless CDK resolves exactly three selected availability zones. Create a dedicated security group and add only `Peer.ipv4(config.allowed_cidr)` on `Port.tcp(5439)`. Apply the `Purpose` tag at stack scope.

- [x] **Step 4: Verify and commit**

Run:

```powershell
uv run --directory examples/cdk python -m pytest tests/test_network_stack.py -q
uv run --directory examples/cdk ruff check .
$env:DB_PASSWORD = 'synthesis-only-value-A1'
Push-Location examples/cdk
cdk synth
Pop-Location
```

Expected: tests pass and synthesis produces a template without contacting AWS.

Commit: `git commit -am "feat: define isolated validation network"` after staging the new files.

### Task 3: Redshift Serverless Resources, Secret, and Cost Controls

**Files:**
- Modify: `examples/cdk/cdk_app/stack.py`
- Create: `examples/cdk/tests/test_redshift_stack.py`

**Interfaces:**
- Consumes: VPC subnet IDs, security-group ID, and `ValidationConfig`.
- Produces: `AWS::RedshiftServerless::Namespace` and `Workgroup` resources, an API-backed usage-limit custom resource, and non-secret CloudFormation outputs.

- [x] **Step 1: Write failing resource tests**

Assert the namespace has the injected `AdminUserPassword`, a non-default admin username, a database name, no `ManageAdminPassword`, no final snapshot properties, and deletion policy `Delete`. Assert the workgroup references all three subnets and the security group, is publicly accessible, uses port 5439, requires SSL through `ConfigParameters`, and has base/max capacities 4/8. Assert the usage limit has `UsageType=serverless-compute`, `Period=daily`, `Amount=8`, and `BreachAction=deactivate`.

Assert outputs contain exactly endpoint address, port, database name, admin username, workgroup name, namespace name, and allowed CIDR. Fail if any output key contains `password`, `secret`, or `token`, case-insensitively, and assert the password value does not appear in any output value.

- [x] **Step 2: Run the focused tests and verify failure**

Run: `uv run --directory examples/cdk python -m pytest tests/test_redshift_stack.py -v`

Expected: FAIL because no Serverless resources exist.

- [x] **Step 3: Implement the namespace and workgroup**

Use L1 constructs `aws_redshiftserverless.CfnNamespace` and `CfnWorkgroup` so all security-sensitive properties are explicit. Set `admin_user_password=config.password`, `admin_username="validation_admin"`, `db_name="validation"`, and `deletion_policy=RemovalPolicy.DESTROY`. Do not set `manage_admin_password`. Add an explicit dependency from the workgroup to the namespace and pass the three public subnet IDs and dedicated security-group ID.

Set workgroup config parameter `require_ssl=true`. Do not output the password.

- [x] **Step 4: Implement the usage limit and deletion order**

CloudFormation and CDK have no Redshift Serverless usage-limit resource. Use
`AwsCustomResource` to call `CreateUsageLimit` with the workgroup ARN,
`usageType="serverless-compute"`, `period="daily"`,
`amount=config.daily_rpu_hours`, and `breachAction="deactivate"`; retain the
returned usage-limit ID as the physical resource ID and call `DeleteUsageLimit`
on deletion. Make the custom resource depend on the workgroup. Ensure deletion
orders the usage limit before the workgroup and the workgroup before the
namespace.

- [x] **Step 5: Verify and commit**

Run:

```powershell
uv run --directory examples/cdk python -m pytest tests -q
uv run --directory examples/cdk ruff check .
git diff --check
```

Commit: `git commit -am "feat: define disposable Redshift validation stack"` after staging the test file.

### Task 4: Plain CDK Deploy and Destroy Contract

**Files:**
- Modify: `examples/cdk/app.py`
- Create: `examples/cdk/tests/test_app.py`

**Interfaces:**
- Consumes: fixed `DB_PASSWORD`, CDK's standard account/Region, and an injectable public-IP lookup response.
- Produces: a Python CDK application runnable as plain `cdk deploy` and `cdk destroy` from `examples/cdk/`.

- [x] **Step 1: Write failing pure-unit tests**

Cover newline-trimmed IPv4 lookup, rejection of IPv6/private/malformed responses, missing required environment values, password exclusion from exception messages, CDK standard account/Region selection, and Region membership in the documented 4-RPU allowlist. Mock all network access; tests must never contact an IP service or AWS.

- [x] **Step 2: Run tests and verify failure**

Run: `uv run --directory examples/cdk python -m pytest tests/test_app.py -v`

Expected: FAIL because the application helpers are absent.

- [x] **Step 3: Implement environment and synthesis preflight**

Use `urllib.request` only for public-IP lookup. Require
`DB_PASSWORD`, `CDK_DEFAULT_ACCOUNT`, and
`CDK_DEFAULT_REGION`. Do not accept CDK context or custom command-line values
and never log the environment mapping.

The 4-RPU Region allowlist must be copied from the AWS Redshift Serverless
capacity documentation and tested as data. An unsupported Region stops before
synthesis with an instruction to update the reviewed allowlist rather than
silently increasing capacity.

- [ ] **Step 4: Verify the plain CDK commands**

From `examples/cdk/`, run `cdk synth` with mocked/injected IP lookup for the
AWS-free check. Confirm `cdk.json` supplies the app command and no `--app`,
context, or parameter argument is needed. Document `cdk deploy` and
`cdk destroy` as the only mutating operator commands; post-destroy AWS CLI
commands are read-only verification.

- [x] **Step 5: Verify and commit**

Run:

```powershell
uv run --directory examples/cdk python -m pytest tests/test_app.py -q
uv run --directory examples/cdk ruff check .
```

Commit: `git commit -am "feat: add plain CDK validation lifecycle"` after staging the new files.

### Task 5: Operator Guide and Release Evidence Template

**Files:**
- Create: `examples/cdk/README.md`
- Create: `.github/PULL_REQUEST_TEMPLATE/live-redshift-validation.md`
- Modify: `docs/superpowers/specs/2026-08-23-redshift-backend-redesign-design.md`

**Interfaces:**
- Consumes: commands and outputs from Tasks 1-4 plus the existing `examples/proj1/config/settings.py` `DATABASE_URL` interface.
- Produces: an end-to-end human runbook and sanitized evidence checklist for release 6.0.0.

- [x] **Step 1: Write the runbook**

Document exact commands for prerequisites, Python CDK bootstrap, setting the
the fixed password environment variable, plain `cdk deploy`, exporting the non-secret
stack outputs, examples of freely selected Django or SQL probes, plain
`cdk destroy`, and read-only cleanup verification. Do not prescribe a
repository-owned validation command; show how to URL-escape `DB_PASSWORD`, set
`DATABASE_URL=redshift://<user>:<password>@<host>:<port>/<database>`, and run a
selected command through the existing `config.settings`. Include the existing
example's required `SECRET_KEY` environment value and the equivalent ignored
`.env` form. The
password handoff must use this PowerShell shape:

```powershell
$env:DB_PASSWORD = Read-Host 'Temporary Redshift password'
Push-Location examples/cdk
cdk deploy
Pop-Location
```

The runbook must explain that the password is present in the ignored local
`cdk.out/` assembly, must not be committed or uploaded, and must be cleared
from `DB_PASSWORD` after validation and destroy.

State estimated cost inputs without promising a fixed price; link the AWS
pricing page and require the operator to confirm current pricing before
deployment.

Include failure paths for changed public IP, VPC Block Public Access, interrupted deploy, failed validation, failed destroy, retained workgroup/namespace, retained snapshots, and retained `CDKToolkit` resources. Make destroy mandatory after both success and failure.

- [x] **Step 2: Add the manual release checklist**

The template must record commit SHA, UTC timestamp, operator, AWS account suffix only, Region, Django version, driver version, sanitized endpoint, the exact validation commands or probes selected for the session, their outcomes, cleanup performed, destroy result, and confirmation that namespace, workgroup, and snapshots are absent. It must warn against pasting passwords, access keys, tokens, or full AWS account IDs.

- [x] **Step 3: Close the parent-design deferral**

Update the redesign design's real-Redshift risk/status text to point to this release-gate implementation. Do not mark real validation successful until a human run has actually passed.

- [x] **Step 4: Verify and commit**

Run:

```powershell
rg -n -i "password|secret|token|access.key" examples/cdk/README.md .github/PULL_REQUEST_TEMPLATE/live-redshift-validation.md
git diff --check
```

Inspect every match and confirm it is an instruction or redaction warning, not a credential.

Commit: `git commit -am "docs: add live Redshift release runbook"` after staging new files.

### Task 6: AWS-Free CI, Final Verification, and Stacked PR Recording

**Files:**
- Create: `.github/workflows/live-validation-contract.yml`
- Modify: `docs/superpowers/plans/2026-08-30-redshift-live-validation.md`
- Modify: PR #9 and tracking PR #1; do not create temporary PR-body files.

**Interfaces:**
- Consumes: the complete isolated CDK project and operator documentation.
- Produces: blocking AWS-free synthesis/contract checks and a reviewable stacked PR ready for the later human AWS run.

- [x] **Step 1: Add the AWS-free workflow**

Use `actions/checkout@v6` and `astral-sh/setup-uv@v7` with Python 3.12. Run exactly:

```yaml
- run: uv sync --directory examples/cdk --locked --all-groups
- run: uv run --directory examples/cdk python -m pytest tests -q
- run: uv run --directory examples/cdk ruff check .
```

Do not add AWS credentials, OIDC permissions, environment secrets, deploy, or destroy steps.

- [x] **Step 2: Run final local verification**

Run:

```powershell
uv sync --directory examples/cdk --locked --all-groups
uv run --directory examples/cdk python -m pytest tests -q
uv run --directory examples/cdk ruff check .
uv run --only-dev tox -v
uv build
uv run --only-dev twine check dist/*
git diff --check
git status --short
```

Expected: all tests, lint, package checks, and diff checks pass; status contains only the plan checkbox/result updates before the final commit.

- [x] **Step 3: Record measured results in this plan and commit**

Mark completed checkboxes and append exact command versions and test counts. Do not claim a real Redshift pass; label it pending human execution.

Commit:

```powershell
git add .github/workflows/live-validation-contract.yml docs/superpowers/plans/2026-08-30-redshift-live-validation.md
git commit -m "ci: verify live validation contracts without AWS"
```

- [ ] **Step 4: Push the stacked branch and update PR #9**

Push `redesign/07-live-validation` without force. Confirm PR #9 still targets `redesign/06-activate-cleanup-release`. Update its summary, review focus, verification counts, and explicit statement that the real AWS run remains a manual pre-release gate.

- [ ] **Step 5: Update tracking PR #1**

Add #9 to the stack, replace stale current-status text, and append a progress comment containing branch, head commit, AWS-free CI results, fixed-environment credential decision, deferred human live-run status, and release-blocking cleanup requirement.

- [ ] **Step 6: Stop before AWS deployment**

Report the exact reviewed operator command sequence. A human must separately choose the AWS account/Region, confirm current pricing and permissions, set `DB_PASSWORD`, run plain `cdk deploy`, run validation, run plain `cdk destroy`, remove `cdk.out/`, and clear the password variables. Repository implementation completion does not authorize or imply an AWS deployment.

## Implementation Results

- Python CDK project and lock completed with uv 0.11.29 and Python 3.12.
- AWS-free CDK contract suite: 20 passed in 50.08 seconds after removing the
  expiration-variable contract.
- CDK project Ruff check: passed.
- Full backend tox matrix: 14 Python/Django environments passed; lint and
  package checks passed in 425.08 seconds. Django 4.2 environments reported
  349 passed/13 skipped each; Django 5.2, 6.0, and 6.1 environments reported
  362 passed/2 skipped each.
- Wheel and sdist passed Twine validation as part of the tox `check`
  environment.
- Local plain `cdk synth` was not run because the CDK CLI is not installed on
  this workstation. Template synthesis is exercised by the 20 AWS-free tests;
  installing CDK CLI v2 remains an operator prerequisite.
- Real Redshift deployment, validation, and destruction: pending explicit
  human execution before release.
