---
status: approved
issue: 16
spec: spec/2026-09-16-16-multicloud-onboarding.md
---

# Plan: Automated multi-provider onboarding and command access

Implement on `feat/16-multicloud-onboarding` only after this plan is approved.
The approved specification decisions are reproduced below so this plan is
self-contained. Retain the approved intent and specification. Cite the relevant
numbered step in each implementation update. Any necessary design deviation must
be explicit and update this plan in the same commit as the affected code; do not
silently weaken scope, identity checks, coverage semantics or compatibility.

PR #15 is still open as of this plan's preparation. This branch is based on its
`195a6ec` revision. Implementation can proceed on that base after plan approval,
but final integration requires the predecessor to merge and this branch to be
rebased onto the resulting main. This task does not authorize merging PR #15.

## Approved decisions

### Scope and compatibility

Extend the approved intent with executable collectors for Azure, GCP, OCI,
Kubernetes, Cloudflare, Hetzner and DigitalOcean. Every collector produces
inventory and bounded configuration findings, not just native recommendations.
Preserve `cloud-onboard-aws`, its arguments, exit codes, version-1 report schema,
and the 35 existing offline scenarios. No cloud account is accessed during
development without an explicit test target. This work depends on PR #15.

First release is deliberately scoped: one tenant/account/project/cluster per
invocation, with explicit child scopes where applicable. There is no automatic
organization traversal, cross-provider combined report, scheduler, dashboard,
report diff, remediation, or compliance certification. All seven new providers
are required for completion; implementation may proceed in tested increments.

### User interfaces

Provide the same executable through three routes:

```sh
# Inside devenv shell or after direnv allow:
cloud-onboard-aws --account-id 123456789012 --regions eu-west-1 \
  --environment production --profile audit

# Inside that same environment, from the generated project:
just onboard aws --account-id 123456789012 --regions eu-west-1 \
  --environment production --profile audit

# From a Git project root, without entering the project shell:
nix run github:olafkfreund/cloud-projects-templates#onboard-aws -- \
  --account-id 123456789012 --regions eu-west-1 \
  --environment production --profile audit
```

Use `cloud-onboard-<provider>` and `#onboard-<provider>` for each provider.
The flake default remains project generation. Shell modules expose only the
selected providers; no all-cloud SDK closure is imposed on single-cloud projects.
Direct flake apps package Python, Git and only the required provider CLI, using
the invoked flake revision. They do not generate a project, update a lockfile,
decrypt secrets, or change the caller's directory. Require execution at a Git
root. Devenv wrappers retain AWS's behavior of resolving `DEVENV_ROOT`.

Put shared package construction in `pkgs/onboarding.nix`, consumed both by
`flake.nix` and provider modules. Dependencies use the caller's pinned nixpkgs;
source code is the module/app revision. Do not import this flake's packages into
project modules through a second nixpkgs evaluation. `--help` performs no cloud
or filesystem preflight and succeeds without credentials.

Add `just` to `modules/common/devenv.nix`. Generate `cloud-onboarding.just` with
an `onboard provider *args` recipe using per-recipe `[positional-arguments]`,
an explicit Bash shell, a fixed provider allowlist, and quoted positional
forwarding (`"$@"`); never interpolate user arguments into shell source or use
`eval`. New projects get a small `justfile` importing that file. Reject unknown
providers before command execution; a provider not installed in the shell gets
a clear error and help on adding its module.

The generator must add missing recipe files even when `devenv.yaml` already
exists. Preserve existing `justfile`, `Justfile`, `.justfile`, symlinks and recipe
files; do not automatically append imports to user files. Document the reviewed
import and fallback `just --justfile cloud-onboarding.just onboard ...` for old
projects. This recipe requires an activated project environment; it does not
implicitly enter another shell or fetch a remote revision. Test the pinned just
version's argument and exit-code behavior. Shell/direnv activation never scans.

### Collector organization and common behavior

Keep scripts under `skills/cloud-onboarding/scripts/`: existing `aws_report.py`,
new `<provider>_report.py` files and a small `report_common.py`. Extract only
demonstrably shared execution, normalization, evidence, finding and private
publication helpers. No provider registry, plugin discovery, SDK framework,
daemon or new Python dependency. Package/copy the complete scripts directory so
sibling imports work from the Nix store and installed skills. AWS's rules and
renderer remain compatible; shared functions accept provider-specific data.

