---
name: gcp
description: Google Cloud (GCP) best practices and architecture for writing, reviewing and deploying infrastructure in this project. Use whenever a task touches GCP, gcloud, the Terraform google or google-beta provider, IAM, service accounts, Workload Identity Federation, VPC / Shared VPC, GKE, Cloud Run, Cloud Storage, the resource hierarchy (organization, folders, projects), organization policy constraints, landing zones, the enterprise foundations blueprint, Fabric FAST, the Google Cloud Well-Architected Framework (operational excellence, security, reliability, cost optimization, performance, sustainability), cost or labels, or the gcloud MCP server. Covers Terraform with a GCS backend, ADC and service account impersonation instead of keys, agenix secrets, and the read-only MCP allow list.
---

# Google Cloud (GCP)

Last verified against Google documentation on 2026-09-15. All links below are
official Google sources; when a link and this text disagree, trust the link.

## What this project ships

The devenv shell provides `gcloud` (google-cloud-sdk with the
`gke-gcloud-auth-plugin` component), `terraform`, `tflint`, `trivy`,
`terraform-docs`, `infracost` and `nodejs`.

Extra gcloud components (`beta`, `alpha`, `cloud-sql-proxy`, ...) go in the
project's `devenv.nix` via `google-cloud-sdk.withExtraComponents`; never
run `gcloud components install` in a Nix-managed SDK, it is read-only
([components](https://docs.cloud.google.com/sdk/docs/components)).

Generic Terraform practice (layout, testing, CI) lives in the always-present
[terraform skill](../terraform/SKILL.md); this skill covers only what is
GCP-specific.

## Non-negotiables

Apply these on every change. Each one exists because the alternative is a
known incident class.

1. **No service account keys.** Authenticate with Application Default
   Credentials (`gcloud auth application-default login`), impersonate a
   service account (`gcloud config set auth/impersonate_service_account SA`,
   or `impersonate_service_account` in the provider), and use Workload
   Identity Federation from CI and GKE. Keys are long-lived bearer secrets
   that leak ([SA best practices](https://docs.cloud.google.com/iam/docs/best-practices-service-accounts),
   [ADC](https://docs.cloud.google.com/docs/authentication/provide-credentials-adc)).
   See [references/iam.md](references/iam.md).
2. **Least privilege, predefined roles before custom, never basic roles**
   (`roles/owner`, `roles/editor`, `roles/viewer` on projects) in Terraform
   ([Use IAM securely](https://docs.cloud.google.com/iam/docs/using-iam-securely)).
3. **Secrets live in agenix.** `secret-add NAME` to store,
   `secret-run --only NAME -- cmd` to use. Never `echo`, `cat`, log, or write
   a secret to disk or a `.tfvars` file. Runtime secrets belong in Secret
   Manager, referenced by resource name, not value
   ([Secret Manager](https://docs.cloud.google.com/secret-manager/docs/best-practices)).
4. **GCS remote state with versioning**, one state per environment,
   `prevent_destroy` on state buckets
   ([Store state](https://docs.cloud.google.com/docs/terraform/resource-management/store-state)).
   See [references/terraform.md](references/terraform.md).
5. **Labels are mandatory** on every labelable resource: at least `env`,
   `owner`, `cost-center`, `managed-by=terraform`. Lowercase keys, 63 chars,
   `[a-z0-9_-]`. Without labels billing export cannot attribute spend
   ([Labels](https://docs.cloud.google.com/resource-manager/docs/labels-overview)).
6. **Organization policies are guardrails, not suggestions.** Do not disable
   `iam.disableServiceAccountKeyCreation`, `compute.vmExternalIpAccess`,
   `storage.publicAccessPrevention`, `gcp.resourceLocations` or domain
   restriction to make a plan apply; fix the design
   ([Org policy constraints](https://docs.cloud.google.com/resource-manager/docs/organization-policy/org-policy-constraints)).
7. **Private by default.** Private GKE nodes, Cloud Run ingress internal
   unless public is a requirement, no external IPs on VMs, Private Google
   Access on subnets, uniform bucket-level access with public access
   prevention ([Private Google Access](https://docs.cloud.google.com/vpc/docs/private-google-access),
   [Public access prevention](https://docs.cloud.google.com/storage/docs/public-access-prevention)).

## Workflow

### Before writing infra

- Confirm the target: `gcloud config list` and `gcloud auth list`. Never
  assume the active project.
- Check the resource hierarchy and org policies that apply
  (`gcloud resource-manager org-policies list --project=P`) so the design
  fits the landing zone. See [references/landing-zone.md](references/landing-zone.md).
- Pick the region deliberately: latency, data residency
  (`gcp.resourceLocations`), and carbon
  ([Regions and zones](https://docs.cloud.google.com/compute/docs/regions-zones),
  [Carbon data](https://docs.cloud.google.com/sustainability/region-carbon)).

### Writing

- Follow the Google Terraform style guide: one resource type per file
  group, `variables.tf`/`outputs.tf`, `google_project_iam_member` not
  `_binding`/`_policy` unless you own the whole policy
  ([Style](https://docs.cloud.google.com/docs/terraform/best-practices/general-style-structure)).
- Prefer Google blueprints and `terraform-google-modules` over hand-rolled
  modules for projects, networks, GKE and IAM
  ([Blueprints](https://docs.cloud.google.com/docs/terraform/blueprints/terraform-blueprints)).
- Enable APIs explicitly with `google_project_service` and
  `disable_on_destroy = false`.

### Reviewing

Run the checklist in [references/well-architected.md](references/well-architected.md)
per pillar, then:

```sh
terraform fmt -check -recursive && terraform validate
tflint --recursive
trivy config .                    # misconfig scan, includes google checks
infracost breakdown --path .      # cost delta on the PR
```

### Deploying

```sh
terraform init       # GCS backend, ADC + impersonation
terraform plan -out=tfplan
terraform show -no-color tfplan | head -200   # read the diff, not just the summary
terraform apply tfplan
```

Never apply from a laptop to prod; CI applies with Workload Identity
Federation ([WIF with pipelines](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)).

## AI agent sessions

The gcloud MCP server has no read-only mode. The allow list in
`.mcp/gcloud-allow.json` filters command groups, but the real boundary is
identity: run agent sessions as a Viewer-only service account. Details and
the write opt-in are in [references/mcp.md](references/mcp.md).

## References

| File | Use when |
|------|----------|
| [well-architected.md](references/well-architected.md) | reviewing a design or PR against the six pillars |
| [landing-zone.md](references/landing-zone.md) | org, folders, projects, Shared VPC, logging, org policy, FAST / CFT |
| [iam.md](references/iam.md) | roles, service accounts, impersonation, WIF, deny policies |
| [cli-cheatsheet.md](references/cli-cheatsheet.md) | gcloud commands, filters, formats, GKE auth |
| [terraform.md](references/terraform.md) | google/google-beta providers, GCS backend, labels, CFT/Fabric modules, GCP gotchas |
| [mcp.md](references/mcp.md) | the gcloud MCP server, allow list, read-only enforcement |
