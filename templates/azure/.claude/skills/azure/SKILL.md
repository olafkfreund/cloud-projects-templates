---
name: azure
description: Azure best practices and architecture for writing, reviewing and deploying infrastructure with az CLI, Bicep, Terraform (azurerm, azapi, AVM modules), Entra ID, RBAC, managed identities and workload identity federation, AKS, Container Apps, Azure Policy, cost management and the Azure MCP server. Applies the Well-Architected Framework, Cloud Adoption Framework (CAF) Ready phase and the Azure landing zone (management groups, subscription vending, hub-spoke / Virtual WAN). Use whenever a task touches Azure resources, an azurerm provider block, a .bicep file, `az` commands, Entra ID app registrations or service principals, AKS/kubelogin, remote state in Azure Storage, tags, policy or Azure spend.
---

# Azure

Date of last verification: 2026-09-15. Every claim below links to the official
Microsoft source. Prefer the linked page over memory when they disagree.

## When to apply

Apply this skill when you write, review or deploy anything that ends up in an
Azure subscription: Terraform with `azurerm`/`azapi`/`azuread`, Bicep,
`az` commands, AKS manifests that depend on Azure identity, GitHub Actions that
log in to Azure, or a cost or security review of an existing environment.

## Tools in this devenv shell

| Tool | Use it for |
| --- | --- |
| `az` (azure-cli + `aks-preview` extension; `az containerapp` is core) | Login, queries, one-off operations, `az deployment ... what-if` |
| `bicep` | Author and lint Bicep; `az bicep` also works |
| `kubelogin` | Entra ID auth to AKS with `az aks get-credentials` |
| `azure-mcp` | Read-only MCP server for agent sessions, see [references/mcp.md](references/mcp.md) |
| `terraform` | IaC engine; generic practice in the `terraform` skill, Azure specifics in [references/terraform.md](references/terraform.md) |
| `tflint`, `trivy`, `terraform-docs`, `infracost` | Lint, scan, document and price IaC before `apply` |

Not in the shell: `azd` (not in nixpkgs). If a task needs it, install it outside
the project following [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd).
Opt-in: `azure-functions-core-tools` (add to `packages` in `devenv.nix`,
see [Develop Functions locally](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local)).

## Project conventions (non-negotiable)

1. **Terraform with the `azurerm` provider.** Pin `hashicorp/azurerm` with `~>`,
   keep the `features {}` block present. Azure specifics in [references/terraform.md](references/terraform.md).