New collectors accept `--environment`, `--max-items` (default 1000 per list),
`--command-timeout` (60 seconds), and `--timeout` (900 seconds), all validated.
Apply a 16 MiB per-response/stdout/stderr bound, a 200 MiB aggregate response
budget and a maximum of 1000 requests including retries. Reaching any bound is
partial coverage, not successful exhaustion. Deadlines include retries and
pagination. Terminate timed-out CLI process groups, avoid unbounded
`capture_output`, and do not spool unrestricted responses to disk.

Follow explicit continuation metadata whenever available. For CLI lists that
hide tokens, request at most N+1 records where supported; more than N means
truncated. If a CLI cannot bound output, use paged read APIs or enforce byte and
time limits and mark interrupted collection partial. Do not mistake exactly N
records for proven exhaustion. Reject repeated tokens/pages and malformed page
metadata. Deduplicate resource IDs without concealing pagination anomalies.

Use argument-list subprocesses, no shell; disable prompts, pagers and automatic
extension/service installation. For direct HTTP use Python stdlib, verified TLS,
fixed provider HTTPS origins, no redirects, and in-memory authorization headers.
Do not follow arbitrary pagination URLs; validate origin/path and reuse only
documented continuation parameters. No credentials in argv, exceptions, debug
output, URLs, persisted metadata or the Nix store. Existing CLI authentication
is used only with explicit scope and profile/config selection. CLI cloud/endpoint
overrides must be checked or rejected; first release targets public commercial
Azure/GCP/OCI and the official SaaS APIs. Kubernetes uses the explicitly verified
kubeconfig endpoint, with TLS verification required.

Retry only transient timeouts, HTTP 429 and 5xx, at most twice with bounded
backoff/Retry-After within the total deadline. Do not retry authorization errors
as successful emptiness. Redact errors to categories; register planned operations
before collection so deadlines leave explicit `not_collected` entries. Optional
native recommendations require `--include-recommendations`; when requested,
denied/unavailable results are partial, otherwise recorded as unsupported/not
requested rather than an invented pass. No scanners or paid services are enabled.

### Identity and scope contracts

| Provider | Required arguments and credentials | Verification before inventory |
|---|---|---|
| Azure | `--tenant-id`, `--subscription-id`; existing Azure CLI login | Compare `az account show --subscription` tenant/subscription, validate enabled subscription and public-cloud context. Never run `az account set`. |
| GCP | `--project-id`, `--expected-principal`; existing gcloud credentials; optional explicit `--impersonate-service-account` | Compare project ID/number from `gcloud projects describe`; resolve active versus impersonated principal. Reject unexpected ambient impersonation or identity. Use project-wide scope and report locations per resource; no organization mode. |
| OCI | `--tenancy-id`, `--compartment-ids`, `--regions`, `--profile`; existing OCI API-key/security-token config | Check profile tenancy and principal metadata without logging credentials, then tenancy and each compartment read. Compartment ancestry must terminate at expected tenancy; inaccessible ancestry prevents verification. No recursive compartment expansion. |
| Kubernetes | `--context`, `--expected-server`, `--expected-principal`, `--namespaces`; existing kubeconfig | Resolve only selected context and compare HTTPS endpoint; call `kubectl auth whoami` and compare principal. Read each selected Namespace UID when permitted; denied namespace metadata is a coverage gap. Local context name alone is not cluster identity; record server plus observed namespace UIDs. Identity review failure stops collection. |
| Cloudflare | `--account-id`, `--zone-ids`; `CLOUDFLARE_READ_TOKEN` | Read expected account and each zone, compare returned account/zone IDs. Do not use token validity alone as identity proof. No automatic zone expansion. |
| Hetzner | `--project-label`, `--acknowledge-project-token`; `HCLOUD_TOKEN`; optional `--expected-server-id` | Project association is explicitly user-attested because no project-identity endpoint is assumed. Optional server GET must match expected ID; this corroborates resource access, not a project ID. Failed authentication or sentinel mismatch stops collection. |
| DigitalOcean | `--account-uuid`, `--project-id`; `DIGITALOCEAN_READ_TOKEN` | GET account and project; compare UUID, project ID and returned ownership metadata where present. Do not equate the account UUID with verified team identity. Record the API's identity limits. |

