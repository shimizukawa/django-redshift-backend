# Redshift Live Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a reproducible, disposable Amazon Redshift Serverless environment and a human-operated release-gate run of `examples/proj1` against the public backend.

**Architecture:** An isolated `uv` project under `live_validation/` owns a Python CDK stack and AWS-free synthesis tests. Its `cdk.json` fixes the Python app command, so a human runs plain `cdk deploy`; the app reads fixed environment variables and resolves the caller's public IPv4 at synthesis time. The stack creates a dedicated public-subnet VPC, a `/32`-restricted Serverless workgroup, and cost controls; the same local password is supplied to a dedicated Django settings module and validation runner.

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
- Tag resources with `Purpose=django-redshift-backend-live-validation` and operator-supplied `Owner` and `ExpiresAt` values.
- Keep all committed tests AWS-free. Commands that contact AWS are explicit operator actions only.
- Keep `live_validation/cdk.out/` ignored; it contains the synthesized password value and must be removed after destroy.

---

### Task 1: Isolated CDK Project and Contract Helpers

**Files:**
- Create: `live_validation/pyproject.toml`
- Create: `live_validation/uv.lock`
- Create: `live_validation/cdk.json`
- Create: `live_validation/app.py`
- Create: `live_validation/live_validation/__init__.py`
- Create: `live_validation/live_validation/config.py`
- Create: `live_validation/tests/test_config.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: Python 3.12, fixed environment values `DB_PASSWORD`, `REDSHIFT_LIVE_OWNER`, and `REDSHIFT_LIVE_EXPIRES_AT`, plus CDK's standard account and Region environment.
- Produces: `ValidationConfig.from_environment(environ: Mapping[str, str], *, allowed_cidr: str) -> ValidationConfig`, `validate_allowed_cidr(value: str) -> str`, and the `uv run --project live_validation ...` command prefix.

- [ ] **Step 1: Create the isolated project metadata**

Create `live_validation/pyproject.toml` with Python `>=3.12,<4`, dependencies `aws-cdk-lib>=2.220,<3` and `constructs>=10,<11`, and a `dev` dependency group containing `pytest>=8,<9`, `pytest-cov>=5,<7`, and `ruff>=0.6.2`. Configure pytest with `testpaths = ["tests"]` and Ruff with `target-version = "py312"`.

Add these exceptions to `.gitignore` so the isolated lock and the example migration added later are committed:

```gitignore
!live_validation/uv.lock
!examples/proj1/testapp/migrations/
!examples/proj1/testapp/migrations/*.py
```

Also add `live_validation/cdk.out/` explicitly to `.gitignore` and create
`live_validation/cdk.json`:

```json
{
  "app": "uv run python app.py"
}
```

- [ ] **Step 2: Lock the isolated project**

Run:

```powershell
uv lock --project live_validation
uv run --project live_validation python -c "import aws_cdk; print(aws_cdk.__version__)"
```

Expected: dependency resolution succeeds and the installed CDK version prints.

- [ ] **Step 3: Write failing configuration tests**

Create tests covering these exact cases:

```python
import pytest

from live_validation.config import ValidationConfig, validate_allowed_cidr


@pytest.mark.parametrize("value", ["0.0.0.0/0", "203.0.113.0/24", "::1/128", "invalid"])
def test_allowed_cidr_requires_public_ipv4_host(value):
    with pytest.raises(ValueError, match="public IPv4 /32"):
        validate_allowed_cidr(value)


def test_environment_supplies_password_and_ownership_values():
    environ = {
        "DB_PASSWORD": "synthesis-only-value-A1",
        "REDSHIFT_LIVE_OWNER": "release-operator",
        "REDSHIFT_LIVE_EXPIRES_AT": "2026-08-31",
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

- [ ] **Step 4: Run tests and confirm the module is absent**

Run: `uv run --project live_validation pytest live_validation/tests/test_config.py -v`

Expected: collection fails because `live_validation.config` does not exist.

- [ ] **Step 5: Implement the immutable configuration object**

Implement `ValidationConfig` as a frozen dataclass. Require non-empty `owner`, `expires_at`, and `region`; use prefix `django-redshift-live`; and pin `base_capacity=4`, `max_capacity=8`, and `daily_rpu_hours=8`. Use `ipaddress.ip_network(value, strict=True)` and reject non-IPv4, non-global, or prefix lengths other than 32. Tests may use `8.8.8.8/32` as a syntactically global address for synthesis only; no test deploys or contacts that address.

- [ ] **Step 6: Add the CDK entry point**

`app.py` must read the three fixed environment variables, resolve the public
IPv4 through an injectable standard-library function, construct
`ValidationConfig`, instantiate `LiveValidationStack`, and call `app.synth()`.
Use `CDK_DEFAULT_ACCOUNT` and `CDK_DEFAULT_REGION` through `cdk.Environment`.
Missing required values fail before synthesis and name only the missing
variable. Do not print the password.

- [ ] **Step 7: Verify and commit**

Run:

```powershell
uv run --project live_validation pytest live_validation/tests/test_config.py -q
uv run --project live_validation ruff check live_validation
```

Expected: tests and Ruff pass.

Commit:

```powershell
git add .gitignore live_validation
git commit -m "build: add isolated live validation project"
```

### Task 2: Network and Public-Access Safety Boundary

**Files:**
- Create: `live_validation/live_validation/stack.py`
- Create: `live_validation/tests/test_network_stack.py`
- Modify: `live_validation/app.py`

**Interfaces:**
- Consumes: `ValidationConfig` from Task 1.
- Produces: `LiveValidationStack(scope, construct_id, *, config, env)` with one VPC, three public subnets, one internet gateway, zero NAT gateways, and one security group ingress rule.

- [ ] **Step 1: Write failing synthesis tests**

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

- [ ] **Step 2: Run the focused test and verify failure**

Run: `uv run --project live_validation pytest live_validation/tests/test_network_stack.py -v`

Expected: FAIL because `LiveValidationStack` is not defined.

- [ ] **Step 3: Implement the minimum network stack**

Create a VPC with `nat_gateways=0`, `max_azs=3`, and one `PUBLIC` subnet configuration using a `/24` mask. Reject synthesis unless CDK resolves exactly three selected availability zones. Create a dedicated security group and add only `Peer.ipv4(config.allowed_cidr)` on `Port.tcp(5439)`. Apply `Purpose`, `Owner`, and `ExpiresAt` tags at stack scope.

- [ ] **Step 4: Verify and commit**

Run:

```powershell
uv run --project live_validation pytest live_validation/tests/test_network_stack.py -q
uv run --project live_validation ruff check live_validation
$env:DB_PASSWORD = 'synthesis-only-value-A1'
$env:REDSHIFT_LIVE_OWNER = 'test'
$env:REDSHIFT_LIVE_EXPIRES_AT = '2026-08-31'
Push-Location live_validation
cdk synth
Pop-Location
```

Expected: tests pass and synthesis produces a template without contacting AWS.

Commit: `git commit -am "feat: define isolated validation network"` after staging the new files.

### Task 3: Redshift Serverless Resources, Secret, and Cost Controls

**Files:**
- Modify: `live_validation/live_validation/stack.py`
- Create: `live_validation/tests/test_redshift_stack.py`

**Interfaces:**
- Consumes: VPC subnet IDs, security-group ID, and `ValidationConfig`.
- Produces: `AWS::RedshiftServerless::Namespace`, `Workgroup`, and `UsageLimit` resources plus non-secret CloudFormation outputs.

- [ ] **Step 1: Write failing resource tests**

Assert the namespace has the injected `AdminUserPassword`, a non-default admin username, a database name, no `ManageAdminPassword`, no final snapshot properties, and deletion policy `Delete`. Assert the workgroup references all three subnets and the security group, is publicly accessible, uses port 5439, requires SSL through `ConfigParameters`, and has base/max capacities 4/8. Assert the usage limit has `UsageType=serverless-compute`, `Period=daily`, `Amount=8`, and `BreachAction=deactivate`.

Assert outputs contain exactly endpoint address, port, database name, admin username, workgroup name, namespace name, and allowed CIDR. Fail if any output key contains `password`, `secret`, or `token`, case-insensitively, and assert the password value does not appear in any output value.

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `uv run --project live_validation pytest live_validation/tests/test_redshift_stack.py -v`

Expected: FAIL because no Serverless resources exist.

- [ ] **Step 3: Implement the namespace and workgroup**

Use L1 constructs `aws_redshiftserverless.CfnNamespace` and `CfnWorkgroup` so all security-sensitive properties are explicit. Set `admin_user_password=config.password`, `admin_username="validation_admin"`, `db_name="validation"`, and `deletion_policy=RemovalPolicy.DESTROY`. Do not set `manage_admin_password`. Add an explicit dependency from the workgroup to the namespace and pass the three public subnet IDs and dedicated security-group ID.

Set workgroup config parameter `require_ssl=true`. Do not output the password.

- [ ] **Step 4: Implement the usage limit and deletion order**

Use `CfnUsageLimit` with the workgroup ARN, `usage_type="serverless-compute"`, `period="daily"`, `amount=config.daily_rpu_hours`, and `breach_action="deactivate"`. Make the usage limit depend on the workgroup. Ensure CloudFormation deletes the usage limit before the workgroup and the workgroup before the namespace through resource references/dependencies.

- [ ] **Step 5: Verify and commit**

Run:

```powershell
uv run --project live_validation pytest live_validation/tests -q
uv run --project live_validation ruff check live_validation
git diff --check
```

Commit: `git commit -am "feat: define disposable Redshift validation stack"` after staging the test file.

### Task 4: Plain CDK Deploy and Destroy Contract

**Files:**
- Modify: `live_validation/app.py`
- Create: `live_validation/tests/test_app.py`

**Interfaces:**
- Consumes: fixed environment variables, CDK's standard account/Region, and an injectable public-IP lookup response.
- Produces: a Python CDK application runnable as plain `cdk deploy` and `cdk destroy` from `live_validation/`.

- [ ] **Step 1: Write failing pure-unit tests**

Cover newline-trimmed IPv4 lookup, rejection of IPv6/private/malformed responses, missing fixed environment variables, password exclusion from exception messages, CDK standard account/Region selection, and Region membership in the documented 4-RPU allowlist. Mock all network access; tests must never contact an IP service or AWS.

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run --project live_validation pytest live_validation/tests/test_app.py -v`

Expected: FAIL because the application helpers are absent.

- [ ] **Step 3: Implement environment and synthesis preflight**

Use `urllib.request` only for public-IP lookup. Require
`DB_PASSWORD`, `REDSHIFT_LIVE_OWNER`,
`REDSHIFT_LIVE_EXPIRES_AT`, `CDK_DEFAULT_ACCOUNT`, and
`CDK_DEFAULT_REGION`. Do not accept CDK context or custom command-line values
and never log the environment mapping.

The 4-RPU Region allowlist must be copied from the AWS Redshift Serverless
capacity documentation and tested as data. An unsupported Region stops before
synthesis with an instruction to update the reviewed allowlist rather than
silently increasing capacity.

- [ ] **Step 4: Verify the plain CDK commands**

From `live_validation/`, run `cdk synth` with mocked/injected IP lookup for the
AWS-free check. Confirm `cdk.json` supplies the app command and no `--app`,
context, or parameter argument is needed. Document `cdk deploy` and
`cdk destroy` as the only mutating operator commands; post-destroy AWS CLI
commands are read-only verification.

- [ ] **Step 5: Verify and commit**

Run:

```powershell
uv run --project live_validation pytest live_validation/tests/test_app.py -q
uv run --project live_validation ruff check live_validation
```

Commit: `git commit -am "feat: add plain CDK validation lifecycle"` after staging the new files.

### Task 5: Django Live Settings, Migration Fixture, and ORM Smoke Runner

**Files:**
- Create: `examples/proj1/config/settings_live.py`
- Create: `examples/proj1/testapp/migrations/__init__.py`
- Create: `examples/proj1/testapp/migrations/0001_initial.py`
- Create: `examples/proj1/live_validate.py`
- Create: `tests/test_live_validation_contract.py`

**Interfaces:**
- Consumes: environment variables `NAME`, `HOST`, `PORT`, `USER`, and `DB_PASSWORD` supplied by the human operator.
- Produces: a TLS-required `DATABASES["default"]`, committed migration SQL coverage, and `live_validate.py` returning zero only after connection, migration, `sqlmigrate`, and CRUD succeed.

- [ ] **Step 1: Write AWS-free contract tests**

Patch the five environment variables and import `config.settings_live`; assert the database dictionary equals the standard settings plus `OPTIONS={"ssl": True}`. Parameterize missing/empty variables and assert import raises `ImproperlyConfigured` naming only the missing non-secret key. Assert source text contains no password value and that `live_validate.py --help` does not initialize a connection.

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run --with pytest pytest tests/test_live_validation_contract.py -v`

Expected: FAIL because `settings_live.py` and `live_validate.py` do not exist.

- [ ] **Step 3: Implement dedicated live settings**

Import defaults from `.settings`, replace `DATABASES` entirely from the five required environment variables, convert `PORT` to `int`, set `ENGINE="django_redshift_backend"`, and set `OPTIONS={"ssl": True}`. Never build or print a database URL.

- [ ] **Step 4: Generate and commit the example migration**

Run:

```powershell
uv run --with "Django>=5.2,<5.3" --with django-environ examples/proj1/manage.py makemigrations testapp --settings=config.settings_live
```

Use dummy non-secret environment values and monkeypatch or settings-only invocation so generation does not open a socket. Inspect `0001_initial.py`; it must represent all existing `testapp` models, `DistKey`, and `SortKey` declarations without hand-editing generated state.

- [ ] **Step 5: Implement the validation runner**

The runner executes, in order, using `DJANGO_SETTINGS_MODULE=config.settings_live`:

1. `django.setup()` and `connections["default"].ensure_connection()`;
2. `call_command("migrate", interactive=False, verbosity=1)`;
3. `call_command("sqlmigrate", "testapp", "0001", verbosity=1)`;
4. create a `TestReferencedModel` and `TestModelWithMetaKeys` row;
5. read and assert values, update `age`, refresh and assert, then delete both rows;
6. report package revision, Django/driver versions, Region, and sanitized host/port/database/user metadata.

Wrap execution in `try/finally`; attempt deletion of application rows in `finally`, preserve the original exception, and always print `Run the documented destroy command now.` Passwords and exception representations containing connection kwargs must never be printed.

- [ ] **Step 6: Verify and commit**

Run:

```powershell
uv run --with pytest pytest tests/test_live_validation_contract.py -q
uv run --only-dev ruff check examples/proj1/config/settings_live.py examples/proj1/live_validate.py tests/test_live_validation_contract.py
git diff --check
```

Commit:

```powershell
git add .gitignore examples/proj1/config/settings_live.py examples/proj1/live_validate.py examples/proj1/testapp/migrations tests/test_live_validation_contract.py
git commit -m "test: add real Redshift validation runner"
```

### Task 6: Operator Guide and Release Evidence Template

**Files:**
- Create: `live_validation/README.md`
- Create: `.github/PULL_REQUEST_TEMPLATE/live-redshift-validation.md`
- Modify: `docs/superpowers/specs/2026-08-23-redshift-backend-redesign-design.md`

**Interfaces:**
- Consumes: commands and outputs from Tasks 1-5.
- Produces: an end-to-end human runbook and sanitized evidence checklist for release 6.0.0.

- [ ] **Step 1: Write the runbook**

Document exact commands for prerequisites, Python CDK bootstrap, setting the
three fixed environment variables, plain `cdk deploy`, exporting the non-secret
stack outputs, running `live_validate.py`, plain `cdk destroy`, and read-only
cleanup verification. The password handoff must use this PowerShell shape:

```powershell
$env:DB_PASSWORD = Read-Host 'Temporary Redshift password'
$env:REDSHIFT_LIVE_OWNER = 'operator-name'
$env:REDSHIFT_LIVE_EXPIRES_AT = 'YYYY-MM-DD'
Push-Location live_validation
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

- [ ] **Step 2: Add the manual release checklist**

The template must record commit SHA, UTC timestamp, operator, AWS account suffix only, Region, Django version, driver version, sanitized endpoint, migration result, `sqlmigrate` result, CRUD result, destroy result, and confirmation that namespace, workgroup, and snapshots are absent. It must warn against pasting passwords, access keys, tokens, or full AWS account IDs.

- [ ] **Step 3: Close the parent-design deferral**

Update the redesign design's real-Redshift risk/status text to point to this release-gate implementation. Do not mark real validation successful until a human run has actually passed.

- [ ] **Step 4: Verify and commit**

Run:

```powershell
rg -n -i "password|secret|token|access.key" live_validation/README.md .github/PULL_REQUEST_TEMPLATE/live-redshift-validation.md
git diff --check
```

Inspect every match and confirm it is an instruction or redaction warning, not a credential.

Commit: `git commit -am "docs: add live Redshift release runbook"` after staging new files.

### Task 7: AWS-Free CI, Final Verification, and Stacked PR Recording

**Files:**
- Create: `.github/workflows/live-validation-contract.yml`
- Modify: `docs/superpowers/plans/2026-08-30-redshift-live-validation.md`
- Modify: PR #9 and tracking PR #1; do not create temporary PR-body files.

**Interfaces:**
- Consumes: complete isolated project and Django contract tests.
- Produces: blocking AWS-free synthesis/contract checks and a reviewable stacked PR ready for the later human AWS run.

- [ ] **Step 1: Add the AWS-free workflow**

Use `actions/checkout@v6` and `astral-sh/setup-uv@v7` with Python 3.12. Run exactly:

```yaml
- run: uv sync --project live_validation --locked --all-groups
- run: uv run --project live_validation pytest live_validation/tests -q
- run: uv run --project live_validation ruff check live_validation
- run: uv run --with pytest pytest tests/test_live_validation_contract.py -q
```

Do not add AWS credentials, OIDC permissions, environment secrets, deploy, or destroy steps.

- [ ] **Step 2: Run final local verification**

Run:

```powershell
uv sync --project live_validation --locked --all-groups
uv run --project live_validation pytest live_validation/tests -q
uv run --project live_validation ruff check live_validation
uv run --with pytest pytest tests/test_live_validation_contract.py -q
uv run --only-dev tox -v
uv build
uv run --only-dev twine check dist/*
git diff --check
git status --short
```

Expected: all tests, lint, package checks, and diff checks pass; status contains only the plan checkbox/result updates before the final commit.

- [ ] **Step 3: Record measured results in this plan and commit**

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

Report the exact reviewed operator command sequence. A human must separately choose the AWS account/Region, confirm current pricing and permissions, set the fixed environment values, run plain `cdk deploy`, run validation, run plain `cdk destroy`, remove `cdk.out/`, and clear the password variables. Repository implementation completion does not authorize or imply an AWS deployment.
