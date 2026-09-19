# Redshift Live Validation Environment Design

## Status

Approved for implementation on 2026-08-30. Implementation is release-gate work
that follows the redesigned backend stack. It does not expand the initial
authentication scope beyond username/password.

## Purpose

The unit and contract suites prove Django and driver behavior without AWS, but
they cannot prove that the selected driver, generated Redshift SQL, network
configuration, and `examples/proj1` operate together. Before releasing 6.0.0,
maintainers must run a reproducible, disposable validation against a real
Amazon Redshift Serverless workgroup.

This repository provides the infrastructure definition and operator commands;
it never creates AWS resources from ordinary CI or from an application test.

## Goals

- Create and destroy an isolated Redshift Serverless environment with CDK.
- Keep compute, network, and database resources ephemeral and prevent
  unattended cost.
- Permit only the machine executing the validation to reach the public
  endpoint, even when that machine has a dynamic public IP address.
- Run the existing `examples/proj1` application as the primary live validation
  target, including Django migration and the existing SQL migration checks.
- Preserve normal CI as AWS-free; real validation is an explicit manual
  release gate.

## Non-goals

- A permanent development, staging, or production Redshift environment.
- GitHub Actions access to the live environment.
- IAM, browser SSO, or other non-password Redshift authentication modes.
- An unrestricted public endpoint, NAT gateway, or a shared VPC platform.
- Converting `examples/dj-sql-explorer` into a required release gate. It may
  later be run as an additional manual smoke test.

## Deployment Architecture

The CDK application is a Python project managed with `uv`. Its `cdk.json`
defines the Python app command, so the operator runs plain `cdk deploy` from
`examples/cdk/`. It defines one CloudFormation stack using CDK's standard
AWS account and Region environment plus fixed process environment variables
for the temporary password, owner, and expiration date. It creates:

1. A dedicated VPC with an internet gateway and three public subnets in
   distinct Availability Zones. It has no NAT gateway and no private workload
   resources.
2. A dedicated security group. Its sole ingress rule is TCP port 5439 from
   `allowed_cidr`; egress uses the VPC default needed by the managed service.
3. A Redshift Serverless namespace and a workgroup associated with that VPC,
   the three subnets, and the dedicated security group. The workgroup is
   publicly accessible, uses the lowest capacity supported in the selected
   Region, has a conservative maximum capacity, and has a daily RPU-hour usage
   limit whose action turns off user queries.

The Python CDK application determines the caller's current public IPv4 address
at synthesis time and converts it to `<address>/32`. A changed ISP address is
handled by rerunning `cdk deploy`, which updates only the security-group rule.
The CDK source must reject a non-single-host CIDR and must never default to
`0.0.0.0/0`.

The Python CDK application reads the required admin password from the fixed
`DB_PASSWORD` process environment variable and passes it to the
namespace as `AdminUserPassword`; it does not use CDK context, a CloudFormation
parameter, or Secrets Manager. The same shell value is passed to the Django
validation process. The stack outputs only endpoint address, port, database
name, admin username, workgroup name, namespace name, and the accepted CIDR. It
never outputs the password.

Because a synth-time environment value appears in the local synthesized
CloudFormation assembly, `examples/cdk/cdk.out/` is ignored and treated as
sensitive temporary data. The operator removes it and clears the environment
variable after every session. The password must never be committed, included
in a PR artifact, or copied into a command-line argument.

CDK requires one per-account/Region bootstrap stack (`CDKToolkit`). That is an
intentional one-time prerequisite and is outside the disposable validation
stack. The documentation identifies its retained S3/ECR/IAM resources. VPC
Block Public Access must permit this dedicated VPC to host a public workgroup;
the documentation explains that `cdk deploy` fails when account or Region
policy prevents public access and how to inspect that policy. The application
never weakens account policy automatically.

## Lifecycle

The documented operator flow is:

1. Configure AWS credentials and bootstrap the target account/Region once.
2. Set the documented fixed environment variables and run `cdk deploy` from
   `examples/cdk/`; `cdk.json` selects the Python application, which resolves
   the current IP and deploys through normal CDK behavior.
3. Export non-secret connection settings from stack outputs and pass the same
   local password environment value to the Django validation process.
4. Run the live-validation command against `examples/proj1`.
5. On success or failure, run `cdk destroy`. Then run the documented AWS CLI
   read-only checks to verify that the workgroup and namespace are no longer
   present. No manual snapshot is created.

The namespace is deleted as well as the workgroup. Deleting only the
workgroup leaves storage-bearing namespace resources behind.

## Live Validation Contract

The validation runner receives standard Django database settings through
environment variables: `NAME`, `HOST`, `PORT`, `USER`, and `DB_PASSWORD`. A
dedicated validation settings module maps those variables directly into
`DATABASES["default"]` with `ENGINE=django_redshift_backend` and TLS enabled;
it does not rely on `examples/proj1`'s development `DATABASE_URL` convention or
introduce special test-only backend options.

Against `examples/proj1`, it must:

- check that Django can establish a TLS-protected password connection;
- run `manage.py migrate` on the empty, dedicated namespace database;
- run the repository's existing migration SQL checks, including the reusable
  `sqlmigrate` coverage, against the live connection where that command needs
  database access;
- execute a small ORM smoke path that creates, reads, updates, and deletes a
  representative model; and
- report the exact commands, package revision, Django version, driver version,
  Redshift Region, and sanitized endpoint metadata needed to record the result
  in the release PR.

The runner creates data only in the disposable namespace and must leave no
credentials in console output, logs, or committed files. It has a cleanup trap
for application-level objects but does not conceal a failed infrastructure
cleanup: the operator must see a clear destroy instruction and status.

## Safety and Cost Controls

- No inbound `0.0.0.0/0` rule is permitted.
- The only public port is 5439, restricted to the deployer's dynamic `/32`.
- TLS is required by the live-validation settings.
- No NAT gateway, operator-managed Elastic IP, VPC endpoint, manual snapshot,
  or persistent database resource is created by this stack. Redshift's
  service-managed public address for the explicitly public workgroup is
  expected and remains protected by the single-host security-group rule.
- The workgroup has both a maximum capacity and a daily RPU-hour cutoff that
  disables user queries.
- Every resource has `Purpose=django-redshift-backend-live-validation`, plus
  owner and expiration tags supplied by the operator.
- Each public subnet has enough free addresses for the Serverless workgroup;
  synthesis tests pin the subnet topology and address ranges.
- The README documents that `cdk destroy` must run after every session, how to
  remove the sensitive local `cdk.out/` assembly and password environment
  variable, and how to check for retained CloudFormation, Redshift, and
  snapshot resources.

## Tests and Evidence

AWS-free tests validate CDK synthesis with injected environment and IP lookup
values rather than contacting AWS. They assert
the number and topology of VPC subnets, no NAT gateway, the constrained
security-group rule, Serverless resource properties, outputs excluding secrets,
and deletion dependency order.

The existing backend test suite remains mandatory. The release PR adds a
manual checklist template for the live run and records each run's sanitized
result. A successful real-Redshift run is a release criterion for 6.0.0;
failure blocks the release until the defect is fixed or the release scope is
explicitly reconsidered.

## Delivery

The work is delivered in a new stacked branch based on
`redesign/06-activate-cleanup-release`, following the established branch
strategy. Its pull request is the real-integration validation PR and includes
the infrastructure source, local commands, AWS-free synthesis tests, and the
manual release checklist. No existing backend behavior or user database schema
is changed by this work.