No first-resource guessing or global credential-context changes. Kubernetes
`SelfSubjectReview` uses a POST but persists no workload or configuration; it is
an explicitly allowed authentication operation. No other Kubernetes create,
patch, exec or debug operations are allowed. Do not store kubeconfig credentials
or complete config output. Namespace permission gaps after verified identity are
reported per scope, never handled by escalating permissions.

### Provider operations, fields and checks

All inventory fields below are whitelisted. Keep IDs, resource kind, location,
selected relationships and configuration booleans/numbers. Keep tag/label
presence, not arbitrary values. Never persist instance metadata/user-data,
environment variables, secret objects, database credentials, DNS record content,
certificate material, logs or unrestricted recommendation payloads. Unavailable
required fields produce unknown. Each rule has a stable provider-prefixed ID,
version, severity, predicate, evidence references and official source.

**Azure.** Use `az graph query` with explicit subscription, stable ID ordering,
selected projections and skip tokens for resource ID/type/location/group and
tag-presence inventory. For supported records, use scoped read commands:
`az vm show`, `az network nsg show`, and `az storage account show`; retrieve no
VM instance-view extensions or deployment outputs. Fields: VM disk/resource
relationships; NSG direction/access/protocol/port ranges/source prefixes;
storage HTTPS-only, minimum TLS, public-blob setting. Fail the storage baseline
when HTTPS-only is false, minimum TLS is older than 1.2, or public blob access is
allowed. Flag inbound Allow TCP 22/3389 from any IPv4/IPv6 source, including
ranges and wildcard protocols, as an exposed rule, not proven reachability.
VM presence alone does not prove encryption/backup adequacy. Optional
`az advisor recommendation list` retains ID/category/impact only as native
review items. Permissions: resource/subscription reads, Resource Graph access,
`Microsoft.Compute/virtualMachines/read`,
`Microsoft.Network/networkSecurityGroups/read`,
`Microsoft.Storage/storageAccounts/read`; optional
`Microsoft.Advisor/recommendations/read`. Reader is a suggested existing role,
not something the collector grants. Record Graph visibility and indexing limits.

**GCP.** Use `gcloud asset search-all-resources` with project scope and selected
read mask for name/type/location; `gcloud compute instances list`,
`gcloud compute disks list`, `gcloud compute firewall-rules list`, and
`gcloud storage buckets list` with selected JSON fields, explicit project and
principal. Fetch bucket details through `gcloud storage buckets describe` only
when required fields are missing from list results. Fields: instance/disk
relationships, external-IP presence (no address persistence), firewall
direction/disabled/action/protocol/ports/source ranges, bucket public-access
prevention, uniform bucket-level access and versioning. Fail active INGRESS
allow rules covering world-open TCP 22/3389 and explicit uniform-access=false;
public-access prevention `enforced` passes, inherited/unspecified requires
manual review of organization policy. Versioning disabled requires manual
review, not universal failure. External IP is exposure evidence, not a failure
on its own. Do not flag provider-managed disk encryption as missing merely
because CMEK is absent. Permissions: `resourcemanager.projects.get`,
`cloudasset.assets.searchAllResources`, `compute.instances.list`,
`compute.disks.list`, `compute.firewalls.list`, `storage.buckets.list/get`.
SCC and Recommender integration are unsupported in this first collector, with
manual review retained; no API activation or IAM-policy dump.

**OCI.** Use `oci iam tenancy get`, `oci iam compartment get`,
`oci search resource structured-search`, `oci compute instance list`,
`oci bv volume list`, `oci network vcn list`, `oci network security-list list`,
`oci network nsg list`, `oci network nsg rules list`,
`oci os ns get`, `oci os bucket list/get`, all with explicit profile, tenancy
where accepted, region and compartment. Escape/validate OCIDs before inserting
them into structured query text. Search supplies bounded overview; the selected
service lists supply check evidence. Fields: resource IDs/relationships, ingress
source/protocol/port ranges, bucket public-access type and versioning. Fail
world-open TCP 22/3389 ingress and non-private bucket public-access type under
this private-storage baseline. Versioning disabled/suspended requires review;
provider-managed encryption is not absence of encryption. Permissions: read
tenancy/compartment metadata, inspect supported resource families, and the read
permissions needed for security rules and bucket details; document policy
resource families `instances`, `volumes`, `vcns`, `security-lists`,
`network-security-groups`, `objectstorage-namespaces`, `buckets`, scoped to
selected compartments where possible. `NotAuthorizedOrNotFound` is unknown.
Cloud Advisor/Cloud Guard ingestion is deferred and listed as unsupported.

