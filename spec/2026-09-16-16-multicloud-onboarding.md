---
status: approved
issue: 16
intent: intent/2026-09-16-16-multicloud-onboarding.md
---

# Spec: Automated multi-provider onboarding and command access

## Design

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

## Alternatives rejected

- Seven copies of the AWS script: duplicates publication and security behavior.
- A plugin/SDK framework or mandatory Prowler/Trivy scanning: unnecessary
  dependencies, broader permissions and less predictable initial coverage.
- Inventory search alone or forwarding native recommendations: insufficient
  configuration evidence and provider-dependent paid-service availability.
- One mega-package for all providers: unnecessary closure and activation cost.
- Automatic scans on direnv entry, saved credentials in just/Nix files, or
  interpolated shell arguments: unwanted cloud access and credential/injection
  risks. Explicit commands and positional forwarding are sufficient.
- Claiming strong Hetzner project verification without an identity endpoint:
  misleading. Explicit attestation and optional known-resource corroboration
  describe the evidence we actually have.
- Forcing AWS v1 account/region fields onto every provider: misrepresents scope;
  explicit v2 reports avoid changing existing AWS output.

## Risks

API/CLI version differences, indexed inventory lag, denied fields, hidden token
scope omissions and request limits can produce partial evidence on any provider.
Predicate tests must include provider defaults, wildcard protocols and port
ranges; a rule observation does not prove effective network reachability.
Kubernetes authentication plugins execute local user-configured programs;
the tool assumes an intentionally selected trusted kubeconfig and records no
plugin output. Credentials with write capability are not made read-only merely
by this collector; its operation allowlist and users' least-privilege credentials
provide distinct protections. Shared extraction can regress AWS, and packaging
can lose sibling imports or special arguments. Existing task files and shell
configurations must survive adoption untouched.

## Verification

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

## Research references

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
