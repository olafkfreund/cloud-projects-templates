---
name: oci
description: Oracle Cloud Infrastructure (OCI) best practices and architecture for writing, reviewing and deploying infrastructure. Use when working with Oracle Cloud, OCI, the oci CLI, the Terraform oracle/oci provider, compartments, IAM policies (inspect/read/use/manage), VCN and DRG networking, OKE (Kubernetes Engine), Autonomous Database, Object Storage remote state, the CIS OCI Landing Zone, the OCI best practices (well-architected) framework, tagging, cost control, Cloud Guard, Security Zones, Vault, or the oci-cloud-mcp-server. Covers Terraform IaC with the native oci state backend, least-privilege policies, security-token and instance/resource principal auth, agenix-managed secrets, and a read-only agent profile.
---

# OCI skill

Last verified against Oracle docs: 2026-09-15. Every rule below links its official source.

## Toolchain in this devenv

| Tool | Use |
|------|-----|
| `oci` (oci-cli) | Query and manage resources; auth via `oci session authenticate` |
| `terraform` (>= 1.12) | Plan/apply with the `oracle/oci` provider; native `oci` state backend. Generic practice: [terraform skill](../terraform/SKILL.md) |
| `tflint`, `trivy`, `terraform-docs`, `infracost` | Lint, scan, document, price every change |
| `uv` / `uvx` | Runs `oracle.oci-cloud-mcp-server` (see [references/mcp.md](references/mcp.md)) |
| `secret-add NAME` / `secret-run --only NAME -- cmd` | agenix secrets; never print or write them to disk |

## Non-negotiable rules

