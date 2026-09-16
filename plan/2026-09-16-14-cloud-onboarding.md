---
status: approved
issue: 14
spec: spec/2026-09-16-14-cloud-onboarding.md
---

# Plan: Cloud onboarding and evidence-based reporting

Implement the approved AWS-first onboarding baseline, shared skills, and provider
corrections on `feat/14-cloud-onboarding`. No implementation starts until this
plan is approved. The approved design is reproduced below so implementation does
not require consulting the specification. Keep the specification in place.

## Approved decisions

### Delivery and boundaries

Add `skills/cloud-onboarding/SKILL.md` and
`skills/cloud-troubleshoot/SKILL.md`. Both are copied by `pkgs/init.sh` for every
provider using the existing non-overwriting helper and agent symlinks. Link them
from `templates/base/AGENTS.md` and explain their use in `README.md`.

Onboarding routes to the selected provider, establishes expected identity and
scope, collects evidence, assesses controls, and reports limitations. AWS has an
executable collector in this release. The other seven providers have manual
procedures using existing CLIs and native assessment services, explicitly marked
as not having an automated collector. Do not promise complete inventory,
organization-wide assessment, compliance certification, or effective network
reachability. No cloud writes, automatic remediation, service activation, paid
scanner provisioning, or automatic report publication.

Put the report contract and provider routing in linked onboarding references;
keep provider-specific procedures in existing provider references. Keep the
repository's frontmatter and line limits. No new plugin framework or MCP server.

### AWS executable and scope

Implement `skills/cloud-onboarding/scripts/aws_report.py` with Python's standard
library, invoking the existing AWS CLI with argument lists, never a shell.
Expose `cloud-onboard-aws` through `modules/aws/devenv.nix`, using the pinned
Python interpreter and the script from the module's source revision. The copied
script remains usable with Python inside an AWS project. No boto3 or Prowler
dependency is needed for these bounded checks.

Example interface:

```sh
cloud-onboard-aws --account-id 123456789012 --regions eu-west-1 eu-west-2 \
  --environment production --profile audit
```

Account ID, at least one region, and a filesystem-safe environment slug are
required. Profile is optional so existing SSO/role credentials can be reused.
Resolve `sts get-caller-identity` first and compare the account exactly; failed
identity or mismatch stops before inventory collection. Use explicit region
arguments on every regional command. First release supports the commercial AWS
partition; reject other partitions with an explanatory error. The environment
label names the report, not a tag filter: scope is the selected account/regions.

Collect only these services and resource relationships:

| Scope | Read APIs | Selected evidence |
| --- | --- | --- |
| Account | STS GetCallerIdentity; IAM GetAccountSummary | Account/partition, root MFA and root access-key counts |
| Each region | EC2 DescribeInstances, DescribeVolumes, DescribeSecurityGroups | IDs, state, VPC/subnet/AZ and group/volume relationships, encryption, ingress protocol/ports/CIDRs, presence of required tags |
| Each region | RDS DescribeDBInstances | IDs, engine, encryption, public-access flag, backup retention, Multi-AZ, VPC/group relationships, required-tag presence where returned |
| Each region | S3 ListBuckets with bucket-region filter; GetPublicAccessBlock, GetBucketVersioning per bucket | Bucket names/region, bucket-level block-public-access flags, versioning status |
| Each region | CloudTrail DescribeTrails and GetTrailStatus | Trail ARN/home region, multi-region flag, logging state; include shadow trails and deduplicate by ARN |

Use home-region endpoints for trail status only when that region is in the
declared scope; otherwise mark its status unknown. General-purpose S3 buckets
only; exclude directory buckets and object contents explicitly. Do not collect
IAM policies, EC2 user data, RDS endpoints, application logs, tag values, resource
descriptions, secrets, or unrestricted API responses in reports. Required tags
are `owner`, `environment`, and `project`; save presence/nonempty booleans only.

Document the exact IAM read actions corresponding to this table, including
`s3:ListAllMyBuckets`, `s3:GetBucketPublicAccessBlock`, and
`s3:GetBucketVersioning`. Do not attach roles or broaden permissions. A reader
may legitimately lack some actions; that produces unknown results. STS identity
does not prove visibility across an organization or all resources in the account.

