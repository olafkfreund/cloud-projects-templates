---
status: approved
issue: 16
author: olafkfreund
---

# Intent: Automated multi-provider onboarding and accessible commands

## Problem

The onboarding work in #14 / PR #15 automates AWS only. Azure, GCP, OCI,
Kubernetes, Cloudflare, Hetzner and DigitalOcean still require an agent to
assemble evidence and reports manually. This makes recurring assessments less
repeatable and makes coverage dependent on the individual agent session.

AWS is available in `devenv shell` and direnv through
`modules/aws/devenv.nix`, but there is no onboarding flake app or generated
`just` recipe. Users need discoverable, consistent entry points without copying
long commands from a conversation or installing tools globally.

## Proposed outcome

- All eight providers have executable, read-only onboarding that produces local
  Markdown and JSON inventory, findings and coverage reports without requiring
  an agent to assemble them. Each provider documents its supported resource
  families, checks, credentials and limitations.
- Selected-provider commands are available in generated project shells and
  direnv. Users can also invoke onboarding through a documented `just` recipe
  and explicit Nix flake apps. The existing AWS command remains compatible.
- Users supply the target account/tenant/project/cluster, regional or namespace
  scope, environment label and existing authentication explicitly. Shell
  activation never starts collection. Help is available without credentials.
- Repeat runs preserve previous reports. Findings carry stable identifiers,
  evidence, actionable recommendations and official references. Collection
  success is distinguished from healthy configuration and complete visibility.
- Documentation covers first use, each entry point, permission requirements,
  coverage, troubleshooting, and adoption in customized existing projects.

## Affected users and systems

Operators and coding agents using generated projects for all eight providers.
Likely affected sources are `skills/cloud-onboarding/`, provider guidance,
`modules/*/devenv.nix`, `flake.nix`, `pkgs/init.sh`, `templates/base/`, tests and
README. Generated provider templates must be regenerated, never edited by hand.

The task branch starts from PR #15 commit `195a6ec`; delivery depends on that
work. It must be rebased onto the merged predecessor before final integration.

## Constraints

- Preserve AWS behavior and its regression tests. Reuse existing CLIs and the
  report contract where appropriate; avoid seven copies of output protection,
  error handling and rendering. Exact code organization belongs in the spec.
- Automation means inventory plus bounded configuration assessments for every
  provider, not merely seven wrappers around manual instructions. The spec must
  enumerate API operations, selected fields, check predicates and permissions.
- Reports must distinguish observed absence from denied, unsupported, stale,
  truncated or uncollected evidence. A completed query is not proof of full
  account visibility or compliance. No synthetic compliance percentage.
- Explicitly model provider scope and the strength of identity verification.
  Do not force namespaces, zones and compartments into an AWS region model or
  claim a project identity was verified just because an API request succeeded.
- Bound requests, pagination, retries, response size and total runtime. Keep
  credentials out of argv, reports and logs. Whitelist persisted fields; exclude
  secret values, arbitrary manifests, workload logs and raw API responses.
- Preserve private, Git-ignored, atomic report publication, previous runs,
  customized skills and existing user task files. Runtime credentials remain
  outside Nix expressions and the Nix store. Use existing agenix helpers where
  applicable; do not require every provider to use the same authentication type.
- No cloud mutation, service activation, permission escalation, debug workloads,
  automatic remediation or automatic publication. Native recommendations may
  supplement deterministic checks only when already accessible.
- Offline tests must cover each provider and command entry point, including
  mismatched identity, denied reads, silent visibility limitations, pagination,
  malformed responses, timeouts, secret exclusion and exit-code propagation.
  Live validation requires explicit test scopes and must be reported separately.
- Scheduling, dashboards, automated report comparison, full compliance
  certification and exhaustive resource coverage are outside this task.

## Research observations and candidate coverage

Reviewed on 2026-09-16. These are inputs to the specification, not an approved
API or rule design. Provider limits must remain visible in the final reports.

| Provider | Candidate first-release evidence | Boundary to resolve in the spec |
|---|---|---|
| Azure | Resource Graph inventory; selected VM/network/storage properties; existing Advisor recommendations | Explicit tenant/subscriptions; Graph pagination and permission-filtered visibility; targeted reads for properties absent from Graph. |
| GCP | Cloud Asset Inventory; selected compute/firewall/storage configuration; existing recommendations where accessible | Explicit projects first; supported searchable asset types, API availability and impersonated identity; search metadata alone is insufficient for configuration checks. |
| OCI | Search plus selected compute/network/block/object-storage reads; existing Advisor findings | Explicit tenancy, compartments and regions; inspect/read permissions; Search covers only supported visible resources. |
| Kubernetes | Selected workloads, Services, Ingresses and NetworkPolicies; security contexts, probes, resource bounds and availability evidence | Explicit cluster identity/context/namespaces; cluster-wide reads separate; no Secrets, full manifests, logs, exec or node-collector jobs. Policy existence does not prove effective isolation. |
| Cloudflare | Explicit account/zones; selected DNS metadata and TLS settings; existing Security Center Insights | Token validity is not account ownership or complete zone access. Zone lists and Insights use different pagination shapes; do not persist DNS record content. |
| Hetzner | Servers, volumes, networks, firewalls and load balancers; backup/protection and selected ingress evidence | Establish project-token association without inventing an STS equivalent. Independently verify pagination and available identity evidence; Object Storage is separate coverage. |
| DigitalOcean | Account/project membership plus selected Droplet, firewall, volume and load-balancer reads; backup evidence | Project-resource listing silently omits resource types lacking token read scopes; project membership does not cover every team service. |

The AWS implementation has useful process execution, output protection and
publication logic, but `render`, `publish` and run metadata contain AWS-specific
assumptions. The specification must address report-schema compatibility before
extracting shared behavior. Prefer small shared functions and provider-specific
collectors over a plugin framework.

Official sources actually consulted:

- [Azure Resource Graph result limits and pagination](https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/work-with-data).
- [GCP resource search and scope](https://docs.cloud.google.com/asset-inventory/docs/search-resources).
- [OCI Search supported resources and required permissions](https://docs.oracle.com/en-us/iaas/Content/Search/Concepts/queryoverview.htm).
- [Kubernetes API list pagination and representation](https://kubernetes.io/docs/reference/using-api/api-concepts/).
- [Cloudflare official OpenAPI specification](https://github.com/cloudflare/api-schemas/blob/main/openapi.yaml): zone listing, token verification and Security Center Insights.
- [DigitalOcean official project-resource operation](https://github.com/digitalocean/openapi/blob/main/specification/resources/projects/projects_list_resources.yml): explicitly documents resource-scope omission.
- [Hetzner official client](https://github.com/hetznercloud/hcloud-go): reviewed as an access route to the official API ecosystem, not a proposed dependency.

Research limitation: web search authentication failed. Direct official pages and
official GitHub sources were used instead. Cloudflare/DigitalOcean documentation
pages returned HTTP 403; official specifications were available. The Hetzner API
reference returned a client-rendered page without usable API text; its exact
identity and pagination contract remains a specification-stage verification item.

## Open questions

No additional product preference is required to review this intent: all seven
providers and shell/direnv, just and flake entry points are in scope. The next
stage must resolve exact first-release rules, report-schema evolution, credential
and identity handling (especially Hetzner and Kubernetes), safe just argument
forwarding, packaging, and preservation of existing task files. These technical
decisions must be documented and approved before implementation.