**Kubernetes.** Through `kubectl --context`, read Namespace metadata and list
Pods, Deployments, StatefulSets, DaemonSets, Services, Ingresses and
NetworkPolicies separately in each selected namespace. Use bounded list chunks
and selected output fields; never `get all`, Secret/ConfigMap reads, events,
logs or unrestricted YAML. Fields: UID/owner relationships, desired/ready counts,
container security-context booleans, request/limit presence, probe presence,
host namespace flags, Service exposure type and Ingress TLS-secret reference
presence (not secret names/content). Check explicit privileged=true,
allowPrivilegeEscalation=true and hostPID/hostIPC/hostNetwork=true as failed
baseline configuration; explicit false satisfies only that field. Missing
security settings need manual review of defaults/admission, not a fabricated
pass. Missing requests/limits/probes and desired-ready shortfall require review;
shortfall is a point-in-time observation, not a diagnosed outage. No
NetworkPolicies after a complete namespace list yields manual review; their
presence is never a pass for effective isolation. Permissions: selected
Namespace GET, namespaced GET/LIST for these resource kinds, identity review.
No cluster-wide workload listing, Nodes, RBAC dumps, scanner jobs or Trivy
execution in the automated collector.

**Cloudflare.** Use stdlib HTTPS GET to `/client/v4/accounts/{id}`,
`/zones/{id}`, `/zones/{id}/dns_records`, and individual zone settings
`ssl`, `min_tls_version`, `always_use_https`; explicitly selected zones only.
Keep DNS ID/type/proxiable/proxied booleans, no names/content; settings retain
only ID/value. `ssl=strict` passes this baseline; off/flexible/full fail the
strict origin-verification baseline. TLS below 1.2 and Always Use HTTPS off
fail these bounded transport checks. DNS-only records require workload review,
not failure. Optional `/accounts/{id}/security-center/insights` retains issue
ID/type/severity/status/time only as native findings needing review. Follow its
documented page metadata separately from DNS pagination. Permissions: Account
Settings Read, Zone Read, DNS Read, Zone Settings Read, and Security Center read
when explicitly requested. Feature/plan unavailability produces unknown, never
activation. Verify token types through actual scope reads; do not require a
user-token-only verification endpoint for account-owned tokens.

**Hetzner.** Use stdlib HTTPS GET at `https://api.hetzner.cloud/v1` for
`/servers`, `/volumes`, `/networks`, `/firewalls`, `/load_balancers`, and optional
`/servers/{sentinel}`. Require the existing project Read token in `HCLOUD_TOKEN`.
Follow `meta.pagination.next_page`; keep only IDs, status, location, attachment
relationships, backup-window presence, protection flags, selected ingress
rules and load-balancer target-health booleans. World-open inbound TCP 22/3389
fails the rule baseline. Missing backups or delete protection requires manual
review because stateless/reprovisionable servers are legitimate. Unhealthy LB
targets require review of a point-in-time observation. Do not infer host firewall
absence from missing cloud firewall associations. Labels used for attachment
selectors are evaluated transiently without storing values; unresolved selectors
make associations unknown. Object Storage, Robot, Storage Boxes and account
audit/token policy are explicitly unsupported.

**DigitalOcean.** Use stdlib HTTPS GET at `https://api.digitalocean.com/v2` for
`/account`, `/projects/{id}`, `/projects/{id}/resources`; fetch selected project
Droplets, volumes and load balancers by their typed URNs using their GET routes.
Reject unknown URN types as unsupported, do not treat arbitrary URNs as paths.
GET `/droplets/{id}/firewalls` for selected Droplets; do not enumerate unrelated
team resources to repair missing project scope. Fields: resource ID/region,
project membership, Droplet backup feature and attachment IDs, firewall inbound
sources/protocol/ports, load-balancer forwarding TLS/redirect booleans. Fail
world-open TCP 22/3389 firewall rules; absent backups, missing cloud firewall or
HTTP-only forwarding requires manual review. No database users, app specs,
kubeconfigs or Spaces credentials. Permissions: `account:read`, `project:read`,
`droplet:read`, `block_storage:read`, `load_balancer:read`, `firewall:read` as
applicable. Follow validated `links.pages.next`; record that token scopes can
silently hide project resources. Unsupported URNs remain explicit inventory
stubs without configuration conclusions. Spaces and managed databases are
unsupported for configuration assessment in this release.