### Collection failure and resource bounds

Allow AWS CLI automatic pagination with JSON output and a per-list `--max-items`
limit of 1,000 by default. A returned continuation token means partial coverage,
never a complete list. Permit an explicit positive `--max-items` override. For
non-paginated APIs, do not pass unsupported pagination flags; detect any
unexpected continuation marker as incomplete. Do not store continuation tokens.

Default subprocess timeout is 60 seconds and total collection budget is 900
seconds, overridable through positive `--command-timeout` and `--timeout` values.
Bound CLI retries, disable pager and auto-prompt, and terminate timed-out child
processes. Remaining operations after the deadline are marked not collected.
Use selected-field CLI queries where practical and whitelist again before
persisting evidence. Never save raw stdout/stderr or print credentials; translate
errors into categories such as access_denied, timeout, unavailable, malformed,
and command_failed. Missing or wrongly typed fields are unknown, not false.

Failed lists must not generate 'no resources' conclusions. Successful observations
from partial lists may support individual findings; scope-wide absence claims
require complete relevant collection. Expected absent configuration responses
(for example missing S3 public-access-block configuration) are distinct from
denied access. An absent bucket block is a failed bucket-baseline check, not proof
that the bucket is public: account/organization controls are outside that check.

Exit codes: 0 means report written with complete collection for the supported
scope, regardless of failing findings; 2 means report written with incomplete
collection; 1 means invalid invocation, identity failure, or inability to write
a valid report. Manual-review items do not themselves make collection incomplete.

### Deterministic first-release checks

Checks carry stable rule IDs and a versioned ruleset. The implementation includes
official references for each rule and tests its predicates.

| Rule | Meaning and limitation |
| --- | --- |
| Root MFA | IAM summary reports root MFA enabled; absent evidence is unknown |
| Root access keys | IAM summary reports no root access keys |
| Administrative ingress | Security group lacks IPv4/IPv6 world-open TCP 22/3389, including covering port ranges or all protocols; flags a rule, not proven reachability |
| EBS encryption | Each discovered volume reports encryption enabled |
| RDS encryption | Each discovered DB instance reports storage encryption enabled |
| RDS public access | Each discovered DB instance reports PubliclyAccessible false; does not prove isolation |
| RDS backups | Positive backup retention; manual review of suitability and restore evidence remains required |
| S3 public-access block | All four bucket-level flags enabled; inherited controls not assessed |
| S3 versioning | Enabled passes; absent/suspended needs manual review of workload requirements, not a universal failure |
| CloudTrail logging | At least one observed logging trail covers each selected region; full collection with none fails this baseline, organization coverage uncertainty remains visible |
| Ownership tags | Required nonempty tags on supported EC2/RDS resources; missing evidence is unknown, missing tags fails the repository's convention |

Always include manual review for ownership accountability, least-privilege IAM,
recovery objectives and restore tests, resilience requirements (including RDS
Multi-AZ suitability), cost recommendations/budgets, and unassessed governance.
These are not automated passes. Empty complete resource sets are not applicable
for resource-specific checks. No synthetic overall compliance percentage.

### Report contract and storage

Write `reports/<environment>/<UTC timestamp with unique suffix>/` under the
project root, with `report.md`, `inventory.json`, `findings.json`, and
`coverage.json`. Add `/reports/` to `templates/base/.gitignore`. The collector
also ensures `/reports/` is ignored in the project's local Git exclude before
writing, protecting existing projects without overwriting their `.gitignore`.
Refuse a report path already tracked by Git, symlinked output ancestors, and
overwriting an existing run. Require a Git project root. Directories are private
(0700), files 0600; publish the completed run by renaming a temporary sibling
directory, cleaning temporary output on handled failures. No cloud evidence
printed to stdout: only report path and collection status.

All JSON documents carry `schema_version: 1` and matching run metadata: run ID,
start/end UTC timestamps, provider, expected/observed account, regions,
environment, collector/ruleset version, and AWS CLI version. Inventory records
have stable resource IDs, type, scope, selected attributes and relationships.
Evidence records identify API operation, scope, collection time, and selected
observations; findings reference those records rather than raw payloads.