2. **Remote state in Azure Storage with Entra ID auth.** Backend `azurerm` with
   `use_azuread_auth = true`; the caller holds *Storage Blob Data Contributor* on the
   container. Never fetch or export a storage account key (`ARM_ACCESS_KEY`), and set
   `allow_shared_key_access = false` on the state account
   ([Prevent Shared Key authorization](https://learn.microsoft.com/en-us/azure/storage/common/shared-key-authorization-prevent)).
3. **Log in with `az login`.** Local `terraform`, `bicep`, `kubelogin` and `azure-mcp`
   all reuse the Azure CLI token
   ([Authenticate with Azure CLI](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli)).
   Select the subscription with `az account set --subscription <id>`.
4. **No client secrets where avoidable.** Order of preference: managed identity,
   workload identity federation (OIDC from GitHub Actions or AKS), then a
   certificate. A client secret is the last resort and must be stored with agenix
   ([Managed identities](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview),
   [Workload identity federation](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation)).
5. **Secrets live in agenix.** `secret-add NAME` to store, `secret-run --only NAME -- cmd`
   to use. Never `echo`, `cat`, log, write to `.env` or paste a secret into a file.
   `ARM_CLIENT_SECRET` and Key Vault values follow the same rule.
6. **Least-privilege RBAC.** Assign built-in roles to groups at the narrowest scope
   that works; no `Owner` on subscriptions for workloads
   ([RBAC best practices](https://learn.microsoft.com/en-us/azure/role-based-access-control/best-practices)).
7. **Mandatory tags** on every resource group and taggable resource: `environment`,
   `owner`, `cost-center`, `project`, `managed-by=terraform`. Enforce with Azure Policy,
   not code review ([Tagging strategy](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-tagging)).
8. **Azure Policy is the guardrail.** Deny public storage, require tags, allow only
   approved regions and SKUs. Policy assignments belong at management-group scope
   ([Azure Policy overview](https://learn.microsoft.com/en-us/azure/governance/policy/overview)).
9. **Naming** follows CAF abbreviations: `rg-<workload>-<env>-<region>`, `st<workload><env><region>`
   ([Naming](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-naming),
   [Abbreviations](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-abbreviations)).

## Workflow: change infrastructure

1. `az account show` to confirm tenant and subscription. Wrong subscription is the
   most expensive mistake an agent can make.
2. Read the existing code and state before adding resources; reuse an existing
   resource group, VNet or identity where one exists.
3. Write the change. Prefer an [Azure Verified Module](https://azure.github.io/Azure-Verified-Modules/)
   over a hand-rolled resource for anything with more than a handful of arguments.
4. `terraform fmt -recursive && terraform validate && tflint && trivy config .`
   For Bicep: `bicep build --stdout main.bicep >/dev/null && bicep lint main.bicep`.
5. `terraform plan -out=tfplan` or `az deployment group what-if`. Read every `destroy`
   and `replace`. Stop and ask before applying either
   ([What-if](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-what-if)).
6. `infracost breakdown --path .` when the change adds compute, storage or a
   database, and report the delta.
7. Apply only after the human confirms. Never `-auto-approve` in a shared subscription.
8. Verify: `az resource list -g <rg> -o table`, then check the Policy compliance
   state (`az policy state list -g <rg> --filter "complianceState eq 'NonCompliant'"`).

## Review checklist

- [ ] Identity: managed identity or federated credential, no `client_secret` in code
- [ ] RBAC: built-in role, group principal, resource or resource-group scope
- [ ] Network: no public IP or `0.0.0.0/0` NSG rule without a written reason;
      private endpoints for PaaS data services
      ([Networking](https://learn.microsoft.com/en-us/azure/well-architected/security/networking))
- [ ] Storage: `allow_nested_items_to_be_public = false`, shared key disabled,
      `min_tls_version = "TLS1_2"`, soft delete and versioning on
- [ ] Key Vault: RBAC permission model, purge protection on, soft delete on
      ([Key Vault best practices](https://learn.microsoft.com/en-us/azure/key-vault/general/best-practices))
- [ ] AKS: Entra ID integration + Azure RBAC, workload identity, private cluster or
      authorised IP ranges, ACR via managed identity
      ([AKS best practices](https://learn.microsoft.com/en-us/azure/aks/best-practices))
- [ ] Tags present, names follow CAF, region is an approved one
- [ ] Zone redundancy for anything with an SLA
      ([Regions and availability zones](https://learn.microsoft.com/en-us/azure/well-architected/reliability/regions-availability-zones))
- [ ] Diagnostic settings send logs to a Log Analytics workspace
- [ ] A budget with an alert exists for the subscription
      ([Budgets](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets))
- [ ] `terraform plan` shows no unexpected `replace`; state backend uses Entra ID auth

## References

- [references/well-architected.md](references/well-architected.md): five pillars with concrete checks
- [references/landing-zone.md](references/landing-zone.md): CAF Ready, ALZ architecture, management groups, subscription vending, hub-spoke vs Virtual WAN, AVM and ALZ Terraform modules
- [references/iam.md](references/iam.md): Entra ID, RBAC, managed identities, workload identity federation, PIM
- [references/cli-cheatsheet.md](references/cli-cheatsheet.md): `az`, `bicep`, `kubelogin` commands you actually need
- [references/terraform.md](references/terraform.md): azurerm/azapi provider, Entra ID state backend, OIDC, AVM modules, Azure gotchas
- [references/mcp.md](references/mcp.md): the `azure-mcp` server, read-only by default
- [../terraform/SKILL.md](../terraform/SKILL.md): generic Terraform practice (always installed alongside this skill)

Framework entry points: [Well-Architected Framework](https://learn.microsoft.com/en-us/azure/well-architected/),
[Cloud Adoption Framework](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/),
[Azure landing zone](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/).
