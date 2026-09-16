# Terraform on OCI (provider, state, tags, gotchas)

Verified 2026-09-15. This file is OCI-specific. Generic Terraform practice (module layout, pipelines, testing, review) lives in the always-installed [terraform skill](../../terraform/SKILL.md); follow it and layer the OCI rules below on top.

Provider: [`oracle/oci`](https://github.com/oracle/terraform-provider-oci), docs at [Terraform provider for OCI](https://docs.oracle.com/en-us/iaas/Content/dev/terraform/home.htm).

## Provider block and auth

```hcl
terraform {
  required_version = ">= 1.12"                            # native oci state backend
  required_providers {
    oci = { source = "oracle/oci", version = "~> 7.0" }   # pin the current major
  }
}

provider "oci" {
  auth                = var.oci_auth            # "SecurityToken" | "InstancePrincipal" | "ResourcePrincipal" | "OKEWorkloadIdentity" | "APIKey"
  config_file_profile = var.oci_profile         # only for SecurityToken / APIKey
  region              = var.region
}
```

- Humans: `auth = "SecurityToken"` with the profile created by `oci session authenticate`. Tokens expire after 1 hour, so Oracle advises against them for long provisioning runs; split big stacks or use a principal. [Configuring the provider](https://docs.oracle.com/en-us/iaas/Content/dev/terraform/configuring.htm)
- OCI-hosted CI: `auth = "InstancePrincipal"`; no config file needed. Dynamic group + policy in [iam.md](iam.md).
- Env-var equivalents: `TF_VAR_auth`/`OCI_AUTH`, `TF_VAR_config_file_profile`/`OCI_CONFIG_FILE_PROFILE`, `TF_VAR_region`/`OCI_REGION`. Precedence: env vars > named profile > DEFAULT profile.
- API keys: encrypted with agenix (`OCI_PRIVATE_KEY`) and supplied through a separately managed private runtime key-file path referenced by the profile/provider. `secret-run` injects environment values, not files; it does not create `TF_VAR_private_key_path`. Prefer security-token/principal authentication; never embed a key in HCL.
- State contains secrets (DB admin passwords, generated keys) regardless of `sensitive = true`. Treat the state bucket as a secret store. [Storing sensitive data](https://docs.oracle.com/en-us/iaas/Content/dev/terraform/storing-sensitive-data.htm)

## Remote state: native `oci` backend

Oracle recommends the native `oci` backend (Terraform >= 1.12) and marks the S3-compatible backend deprecated. The native backend locks state with Object Storage conditional writes and authenticates with the same principals as the provider, so no customer secret keys are needed. [Using Object Storage for state files](https://docs.oracle.com/en-us/iaas/Content/dev/terraform/object-storage-state.htm), [Backend type: oci](https://developer.hashicorp.com/terraform/language/backend/oci)

```hcl
terraform {
  backend "oci" {
    bucket              = "tfstate-prod"
    namespace           = "<namespace>"            # oci os ns get
    key                 = "network/terraform.tfstate"
    region              = "eu-frankfurt-1"
    auth                = "SecurityToken"          # or InstancePrincipal in CI
    config_file_profile = "prod"
    kms_key_id          = "ocid1.key.oc1..."       # customer-managed Vault key
  }
}
```

`auth` accepts `APIKey`, `SecurityToken`, `InstancePrincipal`, `InstancePrincipalWithCerts`, `ResourcePrincipal`, `OKEWorkloadIdentity`. Workspaces are prefixed with `workspace_key_prefix` (default `tf-state-env`).

Legacy S3-compatible backend (customer secret keys, no locking): only for Terraform < 1.12; config and endpoint format are in the [Oracle page above](https://docs.oracle.com/en-us/iaas/Content/dev/terraform/object-storage-state.htm). If you must use it, inject the key pair with `secret-run --only tfstate-s3 -- terraform init`; the secret key is shown once at creation. [S3 compatibility API](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/s3compatibleapi.htm)

Hosted alternative: OCI Resource Manager stacks run the same HCL with managed state, one-job-at-a-time locking, drift detection and rollback jobs. [Resource Manager](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/resourcemanager.htm)

### State bucket requirements

- Private bucket (`public_access_type = "NoPublicAccess"`), versioning enabled, customer-managed `kms_key_id`, in the `security` compartment.
- Policy: CI dynamic group `manage objects in compartment prod:security where target.bucket.name='tfstate-prod'`; humans `use`; `ro-agents` nothing (state holds secrets).
- One key prefix per stack (`network/`, `security/`, `appdev/`); never one state for the whole tenancy.

## Tags on every resource

Defined tags need a namespace created first; freeform tags are free text. Both are required by this project. [Tagging](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/taggingoverview.htm)

```hcl
locals {
  defined_tags = {
    "Ops.Env"        = var.env
    "Ops.Owner"      = var.owner
    "Ops.CostCenter" = var.cost_center
    "Ops.ManagedBy"  = "terraform"
  }
  freeform_tags = { repo = var.repo, stack = path.module }
}

resource "oci_core_vcn" "main" {
  compartment_id = var.network_compartment_id
  cidr_blocks    = ["10.10.0.0/16"]
  display_name   = "${var.env}-vcn"
  defined_tags   = local.defined_tags
  freeform_tags  = local.freeform_tags
}
```

Add `lifecycle { ignore_changes = [defined_tags["Oracle-Tags.CreatedBy"], defined_tags["Oracle-Tags.CreatedOn"]] }` where the tenancy auto-applies `Oracle-Tags`; otherwise every plan shows drift. Enforce presence with a `tflint` rule or a `validation` block on `var.owner`/`var.cost_center`. Tag namespaces belong in a bootstrap stack that runs before everything else.

## Compartments and policies as code

```hcl
resource "oci_identity_compartment" "appdev" {
  compartment_id = var.enclosing_compartment_id
  name           = "${var.env}-appdev"
  description    = "Application workloads (${var.env})"
  enable_delete  = false
  defined_tags   = local.defined_tags
}

resource "oci_identity_policy" "app_admins" {
  compartment_id = oci_identity_compartment.appdev.id
  name           = "${var.env}-app-admins"
  description    = "Compartment admins, MFA required"
  statements = [
    "Allow group ${var.env}-app-admins to manage all-resources in compartment ${oci_identity_compartment.appdev.name} where request.user.mfaTotpVerified='true'",
  ]
  defined_tags = local.defined_tags
}
```

IAM resources live in the home region; run identity stacks with `region = var.home_region`. [IAM overview](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/overview.htm)

## Reuse Oracle landing zone modules

Prefer the CIS-aligned modules over hand-written resources for foundation pieces, pinned by `ref` tag: [terraform-oci-modules-networking](https://github.com/oci-landing-zones/terraform-oci-modules-networking), [terraform-oci-modules-observability](https://github.com/oci-landing-zones/terraform-oci-modules-observability), [terraform-oci-modules-workloads](https://github.com/oci-landing-zones/terraform-oci-modules-workloads), orchestrated by [terraform-oci-modules-orchestrator](https://github.com/oci-landing-zones/terraform-oci-modules-orchestrator). Full foundation: [terraform-oci-core-landingzone](https://github.com/oci-landing-zones/terraform-oci-core-landingzone) (see [landing-zone.md](landing-zone.md)).

## OCI-specific pipeline steps

On top of the generic pipeline in the terraform skill:

```
terraform init -backend-config=env/prod.backend.hcl      # oci backend, token or principal
tflint --init && tflint --recursive
trivy config --severity HIGH,CRITICAL .
infracost breakdown --path . --format table
terraform plan -out plan.tfplan -var-file=env/prod.tfvars # SecurityToken profile, < 1 h
```

- Plan in PRs with a read-only principal where possible; apply only from a protected branch with the deploy principal (instance principal on an OCI runner).
- Run `terraform plan -detailed-exitcode` nightly, or Resource Manager drift detection, to catch console changes.

## OCI gotchas

- `401-NotAuthenticated` after ~1 h: security token expired. `oci session refresh --profile <p>` or switch to a principal.
- `404-NotAuthorizedOrNotFound`: usually a policy missing the compartment or verb, not a missing resource.
- Provider region vs. home region: IAM resources (compartments, groups, policies, tag namespaces) fail outside the home region.
- Tag namespace must exist before any `defined_tags` referencing it.
- Deleting a compartment requires it to be empty and `enable_delete = true`; leave `false` in prod.
- Policy changes take a short time to propagate; a plan right after creating a policy can still be denied.
- Resource principal tokens are cached 15 minutes; policy edits for Functions are not immediate. [Functions resource principals](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsaccessingociresources.htm)