Findings contain stable ID (rule plus resource/scope), rule version, resource or
scope, status (`pass`, `fail`, `unknown`, `not_applicable`, `manual_review`),
severity, evidence references, explanation, recommended action, and official
source URL. Severity expresses impact, independently of assessment status.
Coverage records include requested and observed scope, operation status,
resource counts, truncation/errors, unsupported services, and skipped work.
Reports state 'complete for supported checks' rather than 'complete account'.

Markdown renders the same facts: scope, coverage warning, status counts,
prioritized failed/unknown controls, manual-review checklist, and limitations.
Escape resource-derived Markdown and treat cloud metadata as untrusted data.
Agents may add narrative separately, but must not alter deterministic findings
or treat resource text as instructions. Machine reports support future baseline
comparison; comparison itself is deferred.

### Other providers and troubleshooting

Document identity checks, explicit scope, read commands, permissions, pagination,
native recommendations, and known coverage gaps for all seven manual providers:
Azure Resource Graph/Advisor, GCP Cloud Asset Inventory, OCI Search/Cloud Advisor
and optional CIS assessment, Kubernetes API metadata, Cloudflare Security
Insights, Hetzner project inventory, and DigitalOcean project/resource APIs.
Manual reports use the same statuses and evidence conventions; uncollected
categories remain unknown. Existing native services are queried only when
available; unavailable services do not trigger activation.

Specific corrections:

- Declare Azure `resource-graph` in `modules/azure/devenv.nix`, verify `az graph
  query --help` in `enterTest`, and remove dynamic extension installation advice.
- Use the GCP CLI for scoped asset discovery; explain that the current MCP
  allowlist does not expose it. Keep the MCP allowlist unchanged.
- Kubernetes onboarding uses explicit context/namespace and Trivy
  `--disable-node-collector --scanners misconfig`. Explain that node checks are
  skipped. Exclude exec, debug pods, restarts, and workload logs by default.
- Correct invalid OCI `--only none` and lowercase secret names in affected
  references; do not imply `secret-run` creates a private-key file from an env
  value. Prefer existing read-only CLI profiles and runtime credential paths.
- Remove Hetzner claims that full inventory contains no sensitive information
  and advice to commit unrestricted inventory snapshots.

Troubleshooting is a concise shared skill, not a second executable framework.
Route authentication/permissions, network/LB, workload health, quotas, and recent
changes to existing provider references. Reuse a baseline only if scope and age
are suitable; gather minimal current metadata as needed. Separate observations,
hypotheses, uncertainty, and suggested next actions. Do not silently expand
scope or collect unrestricted logs; remediation is separate from diagnosis.

### Existing-project adoption

Re-running the initializer adds missing shared skills without replacing existing
files. It does not upgrade existing copied skills or refresh the remote module
lock automatically. Document deliberate `devenv update` for module changes and
generation into a temporary project for reviewing/copying skill differences.
Preserve local edits and custom MCP entries. Do not introduce an overwrite flag.
Warn that copied skills and remotely imported modules can be different revisions;
the report records the collector version actually executed.

## Risks

API throttling, CLI schema changes, partial pagination, and restrictive IAM may
reduce coverage; explicit statuses and bounded collection prevent silent
success. Native inventory can omit resources the caller cannot see. Metadata
still reveals infrastructure even after field selection; keep output private.
Read-only checks cannot prove recovery, effective access, or architectural
suitability. Azure extension availability must be tested against the pinned Nix
inputs on supported CI platforms. No live-account verification is assumed.

## Steps

1. **Shared skills and report contract.** Create
   `skills/cloud-onboarding/SKILL.md`, linked `references/report-format.md` and
   `references/providers.md`, and `skills/cloud-troubleshoot/SKILL.md`.
   Specify the JSON envelopes, evidence location and references, all five result
   statuses, supported/manual provider coverage, permissions boundaries, and
   baseline-aware troubleshooting described above. Keep provider procedures in
   provider references rather than copying their manuals. Verify frontmatter,
   reference links, line limits, and agreement with the approved report contract.

