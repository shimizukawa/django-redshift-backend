# Connector 2.2.0 differential integration evidence

## Environment and outcome

Executed on 2026-10-17 against the human-deployed disposable Redshift Serverless
environment in ap-northeast-1, using the activated backend.
Both examples used Python 3.12.15, Django 6.1.1, and explicitly selected
`redshift-connector==2.2.0`; django-sql-explorer was 5.3. No production backend
change was required. The earlier 2.1.16 evidence remains valid for its version.

The application and controlled TLS differential checks passed. The human ran
`cdk destroy` on 2026-10-17, and post-destroy absence verification completed.

## Execution

Each example used a separate temporary uv environment; its backend dependency
was the editable repository checkout. `--with redshift-connector==2.2.0`
selected the driver explicitly. Example locks were left unchanged.

Temporary Python probes initialized each example's existing `config.settings`
and invoked Django management commands with `call_command`. Commands had this
shape from the repository root:

```powershell
uv run --project examples/proj1 --frozen --python 3.12 --with redshift-connector==2.2.0 python _redshift_220_probe.py proj1 STAGE
uv run --project examples/dj-sql-explorer --frozen --python 3.12 --with redshift-connector==2.2.0 python _redshift_220_probe.py dj-sql-explorer STAGE
```

`STAGE` was `check`, `migrate`, `probe`, or `inspectdb`; Explorer additionally
used `explorer-migrate` and `explorer-query`. The credential-aware temporary
probe was removed after execution; it is not a supported validation command.
Settings were loaded from the existing ignored Explorer `.env` through
`ENV_FILE` for proj1. Initially its old password failed authentication, so the
current locally synthesized CDK settings were used only in memory. After the
human updated `.env`, subsequent probes used and verified the updated values.
No passwords, connection URLs, or encrypted credential values were logged.

## Results

| Check | proj1 | dj-sql-explorer |
| --- | --- | --- |
| Django system check | pass | pass |
| Migration state | standard Django migrations applied | through explorer 0028, with limitations below |
| TLS with omitted mode, explicit verify-full, explicit verify-ca | TLS 1.3, verified server certificate, SELECT 1 passed for all three | same |
| Repeated metadata on one connection | 3 matching rounds; 10 tables at that point | 3 matching rounds; 17 tables after Explorer migrations |
| Metadata content | auth_group discovered; id/name columns and PK present | same |
| ORM | Group create/read/update/delete passed; cleanup confirmed | same |
| inspectdb auth_group | unmanaged AuthGroup generated | same |
| Encrypted VARBYTE fields | not applicable | host/user/password write/read/decrypt round trip passed |
| Logged SQL execution | not applicable | Query.execute_with_logging(None) returned [[1]], successful QueryLog persisted |
| Probe records | removed | query, log, encrypted dummy connection, and Group records removed |

Metadata rounds called `get_table_list`, `get_table_description`, and
`get_constraints` repeatedly with the same Django connection/cursor and
compared their results. TLS diagnostics inspected the underlying live
`ssl.SSLSocket` for its protocol and verified peer certificate; these private
diagnostic observations are not a new public backend dependency.

### Existing Explorer limitations and configuration change

For 0018 and 0028, the affected DatabaseConnection/PromptLog tables were
confirmed empty before recreation from the target historical migration state
and fake application, followed by the normal remaining migrations. No
data-preserving table-rebuild support is claimed; upstream issue #189 remains.

The human updated `.env` while migrations were running. The migration-created
default Django connection alias had an encrypted empty host signed with the
previous settings key, and reading it with the updated key raised BadSignature.
Fresh encrypted-field writes with the updated settings passed. For this
session-created default alias (id 1), the engine/alias were checked and SQL
confirmed user/password were NULL before re-encrypting only the known empty
host under the current key. Full model retrieval then passed. No existing
populated credential record was changed. This was a settings-key transition,
not a connector 2.2.0 conversion failure.

## Controlled TLS checks

The companion `2026-10-17-redshift-connector-2.2.0-tls-probe.py` uses a loopback
PostgreSQL SSL-negotiation endpoint and an ephemeral localhost certificate.
For trusted cases only, it adds that certificate to the client's trust store
after loading the driver's normal roots. Driver hostname checking is not
mocked. The endpoint sends a sentinel error after receiving the encrypted
startup packet, so a TLS pass means it reached startup, not authentication.

| Certificate / hostname | omitted | verify-full | verify-ca |
| --- | --- | --- | --- |
| trusted / matches | TLS pass, no mismatch warning | TLS pass | TLS pass |
| trusted / mismatches | TLS pass, mismatch warning captured | rejected | TLS pass |
| untrusted / matches | rejected | rejected | rejected |

All nine cases passed; expected certificate rejection may reset the server-side
socket on Windows. The script handles this and asserts the observed outcome.
Temporary certificates and keys are removed by its temporary-directory scope.
This complements the actual AWS endpoint checks; it does not reconfigure AWS
certificates, trust roots, or hostname verification.

## Cleanup verified

After the human ran `cdk destroy` on 2026-10-17, the first AWS checks found the
workgroup absent, no matching snapshots, and stack/namespace deletion in
progress. Subsequent checks confirmed the CloudFormation stack and namespace
were also absent. No additional resource deletion was initiated by the agent.

The generated `examples/cdk/cdk.out` assembly containing the temporary password
was removed. The human-maintained ignored Explorer `.env` was preserved; its
connection settings now refer to the deleted validation environment. Temporary
credential-aware probe scripts were removed, and both example lockfiles were
unchanged.
