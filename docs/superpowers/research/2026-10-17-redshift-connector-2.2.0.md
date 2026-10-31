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

## Verification requirements

The public DB-API, connection and cursor signatures, exception mapping, and
password-only settings contracts must hold for 2.2.0. The supported-version
matrix includes a blocking connector 2.2.0 cell alongside the driver floor.
Per-run results are recorded in the PR discussion.

Real-Redshift validation must cover TLS connection, ORM round trips, repeated
metadata calls, and `inspectdb`. Controlled TLS checks must cover hostname
mismatch and untrusted certificates. The live-validation layer documents the
operator procedure and version-qualified integration evidence separately.