### Reports and interpretation

New collectors use schema version 2 in the same four-file layout, with common
run metadata: ID, times, provider, environment, collector/ruleset/tool versions,
`requested_scope`, `observed_scope`, and `identity` (method, status, evidence
references). Scope is a provider-specific typed object using the argument names
above; observed scope must never be copied from requested input without evidence.
Identity status is `verified`, `attested`, or `corroborated`; failed required
verification exits before inventory. Hetzner attestation remains visible in the
human summary and coverage even when its collection completes.

Reuse v1 resource/evidence/finding shapes and statuses. Extend coverage with
explicit visibility limitations and operation freshness (`observed_at`, optional
upstream `updated_at`, and `unknown` when unavailable). Queries against indexed
inventories do not prove real-time freshness. Native recommendations preserve
provenance and are `manual_review`, not automatically mapped to deterministic
pass/fail. Add a summary table of supported resource families and checks.

`complete` means all requested supported operations exhausted within limits,
not exhaustive provider visibility. Unsupported families and attested identity
remain visible even in completed reports. Exit 0 = report with supported
collection complete regardless of findings; 2 = valid partial report; 1 = invalid
input, failed required identity or output failure. Wrappers preserve the exit
code. Where just wraps failures, use its documented exit-code propagation and
verify the observed result rather than assuming equivalence.

Keep `reports/<environment>/<timestamp-and-id>/`, private modes, Git exclusion,
symlink/tracked-path rejection, atomic publication, Markdown escaping and old-run
preservation. No credential hashes or secret-shaped identifiers are invented as
identity proofs. Always include manual review for workload ownership, least
privilege, restore evidence/RTO/RPO, resilience, cost/budgets and governance.
Source links are fixed rule metadata, never untrusted recommendation URLs.

Document v1/v2 explicitly in the shared report reference; older AWS reports
remain usable for troubleshooting. Schema-aware consumers must dispatch by
version. Do not silently relabel old reports or imply automatic comparisons.

### Documentation and generated projects

Update README, onboarding/troubleshooting guidance, provider CLI references and
`templates/base/AGENTS.md` with exact coverage and command examples. Keep skills
within existing file limits by using linked references. Explain `just --list`,
help, credentials, input scope, missing providers, exit codes, output privacy,
v1/v2 schemas, shell/app revision differences and existing-project adoption.
Update provider `enterTest` with credential-free command help checks and common
checks with just availability. Regenerate all eight templates through the
maintainer command; never hand-edit generated files.


## Steps

1. **Establish the baseline and resolve pinned-tool details.** Read the repository
   instructions and inspect the working tree before changes. Run
   `python3 tests/onboarding.py` and preserve representative synthetic v1 outputs
   for the later extraction comparison. Inspect the pinned CLI help/schema for
   the approved read operations, including Azure Graph skip tokens, gcloud list
   limits/projections, OCI next-page fields, Kubernetes selected-field output,
   and just positional arguments/exit codes. Obtain tool help through project
   dependencies or the pinned flake inputs, never machine-wide installation.
   Confirm direct HTTP response/permission shapes against official specifications
   and build synthetic fixtures from those shapes. Resolve provider defaults
   explicitly rather than coding from guessed field names. Verify: baseline
   scenarios pass; each planned operation has an exact argv/URL, projection,
   permission, pagination strategy and expected failure category recorded in
   provider references or tests. No credentialed cloud calls. If a required
   operation cannot satisfy the approved bounds, revise the affected plan detail
   before implementing it; do not replace checks with fabricated passes.

2. **Extract shared safety and reporting with AWS compatibility.** Add
   `skills/cloud-onboarding/scripts/report_common.py`; update `aws_report.py`
   only where behavior can be preserved. Implement reusable private output
   protection, evidence/finding construction and parameterized publication.
   Add the v2 renderer and typed scope/identity envelope without changing AWS v1.
   Add bounded subprocess and fixed-origin HTTP execution, finite retry/deadline
   accounting, pagination checks and redacted errors for new collectors. Keep
   provider-specific decoding and rules in their files; no framework or dynamic
   loading. Add `tests/onboarding_multi.py`, a standard-library executable test
   runner accepting an optional source root like the existing AWS runner; use
   unittest.mock for HTTP injection and fake executables for CLI paths. Verify:
   existing AWS scenarios and normalized v1 output comparison pass; shared tests
   exercise size/time/request limits, redirect rejection, coverage, atomic
   publication and secret exclusion before provider work starts.

