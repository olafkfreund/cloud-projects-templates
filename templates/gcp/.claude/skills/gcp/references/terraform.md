# Terraform on Google Cloud: the GCP-specific parts

Verified 2026-09-15. Generic Terraform practice (layout, style, testing,
CI, state hygiene) is in the [terraform skill](../../terraform/SKILL.md);
this file covers only what changes because the target is Google Cloud.
Primary sources:
[Google Terraform best practices](https://docs.cloud.google.com/docs/terraform/best-practices/general-style-structure),
[google provider](https://registry.terraform.io/providers/hashicorp/google/latest/docs),
[google-beta provider](https://registry.terraform.io/providers/hashicorp/google-beta/latest/docs),
[GCS backend](https://developer.hashicorp.com/terraform/language/backend/gcs).

## Providers: google and google-beta

[Provider versions guide](https://registry.terraform.io/providers/hashicorp/google/latest/docs/guides/provider_versions)

- `google` exposes GA APIs; `google-beta` exposes beta fields and
  resources. Declare both, pin them to the same major, and use
  `provider = google-beta` only on the resource that needs a beta field.
  Mixing versions across the two providers is a common source of
  plan-time drift.
- Authenticate with ADC plus impersonation locally, Workload Identity
  Federation in CI. Never `credentials = file("key.json")`
  ([Terraform authentication](https://docs.cloud.google.com/docs/terraform/authentication),
  [Provider reference](https://registry.terraform.io/providers/hashicorp/google/latest/docs/guides/provider_reference)).

```hcl
terraform {
  required_version = ">= 1.9"
  required_providers {
    google      = { source = "hashicorp/google",      version = "~> 6.0" }
    google-beta = { source = "hashicorp/google-beta", version = "~> 6.0" }
  }
}

provider "google" {
  project                     = var.project_id
  region                      = var.region
  impersonate_service_account = var.terraform_sa   # sa-terraform-<env>@...
  default_labels = {
    env        = var.env
    owner      = var.owner
    managed-by = "terraform"
  }
}

provider "google-beta" {
  project                     = var.project_id
  region                      = var.region
  impersonate_service_account = var.terraform_sa
  default_labels              = { env = var.env, owner = var.owner, managed-by = "terraform" }
}
```

`default_labels` labels every labelable resource the provider creates,
which is how the mandatory-label rule is enforced without repeating
`labels` blocks ([Labels](https://docs.cloud.google.com/resource-manager/docs/labels-overview)).
Some resources (Cloud Run v2, GKE node pools) use `labels` on nested
blocks; check the resource docs when a label is missing.

## Remote state in GCS

[Store state remotely](https://docs.cloud.google.com/docs/terraform/resource-management/store-state),
[GCS backend](https://developer.hashicorp.com/terraform/language/backend/gcs),
[Object versioning](https://docs.cloud.google.com/storage/docs/object-versioning)

```hcl
terraform {
  backend "gcs" {
    bucket = "tfstate-ORG-ENV"     # created by bootstrap, not by this root
    prefix = "app/env"             # one prefix per root module
  }
}
```

The GCS backend locks natively; no lock table is needed. State bucket
requirements (from the bootstrap stage):

- Object versioning on, so a bad apply can be rolled back to the previous
  state object.
- Uniform bucket-level access, public access prevention, CMEK if policy
  requires it, `lifecycle { prevent_destroy = true }`.
- Only the CI SA and the impersonated Terraform SA hold
  `roles/storage.objectAdmin`; humans read through impersonation.
- State holds secrets in plaintext. Treat the bucket as a secret store
  ([Security](https://docs.cloud.google.com/docs/terraform/best-practices/security)).

Pass per-environment values with `-backend-config` rather than committing
a `bucket` per root when roots are shared.

## GCP gotchas

- **IAM resources are authoritative or additive.** `google_project_iam_member`
  adds one grant; `_binding` replaces every member of a role; `_policy`
  replaces the whole policy and deletes grants made elsewhere (including
  Google-managed service agents). Default to `_member`
  (see [iam.md](iam.md)).
- **APIs must be enabled first.** `google_project_service` with
  `disable_on_destroy = false`; disabling an API on destroy takes down
  other stacks in the same project. Add `depends_on` from resources to the
  service they need on a fresh project.
- **Eventual consistency.** New service accounts and IAM grants take
  seconds to propagate; a `time_sleep` after SA creation avoids the classic
  403 on first apply.
- **Project deletion is soft.** Deleted projects sit for 30 days and their
  IDs cannot be reused; generate IDs with a random suffix.
- **Default network and default SAs.** Enforce
  `compute.skipDefaultNetworkCreation` and remove the Editor grant from the
  default compute SA in the project factory, or the org policy will reject
  the project.
- **Shared VPC ordering.** Host project, then service project attachment,
  then `roles/compute.networkUser` on the subnet, then the workload.
- **Region vs zone.** GKE, Cloud Run and MIGs are regional; disks and single
  VMs are zonal. Prefer regional resources
  ([Regional/zonal](https://docs.cloud.google.com/compute/docs/regions-zones/global-regional-zonal-resources)).
- **Secrets.** Never in `.tfvars`. Read with
  `google_secret_manager_secret_version` data sources, or inject via
  `secret-run --only NAME -- terraform apply` as `TF_VAR_name` with
  `sensitive = true`. It still lands in state.
- **`prevent_destroy`** on Cloud SQL, buckets with data, KMS keys, the
  state bucket.

## Modules to reuse

[Blueprints](https://docs.cloud.google.com/docs/terraform/blueprints/terraform-blueprints)

| Need | Module |
|------|--------|
| project creation with APIs, SAs, budgets | [terraform-google-project-factory](https://github.com/terraform-google-modules/terraform-google-project-factory) |
| VPC, subnets, routes, NAT | [terraform-google-network](https://github.com/terraform-google-modules/terraform-google-network) |
| full landing zone | [terraform-example-foundation](https://github.com/terraform-google-modules/terraform-example-foundation) or [Fabric FAST](https://github.com/GoogleCloudPlatform/cloud-foundation-fabric/tree/master/fast) |
| composable building blocks | [cloud-foundation-fabric modules](https://github.com/GoogleCloudPlatform/cloud-foundation-fabric) |

Pin module versions with `?ref=vX.Y.Z`. Vendor the module if the upstream
release cadence is a risk.

## Importing and exporting

- Import existing resources instead of recreating them
  ([Import](https://docs.cloud.google.com/docs/terraform/resource-management/import)).
- Bulk export a project to HCL with Config Connector export
  ([Export](https://docs.cloud.google.com/docs/terraform/resource-management/export)).
- Infrastructure Manager is Google's hosted apply service if runs and
  state should live inside Google Cloud
  ([Infra Manager](https://docs.cloud.google.com/infrastructure-manager/docs/overview)).

## Local workflow

```sh
gcloud config set auth/impersonate_service_account sa-terraform-dev@PROJECT.iam.gserviceaccount.com
terraform init -backend-config=env/dev.gcsbackend
terraform fmt -check -recursive && terraform validate
tflint --recursive          # google ruleset
trivy config .
terraform plan -var-file=env/dev.tfvars -out=tfplan
terraform show tfplan       # read it; look for destroy and replace
infracost diff --path . --compare-to=infracost-base.json
terraform apply tfplan      # CI only for prod, via WIF
```

## Review checklist

- [ ] `backend "gcs"` present; state bucket versioned and locked down.
- [ ] Provider uses `impersonate_service_account` or WIF; no `credentials`.
- [ ] `google` and `google-beta` pinned to the same major.
- [ ] `default_labels` set; required labels present.
- [ ] No basic roles; IAM via `_member`.
- [ ] `google_project_service` with `disable_on_destroy = false`.
- [ ] No public ingress, external IPs or public buckets without a comment
      naming the requirement.
- [ ] `prevent_destroy` on stateful resources.
- [ ] Plan output reviewed for `destroy` / `must be replaced`.
- [ ] `infracost` diff attached to the PR.
