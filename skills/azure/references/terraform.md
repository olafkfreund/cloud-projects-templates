# Terraform on Azure: azurerm, azapi, state, identity, AVM

Verified 2026-09-15. This file is Azure-specific. Generic Terraform practice
(module layout, variables, testing, workspaces, CI) lives in the always-installed
[terraform skill](../../terraform/SKILL.md); read that first.
Microsoft entry point: [Terraform on Azure](https://learn.microsoft.com/en-us/azure/developer/terraform/),
[overview](https://learn.microsoft.com/en-us/azure/developer/terraform/overview),
[Terraform vs Bicep](https://learn.microsoft.com/en-us/azure/developer/terraform/comparing-terraform-and-bicep).

## Providers

Sources: [azurerm](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs),
[azapi](https://registry.terraform.io/providers/Azure/azapi/latest/docs),
[azuread](https://registry.terraform.io/providers/hashicorp/azuread/latest/docs),
[AzAPI overview](https://learn.microsoft.com/en-us/azure/developer/terraform/overview-azapi-provider),
[azurerm 4.0 upgrade guide](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/guides/4.0-upgrade-guide),
[features block](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/guides/features-block).

```hcl
terraform {
  required_version = ">= 1.9"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.0" }
    azapi   = { source = "Azure/azapi",       version = "~> 2.0" }
    azuread = { source = "hashicorp/azuread", version = "~> 3.0" }
  }
}

provider "azurerm" {
  features {
    key_vault      { purge_soft_delete_on_destroy = false } # keep prod vaults recoverable
    resource_group { prevent_deletion_if_contains_resources = true }
  }
  subscription_id                 = var.subscription_id   # required in azurerm 4.x
  resource_provider_registrations = "core"                # register only what you use
  storage_use_azuread             = true                  # data-plane calls via Entra ID
}
```

- `azurerm` for everything it supports. `azapi` for preview features and
  resources azurerm lacks; it maps 1:1 to the REST API so it never lags.
  `azuread` for groups, app registrations and federated credentials.
- Pass `subscription_id` explicitly; azurerm 4.x no longer guesses it from
  `az account`, which is exactly what stops a plan from landing in the wrong
  subscription.
- `resource_provider_registrations = "core"` (or `"none"` plus explicit
  `azurerm_resource_provider_registration`) replaces the old
  `skip_provider_registration`; registering all providers needs subscription
  Contributor and is slow.

## Authentication

Sources: [Authenticate Terraform to Azure](https://learn.microsoft.com/en-us/azure/developer/terraform/authenticate-to-azure),
[Azure CLI auth](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/guides/azure_cli),
[managed identity auth](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/guides/managed_service_identity),
[OIDC auth](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/guides/service_principal_oidc),
[GitHub OIDC](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect).

| Where | How | Env |
| --- | --- | --- |
| Laptop | `az login`, provider picks it up | `ARM_SUBSCRIPTION_ID` optional |
| GitHub Actions | `azure/login` with federated credential, then `use_oidc = true` | `ARM_USE_OIDC=true ARM_CLIENT_ID ARM_TENANT_ID ARM_SUBSCRIPTION_ID` |
| Azure-hosted runner / VM | `use_msi = true` | `ARM_USE_MSI=true`, `ARM_CLIENT_ID` for user-assigned |
| Last resort | client secret via `secret-run --only ARM_CLIENT_SECRET -- terraform plan` | never in `.tfvars` or `.env` |

Set the same flags in the backend block; the backend authenticates separately
from the provider.

## Remote state: azurerm backend with Entra ID

Sources: [Store state in Azure Storage](https://learn.microsoft.com/en-us/azure/developer/terraform/store-state-in-azure-storage),
[azurerm backend reference](https://developer.hashicorp.com/terraform/language/backend/azurerm),
[Prevent Shared Key authorization](https://learn.microsoft.com/en-us/azure/storage/common/shared-key-authorization-prevent),
[Blob data protection](https://learn.microsoft.com/en-us/azure/storage/blobs/data-protection-overview),
[versioning](https://learn.microsoft.com/en-us/azure/storage/blobs/versioning-overview),
[soft delete](https://learn.microsoft.com/en-us/azure/storage/blobs/soft-delete-blob-overview).

```hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "rg-tfstate-prod-weu"
    storage_account_name = "sttfstateprodweu"
    container_name       = "tfstate"
    key                  = "app/prod.tfstate"
    use_azuread_auth     = true   # Entra ID data-plane auth; no ARM_ACCESS_KEY
    use_oidc             = true   # only in CI; omit locally, az login is used
  }
}
```

Why: Microsoft's own how-to uses a storage key for simplicity and says to
"evaluate the available authentication options" for production. The key grants
full account access and cannot be scoped; an Entra ID role can. The backend
docs recommend *Storage Blob Data Contributor* on the container as the
least-privilege role for `use_azuread_auth`.

State account checklist:

- [ ] `allow_shared_key_access = false`, `allow_nested_items_to_be_public = false`,
      `min_tls_version = "TLS1_2"`, `https_traffic_only_enabled = true`
- [ ] Blob versioning and soft delete (30 days) on the container; state history
      is your undo button
- [ ] Network rules: deny by default, allow the CI runner egress and the office;
      private endpoint if the runner is in a VNet
- [ ] `lifecycle { prevent_destroy = true }` on the account and container
- [ ] One container per environment or one `key` prefix per workload; never
      share a key between environments
- [ ] State locking is automatic (blob lease); if a lease sticks after a crashed
      run, `terraform force-unlock <id>` after confirming nobody else is running
- [ ] `terraform state pull` output contains secrets; never commit or paste it

Bootstrap once with `az` (or a tiny local-state Terraform root), then never touch it
by hand:

```bash
az group create -n rg-tfstate-prod-weu -l westeurope --tags environment=prod managed-by=terraform
az storage account create -n sttfstateprodweu -g rg-tfstate-prod-weu -l westeurope \
  --sku Standard_ZRS --kind StorageV2 --min-tls-version TLS1_2 --allow-blob-public-access false \
  --allow-shared-key-access false --https-only true
az storage account blob-service-properties update --account-name sttfstateprodweu \
  --enable-versioning true --enable-delete-retention true --delete-retention-days 30
az storage container create -n tfstate --account-name sttfstateprodweu --auth-mode login
az role assignment create --role "Storage Blob Data Contributor" \
  --assignee-object-id "$DEPLOYERS_GROUP_ID" --assignee-principal-type Group \
  --scope "$(az storage account show -n sttfstateprodweu -g rg-tfstate-prod-weu --query id -o tsv)/blobServices/default/containers/tfstate"
```

## Azure Verified Modules

Sources: [AVM](https://azure.github.io/Azure-Verified-Modules/),
[Terraform module index](https://azure.github.io/Azure-Verified-Modules/indexes/terraform/),
[AVM Terraform spec](https://azure.github.io/Azure-Verified-Modules/specs/tf/),
[Azure/naming](https://registry.terraform.io/modules/Azure/naming/azurerm/latest).

Prefer an AVM `avm-res-*` module over a bare resource once you need private
endpoints, diagnostic settings, RBAC, locks or customer-managed keys: the module
exposes them as standard interfaces (`private_endpoints`, `diagnostic_settings`,
`role_assignments`, `lock`, `managed_identities`) so every module reads the
same way. Pin every module version.

| Module | Use |
| --- | --- |
| [Azure/avm-res-storage-storageaccount](https://registry.terraform.io/modules/Azure/avm-res-storage-storageaccount/azurerm/latest) | Storage accounts with secure defaults |
| [Azure/avm-res-keyvault-vault](https://registry.terraform.io/modules/Azure/avm-res-keyvault-vault/azurerm/latest) | Key Vault, RBAC model, purge protection |
| [Azure/avm-res-network-virtualnetwork](https://registry.terraform.io/modules/Azure/avm-res-network-virtualnetwork/azurerm/latest) | VNet, subnets, peering |
| [Azure/avm-res-containerservice-managedcluster](https://registry.terraform.io/modules/Azure/avm-res-containerservice-managedcluster/azurerm/latest) | AKS with Entra ID, workload identity, node pools |
| [Azure/lz-vending](https://registry.terraform.io/modules/Azure/lz-vending/azurerm/latest) | Subscription vending (platform team) |

```hcl
module "kv" {
  source  = "Azure/avm-res-keyvault-vault/azurerm"
  version = "0.10.0"   # pin; check the registry for the current release
  name                = "kv-app-prod-weu"
  location            = azurerm_resource_group.app.location
  resource_group_name = azurerm_resource_group.app.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  public_network_access_enabled = false
  role_assignments = {
    app = { role_definition_id_or_name = "Key Vault Secrets User", principal_id = azurerm_user_assigned_identity.app.principal_id }
  }
  tags = local.tags
}
```

## Identity resources

Sources: [user_assigned_identity](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/user_assigned_identity),
[federated_identity_credential](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/federated_identity_credential),
[role_assignment](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/role_assignment),
[kubernetes_cluster](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/kubernetes_cluster).

```hcl
resource "azurerm_user_assigned_identity" "ci" {
  name = "id-app-ci-prod" location = var.location resource_group_name = azurerm_resource_group.app.name tags = local.tags
}
resource "azurerm_federated_identity_credential" "gh_main" {
  name = "github-main" resource_group_name = azurerm_resource_group.app.name parent_id = azurerm_user_assigned_identity.ci.id
  audience = ["api://AzureADTokenExchange"] issuer = "https://token.actions.githubusercontent.com"
  subject  = "repo:${var.github_repo}:ref:refs/heads/main"
}
resource "azurerm_role_assignment" "ci_rg" {
  scope = azurerm_resource_group.app.id role_definition_name = "Contributor"
  principal_id = azurerm_user_assigned_identity.ci.principal_id principal_type = "ServicePrincipal"
}
```

Set `principal_type` on role assignments; it skips the Graph lookup and avoids
the eventual-consistency `PrincipalNotFound` error on fresh identities.

## Azure gotchas

- **Tags:** define `local.tags` once and pass it everywhere; add
  `ignore_changes = [tags["created-date"]]` for tags Policy `modify` effects inject,
  or the plan is never clean ([tag resources](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/tag-resources)).
- **Names:** storage accounts are 3 to 24 lowercase alphanumerics and globally
  unique; Key Vault names are global too. Use `Azure/naming` or validate against
  [resource name rules](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/resource-name-rules).
- **Soft delete:** Key Vault and some others cannot be recreated with the same
  name right after destroy; recover or purge first (Policy may forbid purge).
- **Storage account conversions** (LRS to ZRS) happen outside Terraform and can
  trigger a destroy/recreate plan; see the warning in
  [store state in Azure Storage](https://learn.microsoft.com/en-us/azure/developer/terraform/store-state-in-azure-storage)
  and `prevent_destroy` stateful resources.
- **Locks:** a `CanNotDelete` lock on a resource group makes `terraform destroy`
  fail by design; remove the lock deliberately, never with `ignore_changes`
  ([lock resources](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/lock-resources)).
- **Policy deny at apply time:** a `RequestDisallowedByPolicy` error means the
  landing zone rejected the resource; fix the code (region, SKU, public access,
  tags), do not request an exemption first
  ([policy effects](https://learn.microsoft.com/en-us/azure/governance/policy/concepts/effect-basics),
  [exemptions](https://learn.microsoft.com/en-us/azure/governance/policy/concepts/exemption-structure)).
- **Importing brownfield:** use
  [Azure Export for Terraform](https://learn.microsoft.com/en-us/azure/developer/terraform/azure-export-for-terraform/export-terraform-overview)
  (`aztfexport`) rather than hand-written `import` blocks for more than a few resources.
- **AKS:** `default_node_pool` changes often force replacement; put workloads on
  additional node pools and keep the system pool small. Enable
  `azure_active_directory_role_based_access_control`, `oidc_issuer_enabled`,
  `workload_identity_enabled`, and `local_account_disabled = true`.
- **Provider drift:** track breaking changes in the
  [azurerm version history](https://learn.microsoft.com/en-us/azure/developer/terraform/provider-version-history-azurerm).
  Common errors: [troubleshoot Terraform on Azure](https://learn.microsoft.com/en-us/azure/developer/terraform/troubleshoot).

## Testing on Azure

Sources: [testing overview](https://learn.microsoft.com/en-us/azure/developer/terraform/best-practices-testing-overview),
[integration testing](https://learn.microsoft.com/en-us/azure/developer/terraform/best-practices-integration-testing),
[compliance testing](https://learn.microsoft.com/en-us/azure/developer/terraform/best-practices-compliance-testing),
[end-to-end testing](https://learn.microsoft.com/en-us/azure/developer/terraform/best-practices-end-to-end-testing).

Minimum for every PR: `terraform fmt -check`, `terraform validate`, `tflint`
(with the azurerm ruleset), `trivy config .`, `terraform plan` posted to the PR,
`infracost diff`. Run `terraform apply` in an ephemeral sandbox subscription for
modules, then `destroy` in the same job.