1. **Compartments isolate; the root compartment stays empty.** Put every resource in a purpose compartment (network, security, app, db), max 6 levels deep, and scope policies to compartments, not `in tenancy`, unless the resource is tenancy-scoped (users, groups, budgets). Why: compartments are the unit of IAM, quotas, budgets and Security Zones. [Tenancy setup best practices](https://docs.oracle.com/en-us/iaas/Content/GSG/Concepts/settinguptenancy.htm)
2. **Least privilege with the right verb.** `inspect` < `read` < `use` < `manage`. Start at `inspect`/`read`, add `use` for operators, reserve `manage` for admins of one compartment. Never `Allow any-user` without a `where` clause. [Policy verbs](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/policyreference.htm), details in [references/iam.md](references/iam.md).
3. **No long-lived API keys on laptops or in CI.** Humans: `oci session authenticate` (1-hour security token, refreshable). Workloads: instance principals, resource principals or OKE workload identity. [Token-based auth](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/clitoken.htm), [Instance principals](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/callingservicesfrominstances.htm)
4. **Agents run read-only.** AI agent sessions use the `ro-agent` CLI profile bound to a group that only has `read all-resources`. The MCP server has no read-only switch; IAM is the boundary. [references/iam.md](references/iam.md), [references/mcp.md](references/mcp.md)
5. **Tags are mandatory.** Every resource gets defined tags from a governed namespace (e.g. `Ops.Owner`, `Ops.CostCenter`, `Ops.Env`) plus freeform tags for ad-hoc metadata. Enforce with tag defaults on compartments. Why: defined tags drive Cost Analysis, budgets and policy conditions; freeform tags cannot be governed. [Tagging overview](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/taggingoverview.htm)
6. **Remote, locked, encrypted state.** State lives in a private, versioned Object Storage bucket, never locally, using the native `oci` backend (Terraform >= 1.12, state locking, principal auth, Vault key). [references/terraform.md](references/terraform.md)
7. **Secrets never touch the repo or stdout.** Customer secret keys, private keys and DB passwords go in agenix (`secret-add`) and are injected with `secret-run --only NAME -- terraform plan`. In OCI, store runtime secrets in Vault. [Vault](https://docs.oracle.com/en-us/iaas/Content/KeyManagement/Concepts/keyoverview.htm)
8. **Private by default.** Private subnets, NSGs over security lists for tier-to-tier rules, service gateway for Oracle services, no public buckets, OKE API endpoint private, Autonomous Database on a private endpoint. [NSGs](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/networksecuritygroups.htm), [OKE security best practices](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengbestpractices_topic-Security-best-practices.htm)
9. **Cloud Guard on, Security Zones for regulated compartments, Audit exported.** Cloud Guard must be enabled before Security Zones. Audit logs keep 365 days; ship them out with Connector Hub for longer. [Cloud Guard](https://docs.oracle.com/en-us/iaas/cloud-guard/using/index.htm), [Security Zones](https://docs.oracle.com/en-us/iaas/security-zone/using/security-zones.htm), [Audit retention](https://docs.oracle.com/en-us/iaas/Content/Audit/Tasks/settingretentionperiod.htm)
10. **Budget every compartment.** Create a budget with an 80 % forecast alert per top-level compartment and act on Cloud Advisor cost findings weekly. [Budgets](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm), [Cloud Advisor](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Concepts/cloudadvisoroverview.htm)

## Workflow

### Before writing infra

- Read [references/well-architected.md](references/well-architected.md) for the pillar checks that apply.
- New tenancy or new environment? Start from the CIS Landing Zone, do not hand-roll: [references/landing-zone.md](references/landing-zone.md).
- Confirm target compartment OCID and region: `oci iam compartment list --compartment-id-in-subtree true --query 'data[].{name:name,id:id}' --output table`.

### Writing Terraform

```
terraform init && terraform fmt -check && terraform validate
tflint --recursive
trivy config .
infracost breakdown --path .
terraform plan -out plan.tfplan          # SecurityToken profile or principal; no keys in env
```

- Provider: `oracle/oci`, pinned `~> 7.0` (check current major). Auth: `auth = "SecurityToken"` + `config_file_profile` for humans, `InstancePrincipal`/`ResourcePrincipal` in OCI-hosted runners. Security tokens expire after one hour, so split long applies. [Provider configuration](https://docs.oracle.com/en-us/iaas/Content/dev/terraform/configuring.htm)
- Every resource sets `defined_tags` and `freeform_tags` via a shared `locals` block. See [references/terraform.md](references/terraform.md).
- Mark passwords and keys `sensitive = true`; the state file still holds them, so the state bucket is the secret boundary. [Storing sensitive data](https://docs.oracle.com/en-us/iaas/Content/dev/terraform/storing-sensitive-data.htm)

### Reviewing a change (checklist)

- [ ] Resource is in a non-root compartment and the compartment matches its function
- [ ] Policies use the least verb, name a compartment, and carry a `where` clause when scoped to tags or MFA
- [ ] No `0.0.0.0/0` ingress except on a public load balancer subnet; NSGs used between tiers
- [ ] No public bucket, no `is_public_ip_enabled = true` on non-bastion instances
- [ ] Encryption uses a customer-managed Vault key where Security Zones or compliance require it
- [ ] `defined_tags` and `freeform_tags` present on every resource
- [ ] `tflint`, `trivy config`, `infracost` outputs attached to the PR
- [ ] Plan was produced with a token/principal, not an API key; no credentials in the diff

### Deploying

- Humans: `oci session authenticate --profile-name <env> --region <region>` then `OCI_CLI_AUTH=security_token`.
- CI inside OCI: instance principal on the runner, dynamic group + policy scoped to the target compartment.
- Long applies (> 1 h): use a principal, not a security token.
- Alternative: OCI Resource Manager stacks give hosted state, locking and drift detection with the same HCL. [Resource Manager](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/resourcemanager.htm)

## Reference index

| File | What it covers |
|------|----------------|
| [references/well-architected.md](references/well-architected.md) | OCI best practices framework: 5 pillars, concrete checks per pillar |
| [references/landing-zone.md](references/landing-zone.md) | CIS Landing Zone, compartment and hub-spoke design, Cloud Guard, Security Zones, Vault, logging |
| [references/iam.md](references/iam.md) | Policy syntax, verbs, principals, read-only `ro-agents` policy and CLI profile |
| [references/cli-cheatsheet.md](references/cli-cheatsheet.md) | `oci` CLI auth, profiles, JMESPath queries, common read-only commands |
| [references/terraform.md](references/terraform.md) | `oracle/oci` provider auth, native `oci` state backend, tags, landing zone modules, OCI gotchas |
| [references/mcp.md](references/mcp.md) | `oci-cloud-mcp-server` configuration, auth, and the IAM-based read-only boundary |

Further official entry points: [OCI Security Guide](https://docs.oracle.com/en-us/iaas/Content/Security/Concepts/security_guide.htm), [Securing your tenancy](https://docs.oracle.com/en-us/iaas/Content/Security/Tasks/securing_your_tenancy.htm), [Service security best practices index](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/configuration_security.htm), [OCI security checklist](https://docs.oracle.com/en/solutions/oci-security-checklist).