2. **AWS collection and reporting.** Add
   `skills/cloud-onboarding/scripts/aws_report.py` using only the standard library
   and AWS CLI. Implement argument validation and Git/output preflight before
   cloud reads; identity verification before inventory; fixed read operations;
   selected-field normalization; bounded pagination, retries and deadlines;
   deterministic checks; private atomic report output; and the documented exit
   codes. Keep evidence in `inventory.json` with IDs referenced by findings and
   coverage. Use simple functions, no provider registry or scanner abstraction.
   Version the collector and ruleset explicitly. Verify each check against its
   official API/control source while implementing, including missing-field and
   absent-configuration semantics. Add `tests/onboarding.py` in this step: a
   standard-library test runner that creates a fake AWS executable and isolated
   Git projects, exercises the CLI end to end, and never needs real credentials.
   Run it before continuing; cover the verification cases below.

3. **AWS project command and flake check.** In `modules/aws/devenv.nix`, declare
   Python and expose `cloud-onboard-aws` from the module's own script revision.
   Resolve execution to the project root; include an offline `--help` smoke check
   in `enterTest`. In `flake.nix`, add an onboarding check running
   `tests/onboarding.py` with Python and Git available. Ensure tests resolve the
   collector from a supplied source path or their repository location so they
   work inside a Nix build. Verify the check and the generated AWS command without
   contacting a cloud account.

4. **Provider discovery corrections.** Add Azure `resource-graph` and its offline
   help check in `modules/azure/devenv.nix`; update
   `skills/azure/references/cli-cheatsheet.md` to use declared tooling. Update
   discovery sections of each provider's `references/cli-cheatsheet.md` and link
   shared guidance where appropriate. Explain GCP CLI asset access without
   changing `modules/gcp/gcloud-allow.json`. Correct Kubernetes live-scan examples
   in `skills/kubernetes/SKILL.md` and its CLI reference to disable node collection
   and use explicit scope. Correct OCI helper/key-file examples in its CLI,
   landing-zone, and Terraform references. Correct Hetzner inventory sensitivity
   and publication advice in its CLI and security references. Cover Cloudflare
   and DigitalOcean scope, permissions, pagination, and partial visibility in
   their discovery guidance. Verify changed commands against official references;
   no live scans or service activation. Run the Azure project tool check at the
   final verification step using the pinned project inputs.

5. **Generation and adoption.** Add both shared skills through `add_skill` in
   `pkgs/init.sh`; preserve existing copy and symlink behavior. Update
   `templates/base/AGENTS.md`, `templates/base/.gitignore`, and `README.md` with
   command usage, scope limitations, output privacy, exit codes, manual-provider
   coverage, and safe existing-project adoption. Explain module updates versus
   copied-skill updates, including temporary generation and reviewed copying;
   add no automatic overwrite or module-lock update. Extend
   `tests/generation.sh` to check all providers receive both skills and links,
   reruns preserve customized shared skills/MCP entries, and new reports are
   ignored. Exercise old-project report exclusion in `tests/onboarding.py`.
   Stage new source files before Nix commands so flake evaluation includes them.

6. **Regenerate and validate.** Run `nix run .#regenerate-templates` once source
   changes are ready; never hand-edit `templates/<provider>`. Run the tests below,
   fix failures at their source, and regenerate again only if source changes
   affect generated files. Inspect the final diff for unplanned changes, secrets,
   broken reference links, and misleading coverage claims. Preserve the previous
   generation/secrets/MCP regression checks. Document any unavailable live-account
   verification explicitly rather than claiming success.

7. **Reviewable delivery.** Commit implementation with a Conventional Commit
   referencing #14. If implementation deviates from the approved decisions,
   update this plan in the same commit and explain why. After `nix flake check`
   passes, push the task branch and open a PR with `Closes #14`, links to intent,
   specification and plan, supported scope, test results, and live-validation
   limitations. Review CI results, including informative macOS jobs; do not merge
   untested changes or assume PR creation authorizes a merge.

## Tests

Run focused checks as their steps become executable; the final flake check runs
all offline checks together. A successful mock run does not prove live AWS API
compatibility or IAM visibility.