3. **Implement Azure.** Add `azure_report.py` with the approved tenant/subscription
   checks, Graph paging, VM/NSG/storage reads and storage/ingress rules. Include
   opt-in Advisor ingestion and fixed native-review semantics. Tests cover
   disabled/wrong subscription, denied Graph/detail reads, missing projections,
   multiple pages, rule defaults/ranges/wildcards and unavailable Advisor.
   Verify: Azure fake-CLI cases pass, recorded commands use explicit subscription,
   and unavailable evidence never becomes absence or a pass.

4. **Implement GCP.** Add `gcp_report.py` with project/principal verification,
   explicit impersonation handling, bounded asset/compute/firewall/storage reads
   and approved bucket/ingress rules. Preserve provider-managed encryption
   semantics and mark inherited public-access prevention as review. Tests cover
   ambient impersonation mismatch, disabled API, N/N+1 list boundaries, partial
   aggregate lists, bucket detail fallback and missing fields. Verify: GCP cases
   pass and no service enablement, IAM-policy dump or MCP allowlist change occurs.

5. **Implement OCI.** Add `oci_report.py` for profile/tenancy/compartment ancestry
   validation and approved per-region lists/detail reads. Bound ancestry traversal
   and detect cycles; do not broaden compartment scope. Validate OCIDs used in
   query text. Normalize security-rule and bucket evidence with explicit
   NotAuthorizedOrNotFound handling. Tests cover tenancy mismatch, inaccessible
   or cyclic ancestry, multiple regions/compartments, next pages and required
   rule cases. Verify: OCI cases pass; every recorded call has the intended
   profile and regional/compartment context where its API accepts it.

6. **Implement Kubernetes.** Add `kubernetes_report.py` for selected kubeconfig
   endpoint/TLS checks, principal review and selected namespace reads. Use the
   approved resource-kind allowlist; select configuration fields from Pods and
   workload templates without persisting arbitrary manifests. Account for pod-
   versus container-level settings without declaring missing defaults healthy.
   Tests include denied Namespace metadata after valid identity, expired list
   continuation, absent API kinds, missing/explicit security settings, init
   containers, namespace boundaries and workload readiness. Verify: only allowed
   reads and the non-persistent identity review execute; no Secrets, logs, exec,
   cluster-wide workload lists or scanner workloads are accessed.

7. **Implement Cloudflare.** Add `cloudflare_report.py` using fixed-origin stdlib
   HTTPS and the existing read-token environment variable. Verify account and
   explicit zones, collect selected DNS/settings, and implement transport rules
   plus opt-in Insights. Tests distinguish DNS and Insights pagination shapes,
   account/zone mismatch, unavailable settings and native recommendations.
   Verify: no DNS names/content, token values or arbitrary recommendation links
   are retained; each zone remains within the requested account.

8. **Implement Hetzner.** Add `hetzner_report.py` with explicit token-project
   attestation, optional server corroboration, approved five resource families
   and page metadata. Persist the weaker identity status visibly. Use selected
   firewall/backup/protection/health evidence; evaluate label selectors only in
   memory and mark unresolved associations unknown. Tests cover missing
   attestation, sentinel mismatch, empty valid project, page termination,
   unsupported selectors and manual-review cases. Verify: no claim of API-verified
   project identity and no Object Storage/Robot/Storage Box scope expansion.

9. **Implement DigitalOcean.** Add `digitalocean_report.py` with account/project
   verification, bounded project-resource pagination, typed URN routing and
   approved resource detail/Droplet-firewall reads. Unsupported URNs become
   explicit stubs. Tests cover ownership metadata absence/mismatch, token-scope
   visibility limitations, unsupported URNs, cross-origin next URLs, repeated
   pages and missing firewall/backup information. Verify: no unrelated team
   enumeration and no assumption that a completed project list reveals every
   resource family the user owns.

10. **Package commands and add all flake apps.** Add `pkgs/onboarding.nix` and
    wire per-provider packages/apps through `flake.nix`. Update the eight provider
    modules to expose the same packaged executable with project-root handling;
    retain the AWS command and avoid importing a second nixpkgs. Include the
    complete Python script directory. Only CLI-backed collectors need their
    provider CLI in the app closure; HTTP collectors need Python and Git, while
    existing project provider tooling remains available. Add offline `--help`
    smoke checks to provider `enterTest`. Verify: all eight `nix run
    .#onboard-<provider> -- --help` invocations succeed from outside any generated
    project, with no credentials; paths, output-root behavior and exit codes
    remain correct through the package and devenv wrappers.

