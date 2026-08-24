# AWS Redshift Connector Investigation

## Decision

Decision: GO

Scope: username/password authentication only.

The public, AWS-free contracts required for a password-only backend layer pass
on both the 2.1.14 security floor and the investigated 2.1.16 release. All 15
cells in the proposed blocking compatibility matrix also passed when reproduced
locally. The next layer may therefore adopt the public connector API with
`redshift-connector>=2.1.14,<3`, without a psycopg2 adapter or a private driver
API, provided the initial release accepts only non-empty Django `USER` and
`PASSWORD`. IAM, profile, provisioned/Serverless IAM, and IdP/provider
authentication are explicitly deferred and unsupported. The stacked PR must
still pass the same matrix on GitHub Actions before it is merged.

## Candidate and proposed constraint

- Investigated release: 2.1.16, released on 2026-08-03.
- Security floor: 2.1.14, released on 2026-05-18 and containing the fix for
  [GHSA-29h4-r29x-hchv](https://github.com/advisories/GHSA-29h4-r29x-hchv).
- Proposed runtime constraint: `redshift-connector>=2.1.14,<3`.
- The 2.1.16 wheel declares `Requires-Python >=3.8`. The project matrix covers
  its supported Python 3.10-3.14 range, with Django's own Python-version bounds
  applied.

## Maintenance, license, security, and dependencies

The upstream changelog and PyPI history show continued activity: 2.1.14 was
released on 2026-05-18, 2.1.15 on 2026-06-09, and 2.1.16 on 2026-08-03. As of
2026-08-23, 2.1.16 is the latest published release.

The locked 2.1.16 wheel has SHA-256
`6d50ef7c19bf48e0895f8e81636f182bd8d0f3b447f02e9c924e9c52ca8e2cb6`.
Its core metadata says `License: Apache License 2.0`, but its classifier says
`License :: OSI Approved :: BSD License`. Direct inspection of the wheel's
packaged files resolves the substantive license as Apache License 2.0:
`licenses/LICENSE` contains the complete Apache License, Version 2.0 text, and
`licenses/NOTICE` contains Amazon's copyright notice. The BSD classifier is
inconsistent/stale metadata, not a second license in the distribution. This
discrepancy does not block adoption, but should be reported upstream.

The locked distribution has these direct runtime dependencies:

- `beautifulsoup4>=4.13.5,<5.0.0`
- `boto3>=1.42.22,<2.0.0`
- `botocore>=1.12.201,<2.0.0`
- `lxml>=6.1.0,<7.0.0`
- `packaging`
- `pytz>=2020.1`
- `requests>=2.23.0,<3.0.0`
- `scramp>=1.2.0,<1.5.0`
- `setuptools`

`numpy` and `pandas` are declared only for the `full` extra and are not direct
dependencies of the default installation.

The checked-in `driver_tests/uv.lock` resolves 29 distributions for the complete
investigation harness (project, pytest tooling, and runtime dependencies). To
measure the production dependency rather than the test harness, fresh Python
3.12.13 environments were installed from the public index with only one pinned
requirement. Both `redshift-connector==2.1.14` and `==2.1.16` resolved to 21
distributions: the connector plus 20 unique transitive distributions. The
logical size of all files under `site-packages` was 39,152,756 bytes (37.34 MiB)
for 2.1.14 and 39,166,415 bytes (37.35 MiB) for 2.1.16 on Windows x86-64.
These are installed logical sizes, not download, compressed-wheel, or shared uv
cache sizes, and other platforms can differ.

`uv pip check` reported all 21 packages compatible in both isolated runtime
environments. The 15 matrix runs also resolved without a dependency conflict;
their complete test environments contained 28 installed packages on Python
3.10 and 26 on Python 3.11-3.14. This establishes satisfiable resolutions for
the proposed Python/Django matrix at the time of investigation, not a guarantee
against future releases under open transitive constraints.

`pip-audit` reported no known vulnerabilities in either isolated 21-package
runtime environment on 2026-08-23. The audit queried the resolved Windows
Python 3.12 package sets; it does not cover future resolutions, optional extras,
operating-system libraries, or vulnerabilities absent from the audit database.

The reviewed security advisories establish both relevant floors:

- [GHSA-r244-wg5g-6w2r](https://github.com/advisories/GHSA-r244-wg5g-6w2r)
  affects 2.0.872 through 2.1.6 and is fixed in 2.1.7.
- [GHSA-29h4-r29x-hchv](https://github.com/advisories/GHSA-29h4-r29x-hchv)
  affects versions through 2.1.13 and is fixed in 2.1.14. This critical fix is
  why 2.1.14, rather than 2.1.7, is the proposed minimum.

## Must-pass public contracts

All must-pass contracts succeeded on public objects imported from
`redshift_connector`:

- DB-API level is `2.0`, the default parameter style is `format`, and thread
  safety is level 1.
- The complete DB-API/Django exception namespace is present: `Error`,
  `InterfaceError`, `DatabaseError`, `DataError`, `OperationalError`,
  `IntegrityError`, `InternalError`, `ProgrammingError`, and
  `NotSupportedError`. Django's public `DatabaseErrorWrapper` translates all
  nine names without an adapter.
- The public `connect()` signature exposes the `user` and `password` arguments
  needed by the initial scope. Only password-scope arguments are a must-pass
  signature contract; alternate-authentication arguments are inventory for
  future work, not a CI GO gate.
- Public synchronous `Connection` methods cover `cursor()`, `commit()`,
  `rollback()`, `close()`, and context management. Public `Cursor` methods and
  properties cover `execute()`, `executemany()`, fetch methods, `close()`,
  context management, `description`, and `rowcount` on both investigated
  versions.
- The investigation harness imports only the public package and public classes.
  The production backend is unchanged, and no private driver member or
  psycopg2 compatibility adapter is required by these contracts.
- Every one of the 15 AWS-free compatibility-matrix cells passed locally at
  91 tests per cell; 14 exercise the 2.1.14 floor and the final smoke cell
  exercises 2.1.16.

## Connection option crosswalk

- Non-empty standard Django settings `NAME`, `HOST`, and `PORT` map to
  `database`, `host`, and `port` and override duplicate names supplied in
  `OPTIONS`.
- Django `USER` and `PASSWORD` map to public driver `user` and `password`.
  Both must be non-empty before any connector or socket use; duplicate `user`
  or `password` values in `OPTIONS` are overwritten by the Django settings.
- Any authentication or IdP option in the deferred inventory below is rejected
  based on key presence, including false or empty-looking values, with a clear
  username/password-only error before connector or socket use.
- An option is passed to the driver only if it is in the public `connect()`
  signature.
- `passfile`, `service`, `sslrootcert`, `sslcert`, and `sslkey` are retained
  only for `dbshell`. Driver-side `sslmode` accepts exactly the two values in
  the AWS connector documentation, `verify-ca` and `verify-full`.
- The independent `dbshell` classifier preserves psql's `disable`, `allow`,
  `prefer`, `require`, `verify-ca`, and `verify-full` values. A database
  connection configured with one of the first four legacy modes is rejected
  before a socket is opened; it is not silently translated or dropped. This is
  an intentional compatibility impact, while direct dbshell construction can
  still retain the original psql value.
- Legacy psycopg2-only options `options`, `isolation_level`, `cursor_factory`,
  `connection_factory`, and `client_encoding` are rejected.
- Any other unknown option fails during classification, before a socket can be
  opened.
- Logging redacts all values named `password`, `access_key_id`,
  `secret_access_key`, `session_token`, `client_secret`,
  `web_identity_token`, or `token`.

## Deferred authentication inventory

Both investigated public `connect()` signatures expose the same authentication
and IdP-specific option inventory. The initial release does not construct or
validate these modes. Instead, its bounded denylist rejects all 45 names:

`access_key_id`, `allow_db_user_override`, `app_id`, `app_name`, `auth_profile`,
`auto_create`, `client_id`, `client_secret`, `cluster_identifier`,
`credentials_provider`, `db_groups`, `db_user`, `endpoint_url`,
`force_lowercase`, `group_federation`, `iam`, `iam_disable_cache`,
`identity_namespace`, `idc_client_display_name`, `idc_region`, `idp_host`,
`idp_partition`, `idp_response_timeout`, `idp_tenant`, `is_serverless`,
`issuer_url`, `listen_port`, `login_to_rp`, `login_url`, `partner_sp_id`,
`preferred_role`, `principal_arn`, `profile`, `provider_name`, `role_arn`,
`role_session_name`, `scope`, `secret_access_key`, `serverless_acct_id`,
`serverless_work_group`, `session_token`, `ssl_insecure`, `token`, `token_type`,
and `web_identity_token`.

This inventory is non-blocking evidence for future design. It is not a claim
that IAM, profile, provisioned IAM, Serverless, SAML, Identity Center, Okta, or
any other `credentials_provider` works. `region` and generic transport,
protocol, metadata, and numeric-conversion options remain ordinary public
driver options because they do not select an authentication mode by themselves.

## Explicit limitations and deferred integration checks

`Connection.cursor()` has no public named-cursor argument. Django chunked
cursors must initially use an ordinary cursor or be explicitly marked
unsupported.

The following behavior remains unverified until a real Redshift service is
available: parameter binding; round trips for UUID, Decimal, date, time,
datetime, timezone, Boolean, JSON, NULL, Redshift-specific, and unknown types;
savepoint SQL; actual `execute()`, `executemany()`, fetch, and result-metadata
behavior; connection health after a network failure; and `CONN_MAX_AGE`.
IAM, profile, provisioned-cluster IAM, Serverless, SAML, Identity Center, Okta,
and every other provider mode are not merely unverified: they are unsupported
in the initial release and must be addressed by future design and real-Redshift
integration work before their denylist entries can be removed.

AWS's public examples state that autocommit is off by default and demonstrate
setting `Connection.autocommit`. They also demonstrate connection and cursor
context managers. The public surface exists in both investigated driver
versions, but these behaviors were not integration-tested here.

## Commands and results

All successful local commands used a workspace-local uv cache because the
sandbox could not access uv's default host cache. Python 3.12 resolved to
3.12.13, Python 3.10 to 3.10.20, Python 3.11 to 3.11.14, Python 3.13 to 3.13.3,
and Python 3.14 to 3.14.0. `Django~=6.0.0` resolved to 6.0.8 and
`Django~=6.1.0` to 6.1.

Task-specific public contract commands:

```text
uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with redshift-connector==2.1.16 pytest driver_tests/test_metadata_contract.py -q
PASS: Python 3.12.13, driver 2.1.16, 5 passed

uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with redshift-connector==2.1.14 pytest driver_tests/test_metadata_contract.py -q
PASS: Python 3.12.13, driver 2.1.14, 5 passed

uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with redshift-connector==2.1.14 pytest driver_tests/test_connect_options.py -q
PASS: Python 3.12.13, driver 2.1.14, 74 passed

uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with redshift-connector==2.1.16 pytest driver_tests/test_connect_options.py -q
PASS: Python 3.12.13, driver 2.1.16, 74 passed

uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with Django==4.2.30 pytest driver_tests/test_django_exceptions.py -q
PASS: Python 3.12.13, Django 4.2.30, locked driver 2.1.16, 9 passed

uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with Django==5.2.8 pytest driver_tests/test_django_exceptions.py -q
PASS: Python 3.12.13, Django 5.2.8, locked driver 2.1.16, 9 passed

uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with "Django~=6.0.0" pytest driver_tests/test_django_exceptions.py -q
PASS: Python 3.12.13, Django 6.0.8, locked driver 2.1.16, 9 passed

uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with "Django~=6.1.0" pytest driver_tests/test_django_exceptions.py -q
PASS: Python 3.12.13, Django 6.1, locked driver 2.1.16, 9 passed

uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with redshift-connector==2.1.14 pytest driver_tests/test_connection_cursor_contract.py -q
PASS: Python 3.12.13, driver 2.1.14, 3 passed

uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with redshift-connector==2.1.16 pytest driver_tests/test_connection_cursor_contract.py -q
PASS: Python 3.12.13, driver 2.1.16, 3 passed
```

Fresh current matrix representative commands:

```text
uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with Django==4.2.30 --with redshift-connector==2.1.14 pytest driver_tests -q
PASS: Python 3.12.13, Django 4.2.30, driver 2.1.14, 91 passed

uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with Django==5.2.8 --with redshift-connector==2.1.14 pytest driver_tests -q
PASS: Python 3.12.13, Django 5.2.8, driver 2.1.14, 91 passed

uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with "Django~=6.0.0" --with redshift-connector==2.1.14 pytest driver_tests -q
PASS: Python 3.12.13, Django 6.0.8, driver 2.1.14, 91 passed

uv --cache-dir .uv-cache run --python 3.14 --project driver_tests --with "Django~=6.1.0" --with redshift-connector==2.1.16 pytest driver_tests -q
PASS: Python 3.14.0, Django 6.1, driver 2.1.16, 91 passed
```

The complete workflow matrix was then reproduced with this exact command,
substituting each row below:

```text
uv --cache-dir .uv-cache run --python PYTHON --project driver_tests --with "DJANGO" --with redshift-connector==DRIVER pytest driver_tests -q
```

| Python | Django requirement (resolved) | Driver | Result |
| --- | --- | --- | --- |
| 3.10 | `Django==4.2.30` (4.2.30) | 2.1.14 | 91 passed |
| 3.11 | `Django==4.2.30` (4.2.30) | 2.1.14 | 91 passed |
| 3.12 | `Django==4.2.30` (4.2.30) | 2.1.14 | 91 passed |
| 3.10 | `Django==5.2.8` (5.2.8) | 2.1.14 | 91 passed |
| 3.11 | `Django==5.2.8` (5.2.8) | 2.1.14 | 91 passed |
| 3.12 | `Django==5.2.8` (5.2.8) | 2.1.14 | 91 passed |
| 3.13 | `Django==5.2.8` (5.2.8) | 2.1.14 | 91 passed |
| 3.14 | `Django==5.2.8` (5.2.8) | 2.1.14 | 91 passed |
| 3.12 | `Django~=6.0.0` (6.0.8) | 2.1.14 | 91 passed |
| 3.13 | `Django~=6.0.0` (6.0.8) | 2.1.14 | 91 passed |
| 3.14 | `Django~=6.0.0` (6.0.8) | 2.1.14 | 91 passed |
| 3.12 | `Django~=6.1.0` (6.1) | 2.1.14 | 91 passed |
| 3.13 | `Django~=6.1.0` (6.1) | 2.1.14 | 91 passed |
| 3.14 | `Django~=6.1.0` (6.1) | 2.1.14 | 91 passed |
| 3.14 | `Django~=6.1.0` (6.1) | 2.1.16 | 91 passed |

This fresh matrix uses the expanded password-only suite and supersedes the
historical 48-test matrix evidence. Each cell used an isolated uv project
environment, matching CI job isolation. The focused password-only option suite
passed 74 tests on each of 2.1.14 and 2.1.16, and the complete AWS-free driver
suite passed 91 tests on both connector endpoints with Django 5.2.8.

Dependency and packaging evidence commands:

```text
uv --cache-dir .uv-cache tree --project driver_tests --locked
PASS: 29-package locked investigation graph; connector 2.1.16 plus 20 unique
runtime transitives and the project/pytest harness

uv ... venv --python 3.12 RUNTIME_ENV
uv ... pip install --python RUNTIME_ENV redshift-connector==DRIVER
uv ... pip check --python RUNTIME_ENV
PASS for 2.1.14 and 2.1.16: 21 packages resolved and installed; all compatible

pip-audit --path RUNTIME_ENV/Lib/site-packages
PASS for both isolated runtime environments: no known vulnerabilities found

uv --cache-dir .uv-cache run --with pytest --with pytest-cov --with mock --with django-environ --with psycopg2-binary pytest -q
PASS: editable root build succeeded; 10 passed, 22 skipped

uv --cache-dir .uv-cache build --out-dir PACKAGE_ARTIFACTS
PASS: sdist built. The direct wheel build then hit the Windows long-path limit
in the nested worktree; rebuilding that exact sdist from C:\\tmp\\drb168 succeeded.
The wheel contains 33 files: 28 under django_redshift_backend, zero under
driver_tests, and only the production package plus dist-info at top level.
The sdist contains the tracked investigation sources, while its generated
top_level.txt names only django_redshift_backend.
```

## Sources

- [AWS Python connector API reference](https://docs.aws.amazon.com/redshift/latest/mgmt/python-api-reference.html)
- [AWS connector configuration options](https://docs.aws.amazon.com/redshift/latest/mgmt/python-configuration-options.html)
- [AWS connector examples, including autocommit and context managers](https://docs.aws.amazon.com/redshift/latest/mgmt/python-connect-examples.html)
- [AWS Python connector identity-provider examples](https://docs.aws.amazon.com/redshift/latest/mgmt/python-connect-identity-provider-plugins.html)
- [AWS Identity Center direct-token integration](https://docs.aws.amazon.com/redshift/latest/mgmt/identity-center-authentication.html)
- [Official AWS driver repository](https://github.com/aws/amazon-redshift-python-driver)
- [Official AWS driver changelog](https://github.com/aws/amazon-redshift-python-driver/blob/master/CHANGELOG.md)
- [Official AWS driver releases](https://github.com/aws/amazon-redshift-python-driver/releases)
- [PyPI release metadata and history](https://pypi.org/project/redshift-connector/)
- [GHSA-r244-wg5g-6w2r](https://github.com/advisories/GHSA-r244-wg5g-6w2r)
- [GHSA-29h4-r29x-hchv](https://github.com/advisories/GHSA-29h4-r29x-hchv)