- `python3 tests/onboarding.py` inside an environment providing Python and Git:
  pass with no network or cloud credentials. Supply synthetic responses through
  a temporary fake AWS executable, not a production bypass/test flag. Verify
  identity mismatch prevents discovery; command names are read-only; every
  regional call is scoped; IAM/global handling is explicit; and unsupported
  partitions or invalid inputs fail with code 1.
- The same test covers every rule, including all-protocol and covering-port
  ingress, IPv4/IPv6, absent/suspended versioning, missing S3 block versus access
  denial, CloudTrail home-region boundaries, malformed fields, complete empty
  lists, truncated lists, and command/total timeouts. Individual supported facts
  may pass in a partial report; unavailable evidence must never pass.
- Verify exit codes 0/2/1, stable IDs, matching JSON metadata, evidence references,
  Markdown status totals, unsupported coverage, manual-review entries, and no
  secret-shaped sentinel values in output or terminal messages. Exercise
  Markdown escaping with synthetic untrusted resource text.
- Verify private modes, collision and symlink rejection, tracked-path rejection,
  Git exclusion for old projects, unchanged prior reports, and temporary cleanup
  on handled failure. Use disposable directories, including paths with spaces.
- `nix run .#regenerate-templates`: successfully generate all eight providers.
- `nix flake check -L`: pass onboarding, generation, template freshness, skills,
  and existing MCP configuration checks. The generation suite must prove shared
  skill installation and preservation of local edits on reruns.
- For AWS and Azure separately, generate into disposable directories with
  `nix run . -- <provider> --into <directory>`, stage the generated project, and
  run `devenv --override-input cloud path:<absolute-repository-path> test` inside
  it. Expected: existing tool checks plus `cloud-onboard-aws --help` for AWS and
  `az graph query --help` for Azure succeed without cloud credentials.
- Check the PR's existing CI matrix for the other providers and Linux/macOS.
  Record macOS failures even though those jobs are currently informative.

## Approved verification requirements

- Add one credential-free Python test script with a fake AWS executable to
  exercise observable reports and command boundaries: matching/mismatching
  identity, representative pass/fail/manual results, denied reads, missing or
  malformed fields, pagination truncation, timeouts, and empty resource sets.
- Verify no write APIs are invoked, unknowns never become passes, selected
  regions are respected, raw secret-shaped sentinel fields do not reach any
  report or terminal output, and Markdown cannot inject resource-derived markup.
- Check deterministic finding IDs, JSON/Markdown consistency, exit codes,
  collision/symlink protection, private permissions, Git ignore behavior for old
  projects, and preservation of previous reports and customized skills.
- Integrate the offline collector tests into `flake.nix` checks. Extend
  `tests/generation.sh` for both shared skills and existing-project preservation.
- Regenerate all eight templates using `nix run .#regenerate-templates`; run
  `nix flake check` and relevant AWS/Azure generated-project `devenv test` checks.
  Existing CI supplies platform coverage. Only claim live validation if run
  against an explicitly selected account; otherwise record that limitation.

Design references: [AWS CLI pagination](https://docs.aws.amazon.com/cli/latest/userguide/cli-usage-pagination.html),
[S3 regional bucket listing](https://docs.aws.amazon.com/AmazonS3/latest/userguide/list-buckets.html),
[EC2 security groups](https://docs.aws.amazon.com/cli/latest/reference/ec2/describe-security-groups.html),
[Azure Resource Graph](https://learn.microsoft.com/en-us/azure/governance/resource-graph/first-query-azurecli),
[Cloud Asset Inventory](https://docs.cloud.google.com/asset-inventory/docs/asset-inventory-overview),
[Trivy Kubernetes](https://trivy.dev/docs/latest/target/kubernetes/).

## Rollback

Revert the implementation commit(s), retaining the approved artifacts as the
history of the decision. Regenerate templates from reverted sources if needed
and run `nix flake check`. If the implementation is split across commits, revert
in reverse order so module/script references remain consistent.

Existing projects roll back their cloud input through their tracked lockfile and
restore copied skills from their own Git history. Remove only the newly added
shared-skill directories/symlinks when rolling back their initial adoption;
never delete unrelated customizations. Locally generated reports and Git exclude
entries are retained unless the user explicitly chooses to remove them. No cloud
rollback is necessary because onboarding does not mutate cloud resources.