11. **Add just access and safe adoption.** Add `just` to the common module,
    `templates/base/cloud-onboarding.just` and the fresh-project import file;
    update `pkgs/init.sh` so old projects receive missing recipe files without
    shadowing existing task filenames or following symlinks. Use a single
    positional-argument recipe, fixed provider validation and clear missing-tool
    errors. Extend `tests/generation.sh` and add `tests/onboarding-entrypoints.py`
    for fake-command argument/exit tests; use no new framework. Verify: all eight
    providers forward literal arguments and 0/1/2 exits, activation performs no
    scan, and reruns preserve customized/symlinked task files and existing skills.
    Test projects with spaces and all supported task-file names. `just --list`
    and the standalone recipe-file fallback must work as documented.

12. **Complete documentation and integrate checks.** Update README,
    `skills/cloud-onboarding/SKILL.md`, its report/provider references,
    `skills/cloud-troubleshoot/SKILL.md`, provider CLI references and
    `templates/base/AGENTS.md`. Document exact permission requirements and selected
    fields, first-run examples for each provider, all three entry points,
    credential handling, v1/v2 differences, privacy, partial exits, attestations,
    optional recommendations and existing-project adoption. Split references as
    needed to respect limits, with official source links. Add multi-provider and
    entry-point checks in `flake.nix`; adjust existing CI only where required to
    exercise new app help checks and recipe integration, preserving current
    provider/OS, secret and MCP checks. Verify: every approved provider/check and
    user entry point maps to implementation, documentation and an observable
    test; no manual-only claims remain for implemented coverage.

13. **Regenerate and validate.** Stage new source files so Nix includes them,
    then run `nix run .#regenerate-templates` and `nix flake check -L`. Review all
    generated changes rather than hand-editing them. Run fresh-project devenv
    tests for all eight single-provider combinations and the existing mixed
    combinations through the local source override. Exercise direnv activation
    in a disposable project when available, confirming command discovery and
    zero API calls; otherwise report this runtime check as unavailable and test
    the unchanged .envrc wiring plus devenv shell directly. Verify the tests
    below; fix at the source and regenerate only when source changes require it.

14. **Deliver for review.** Commit tested implementation with Conventional Commits
    referencing #16. Keep plan deviations with their code. Run `nix flake check`
    before pushing. Open a PR with `Closes #16`, links to all three artifacts,
    supported coverage, test evidence and explicit live-validation gaps. If #15
    remains open, use its branch as the stacked PR base and state the dependency;
    after its authorized merge, rebase on main, retarget, and rerun affected
    checks before integration. Inspect every CI result, including informative
    macOS jobs. Do not merge without authorization or claim live validation from
    fixtures. No all-provider completion claim while any collector is missing.

## Tests

Run focused tests after the associated step; do not wait for final integration
or repeatedly rebuild unchanged providers. The following new test filenames
are part of this plan and must be added before these commands are run:

- `python3 tests/onboarding.py`: all existing AWS scenarios pass.
- `python3 tests/onboarding_multi.py`: shared safety, reporting and all seven
  provider cases pass without cloud credentials/network. The runner accepts an
  optional source-root positional argument for Nix sandbox execution.
- `python3 tests/onboarding-entrypoints.py`: with pinned just/Bash/Git on PATH,
  literal arguments, dispatch, help, missing provider and exit-code tests pass.
- `nix run .#onboard-aws -- --help`, repeated with azure, gcp, oci, kubernetes,
  cloudflare, hetzner and digitalocean: success without credentials/Git preflight.
- `nix run .#regenerate-templates`: all eight templates generated from source.
- `nix flake check -L`: old and new checks pass, including format, freshness,
  generator, MCP configuration, AWS regression, new collectors and entry points.
- For each existing CI provider combination, use a disposable project directory:
  run `nix run . -- <providers> --into <directory>`, stage generated files inside
  that project, then run `devenv --override-input cloud path:<absolute-repo> test`
  there. Expect provider tool checks, onboarding help and just checks to pass.
  Run `devenv --override-input cloud path:<absolute-repo> shell -- just --list`
  and each installed `just onboard <provider> --help` route. Execute commands
  sequentially and inspect results; never point disposal/cleanup at user projects.
