# Connector 2.2.0 compatibility follow-up

## Decision and scope

Retain the username/password GO decision and runtime requirement
`redshift-connector>=2.1.14,<3`. This follow-up adds evidence for 2.2.0;
it does not replace the original 2.1.14/2.1.16 investigation or its live results.

## Upstream changes

- 2.1.17 improves metadata API performance and fixes repeated metadata calls
  on the same connection. It also adds an opt-in credential-plugin allowlist.
  Alternate authentication remains outside this backend's supported scope.
- 2.2.0 changes the default TLS mode from `verify-ca` to `verify-full`.
  When omitted, hostname mismatch warns but connects during the transition;
  explicit `verify-full` rejects a mismatch. Certificate-chain verification
  still applies. The backend continues to delegate an omitted mode to the
  driver, rather than restoring the older default.
- Installed 2.2.0 metadata requires `boto3>=1.42.22,<2.0.0` and
  `lxml>=6.1.0,<7.0.0`. Its other runtime requirements are scramp, pytz,
  beautifulsoup4, requests, botocore, packaging, and setuptools; numpy/pandas
  remain optional `full` extras. This is not a new dependency audit or a
  replacement for the older dependency-size measurements.

Source: [AWS changelog](https://github.com/aws/amazon-redshift-python-driver/blob/master/CHANGELOG.md)
and the installed 2.2.0 wheel's `importlib.metadata.requires()` output.

## AWS-free verification

Executed on Windows with Python 3.12.15 and Django 5.2.8:

```powershell
uv run --project driver_tests --python 3.12 --with Django==5.2.8 --with redshift-connector==2.2.0 pytest driver_tests -q
```

- PR #2 layer: 91 passed. Public DB-API, cursor/metadata signatures,
  username/password option mapping, and existing authentication rejections pass.
- Complete stack before this follow-up: 381 passed, 2 skipped.
- CI retains all 15 original cells and adds a blocking Python 3.12 / Django
  5.2.8 / connector 2.2.0 cell, which runs each PR's complete driver suite.

The installed public `connect()` signature still exposes the required
password-connection parameters. No production change was needed for the
AWS-free contracts exercised here.

## Remaining integration evidence

The existing real-Redshift evidence applies to its recorded driver version,
not automatically to 2.2.0. A human-operated CDK session must still check
TLS connection, ORM round trips, repeated metadata calls, and `inspectdb`
with 2.2.0. Controlled TLS hostname-mismatch and untrusted-certificate cases
also remain pending. See the differential-validation section in
`examples/cdk/README.md` in the live-validation layer. No AWS resources were
created for this follow-up's offline checks.
