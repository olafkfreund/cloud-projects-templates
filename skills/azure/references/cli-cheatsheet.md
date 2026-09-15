# az, bicep and kubelogin cheatsheet

Verified 2026-09-15. Reference: [Azure CLI docs](https://learn.microsoft.com/en-us/cli/azure/),
[command index](https://learn.microsoft.com/en-us/cli/azure/reference-index),
[tips for using the CLI successfully](https://learn.microsoft.com/en-us/cli/azure/use-azure-cli-successfully-tips).
Every `az` command accepts `-o table|json|tsv|yaml` and `--query <JMESPath>`
([Output formats](https://learn.microsoft.com/en-us/cli/azure/format-output-azure-cli),
[Query with JMESPath](https://learn.microsoft.com/en-us/cli/azure/query-azure-cli)).
Use `-o tsv --query` for values you pipe into a variable; `-o json` when a human
or `jq` reads it. Add `--only-show-errors` in scripts.

## Login and context

Source: [Authenticate](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli),
[interactive](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli-interactively),
[managed identity](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli-managed-identity),
[service principal](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli-service-principal),
[manage subscriptions](https://learn.microsoft.com/en-us/cli/azure/manage-azure-subscriptions-azure-cli),
[CLI configuration](https://learn.microsoft.com/en-us/cli/azure/azure-cli-configuration).

```bash
az login                                    # browser; add --use-device-code on a headless box
az login --tenant <tenant-id>               # pick the tenant explicitly when you have several
az login --identity                         # on a VM / Container App with a managed identity
az login --service-principal --username "$ARM_CLIENT_ID" --tenant "$ARM_TENANT_ID" \
         --federated-token "$(cat "$AZURE_FEDERATED_TOKEN_FILE")"   # OIDC, no secret
az account show -o table                    # ALWAYS check before changing anything
az account list -o table
az account set --subscription <id-or-name>
az config set core.output=table defaults.location=westeurope   # per-machine defaults
az logout
```

A service-principal login with `--password` needs the secret: run it as
`secret-run --only ARM_CLIENT_SECRET -- az login --service-principal ... --password "$ARM_CLIENT_SECRET"`
and prefer the federated-token form above whenever possible.

## Extensions

Source: [Extensions overview](https://learn.microsoft.com/en-us/cli/azure/azure-cli-extensions-overview),
[available extensions](https://learn.microsoft.com/en-us/cli/azure/azure-cli-extensions-list).
`aks-preview` is built into this shell's `az`. Core `az containerapp` commands work without the `containerapp` extension, which is omitted until its nixpkgs build is fixed.

```bash
az extension list -o table
az config set extension.use_dynamic_install=yes_without_prompt   # auto-install missing ones
```

## Discover and query

Source: [az resource](https://learn.microsoft.com/en-us/cli/azure/resource),
[az group](https://learn.microsoft.com/en-us/cli/azure/group),
[Resource Graph](https://learn.microsoft.com/en-us/azure/governance/resource-graph/first-query-azurecli),
[starter queries](https://learn.microsoft.com/en-us/azure/governance/resource-graph/samples/starter),
[az tag](https://learn.microsoft.com/en-us/cli/azure/tag), [az lock](https://learn.microsoft.com/en-us/cli/azure/lock).

```bash
az group list -o table
az resource list -g <rg> -o table
az resource list --tag environment=prod --query "[].{name:name,type:type}" -o table
az graph query -q "Resources | where tags['owner'] == '' or isnull(tags['owner']) | project name, type, resourceGroup"
az graph query -q "Resources | summarize count() by type | order by count_ desc"
az tag list --resource-id "/subscriptions/$SUB/resourceGroups/<rg>"
az lock create -n no-delete -g <rg> --lock-type CanNotDelete       # on prod RGs
az monitor activity-log list -g <rg> --offset 1d -o table          # who changed what
```

## Bicep and ARM deployments

Source: [Bicep overview](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/overview),
[Bicep CLI](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/bicep-cli),
[deploy with CLI](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-cli),
[what-if](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-what-if),
[linter](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/linter),
[parameter files](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/parameter-files),
[modules](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/modules),
[best practices](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/best-practices),
[deployment stacks](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deployment-stacks).

```bash
bicep build main.bicep                      # compiles to main.json, fails on errors
bicep lint main.bicep
bicep format main.bicep
bicep decompile template.json               # ARM JSON -> Bicep starting point
az deployment group what-if  -g <rg> -f main.bicep -p main.bicepparam
az deployment group create   -g <rg> -f main.bicep -p main.bicepparam -n deploy-$(date +%Y%m%d-%H%M)
az deployment sub what-if    -l westeurope -f main.bicep       # subscription-scope (RGs, policy)
az deployment group list -g <rg> -o table
az stack group create -n app -g <rg> -f main.bicep --action-on-unmanage deleteResources --deny-settings-mode denyDelete
```

Why deployment stacks: they track what a template created and can delete
drift and block manual deletion, which plain deployments cannot. Use them for
Bicep-managed environments that are not under Terraform.

## AKS and kubelogin

Source: [az aks](https://learn.microsoft.com/en-us/cli/azure/aks),
[AKS quickstart](https://learn.microsoft.com/en-us/azure/aks/learn/quick-kubernetes-deploy-cli),
[kubelogin](https://learn.microsoft.com/en-us/azure/aks/kubelogin-authentication),
[private clusters](https://learn.microsoft.com/en-us/azure/aks/private-clusters).

```bash
az aks list -o table
az aks show -g <rg> -n <aks> --query "{k8s:kubernetesVersion,rbac:aadProfile.enableAzureRbac,oidc:oidcIssuerProfile.issuerUrl}"
az aks get-credentials -g <rg> -n <aks>                 # writes kubeconfig with Entra ID exec plugin
kubelogin convert-kubeconfig -l azurecli                # reuse the az login token, no device code
kubectl get nodes                                       # first call triggers auth
az aks get-versions -l westeurope -o table
az aks upgrade -g <rg> -n <aks> --kubernetes-version <v> --control-plane-only
az aks nodepool list -g <rg> --cluster-name <aks> -o table
az aks command invoke -g <rg> -n <aks> --command "kubectl get pods -A"   # private cluster, no VPN
```

Never use `az aks get-credentials --admin` outside break-glass; it bypasses
Entra ID and Azure RBAC.

## Container Apps, ACR, Functions, Web Apps

Source: [az containerapp](https://learn.microsoft.com/en-us/cli/azure/containerapp),
[Container Apps get started](https://learn.microsoft.com/en-us/azure/container-apps/get-started),
[az acr](https://learn.microsoft.com/en-us/cli/azure/acr),
[az functionapp](https://learn.microsoft.com/en-us/cli/azure/functionapp),
[az webapp](https://learn.microsoft.com/en-us/cli/azure/webapp).

```bash
az acr login -n <acr>                                   # token via az login, no admin user
az acr build -r <acr> -t app:$(git rev-parse --short HEAD) .
az containerapp env list -o table
az containerapp list -o table
az containerapp logs show -n <app> -g <rg> --follow
az containerapp revision list -n <app> -g <rg> -o table
az containerapp update -n <app> -g <rg> --image <acr>.azurecr.io/app:<tag>
az functionapp list -o table
az webapp log tail -n <app> -g <rg>
```

Local Functions development needs `func` from `azure-functions-core-tools`
(opt-in package in `devenv.nix`,
[run locally](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local)).

## Identity and RBAC

Source: [az role assignment](https://learn.microsoft.com/en-us/cli/azure/role/assignment),
[az identity](https://learn.microsoft.com/en-us/cli/azure/identity),
[az ad app](https://learn.microsoft.com/en-us/cli/azure/ad/app), [az ad sp](https://learn.microsoft.com/en-us/cli/azure/ad/sp).

```bash
az ad signed-in-user show --query "{upn:userPrincipalName,id:id}"
az role assignment list --assignee <object-id> --all -o table
az role assignment list --scope "/subscriptions/$SUB/resourceGroups/<rg>" --include-inherited -o table
az role definition list --query "[?roleName=='Storage Blob Data Contributor'].{name:roleName,id:name}"
az identity create -g <rg> -n id-<workload>-<env>
az identity federated-credential list --identity-name <id> -g <rg> -o table
az ad app list --display-name <name> --query "[].{name:displayName,appId:appId}"
az ad app credential list --id <app-id> -o table     # spot expiring secrets; do not create new ones
```

## Key Vault

Source: [az keyvault](https://learn.microsoft.com/en-us/cli/azure/keyvault),
[az keyvault secret](https://learn.microsoft.com/en-us/cli/azure/keyvault/secret).

```bash
az keyvault list -o table
az keyvault show -n <kv> --query "{rbac:properties.enableRbacAuthorization,purge:properties.enablePurgeProtection}"
az keyvault secret list --vault-name <kv> -o table           # names only, safe to print
az keyvault secret show --vault-name <kv> -n <name> --query value -o tsv   # NEVER echo; pipe into secret-add
az keyvault secret show --vault-name <kv> -n db-password --query value -o tsv | secret-add DB_PASSWORD
```

## Policy, cost, advisor

Source: [az policy assignment](https://learn.microsoft.com/en-us/cli/azure/policy/assignment),
[az policy state](https://learn.microsoft.com/en-us/cli/azure/policy/state),
[built-in policies](https://learn.microsoft.com/en-us/azure/governance/policy/samples/built-in-policies),
[az consumption](https://learn.microsoft.com/en-us/cli/azure/consumption),
[az costmanagement](https://learn.microsoft.com/en-us/cli/azure/costmanagement),
[az advisor](https://learn.microsoft.com/en-us/cli/azure/advisor).

```bash
az policy assignment list --disable-scope-strict-match -o table
az policy state list --filter "complianceState eq 'NonCompliant'" --query "[].{policy:policyDefinitionName,resource:resourceId}" -o table
az policy state trigger-scan -g <rg>
az consumption budget list -o table
az costmanagement query --type ActualCost --timeframe MonthToDate --scope "/subscriptions/$SUB" \
  --dataset-aggregation '{"totalCost":{"name":"Cost","function":"Sum"}}' \
  --dataset-grouping name=ResourceGroupName type=Dimension -o table
az advisor recommendation list --category Cost -o table
```

## Networking and storage quick checks

Source: [az network vnet](https://learn.microsoft.com/en-us/cli/azure/network/vnet),
[az storage account](https://learn.microsoft.com/en-us/cli/azure/storage/account).

```bash
az network vnet list -o table
az network vnet subnet list -g <rg> --vnet-name <vnet> -o table
az network nsg rule list -g <rg> --nsg-name <nsg> --query "[?access=='Allow' && sourceAddressPrefix=='*']" -o table
az network public-ip list --query "[].{name:name,ip:ipAddress,rg:resourceGroup}" -o table
az storage account list --query "[].{name:name,sharedKey:allowSharedKeyAccess,public:allowBlobPublicAccess,tls:minimumTlsVersion}" -o table
az storage account update -n <st> -g <rg> --allow-shared-key-access false --min-tls-version TLS1_2
```

## Cleanup

```bash
az group delete -n <rg> --yes --no-wait          # only for sandbox RGs you created; check az account show first
az deployment group delete -g <rg> -n <name>     # removes history only, not resources
```