- Inspect the existing Linux/macOS CI matrix after PR creation. Record macOS
  failures even where CI currently marks them informative.

### Required verification cases copied from the approved specification

- Preserve and run the existing 35 AWS scenarios; compare representative AWS
  v1 reports before/after extraction, ignoring timestamps/run IDs.
- Add standard-library fake-CLI and fake-HTTP tests for every new provider:
  verified/mismatched/attested identity, each rule pass/fail/unknown/manual case,
  absent fields, denied scope, unsupported kinds, multiple pages, N/N+1 limits,
  repeated tokens, 429/5xx, response-size bounds, timeouts and partial publication.
  Inject HTTP transports in tests, never add a production arbitrary-endpoint flag.
- Assert exact allowed operations and explicit scopes. Reject unsafe redirects,
  cross-origin pagination, user-controlled paths and cloud-context overrides.
  Verify no secret sentinel, raw response or arbitrary error reaches files/logs.
- Test schema agreement, stable IDs, evidence references, identity claims,
  unknown freshness and visibility limits, permissions, symlink/tracked-output
  rejection, collision safety and unchanged prior runs.
- Test all just routes with fake executables for arguments containing spaces,
  quotes, dollar signs and shell substitutions; zero arguments/help, unknown or
  missing provider, exact 0/1/2 exit codes, project paths with spaces and existing
  differently cased task files. Help and shell entry invoke no provider APIs.
- Run package/app help smoke checks for all eight providers, generation/adoption
  checks, skill validation, `nix flake check`, regenerated-template freshness and
  generated-project `devenv test` across the existing Linux/macOS CI matrix.
- Live acceptance uses one explicitly approved scope per provider and an
  existing read credential; compare selected known resources and configuration
  with the provider console. Report untested providers honestly; offline success
  is not proof of live permissions or full API compatibility.


## Rollback

Revert implementation commits in reverse dependency order, keeping the approved
artifacts as the audit trail. Restore the old AWS wrapper and standalone script
before removing shared helpers; do not leave a module referencing a removed
package. Regenerate templates from reverted sources and run the flake checks.
No cloud rollback is needed because collectors only inspect configuration.

Existing projects revert their cloud input lockfile through their own Git history.
Copied skills and just imports are separate: restore only reviewed task changes,
never remove unrelated customizations or overwrite a user's task files. Retain
local reports and Git exclusion entries unless their owner explicitly requests
removal. New v2 reports are not rewritten as v1. This task performs no automatic
module-lock upgrades, global package installation or credential changes.

## Official research and implementation verification references

Official documentation consulted for this specification on 2026-09-16:

- [just positional arguments](https://just.systems/man/en/positional-arguments.html).
- [Azure Graph CLI](https://learn.microsoft.com/en-us/cli/azure/graph) and
  [result limits](https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/work-with-data).
- [GCP asset CLI](https://docs.cloud.google.com/sdk/gcloud/reference/asset/search-all-resources),
  [Compute discovery schema](https://www.googleapis.com/discovery/v1/apis/compute/v1/rest),
  [Storage discovery schema](https://storage.googleapis.com/$discovery/rest?version=v1).
- [OCI Search CLI](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/search/resource/structured-search.html).
- [Kubernetes identity reviews](https://kubernetes.io/docs/reference/access-authn-authz/authentication/#api-access-to-authentication-information)
  and [list APIs](https://kubernetes.io/docs/reference/using-api/api-concepts/).
- [Cloudflare OpenAPI](https://github.com/cloudflare/api-schemas/blob/main/openapi.yaml).
- [Hetzner token creation](https://docs.hetzner.com/cloud/api/getting-started/generating-api-token/)
  and [official client](https://github.com/hetznercloud/hcloud-go/blob/main/hcloud/client.go).
- [DigitalOcean API definitions](https://github.com/digitalocean/openapi/tree/main/specification/resources),
  including account, firewall and project-resource permissions.

The search service was unavailable; direct official sources were used. Hetzner's
rendered reference exposes a specification location that did not resolve through
the attempted URLs; its official client confirms page/per-page parameters and
next-page metadata, and its token documentation confirms project selection and
GET-only Read tokens. Test wire-level pagination with representative API fixtures.
Exact CLI flags, JSON projections,
API read actions and optional-service permission names must be checked against
the pinned tool versions before the implementation plan's verification commands
are finalized. No undocumented identity endpoint or cloud behavior is assumed.
