# Identity and access: Entra ID, RBAC, managed identities

Verified 2026-09-15. Entry points: [Azure RBAC overview](https://learn.microsoft.com/en-us/azure/role-based-access-control/overview),
[RBAC best practices](https://learn.microsoft.com/en-us/azure/role-based-access-control/best-practices),
[Identity management best practices](https://learn.microsoft.com/en-us/azure/security/fundamentals/identity-management-best-practices),
[CAF identity design area](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/design-area/identity-access).

## Two role systems, do not confuse them

- **Azure RBAC** controls Azure resources (subscriptions, resource groups,
  resources). Roles: Owner, Contributor, Reader, and service-specific ones.
- **Entra ID roles** control the directory (users, apps, groups). Roles:
  Global Administrator, Application Administrator, and so on.

They are separate. A Global Administrator has no Azure RBAC access until they
[elevate](https://learn.microsoft.com/en-us/azure/role-based-access-control/elevate-access-global-admin),
which should be rare and audited
([RBAC vs directory admin roles](https://learn.microsoft.com/en-us/azure/role-based-access-control/rbac-and-directory-admin-roles)).

## Azure RBAC rules

Source: [RBAC best practices](https://learn.microsoft.com/en-us/azure/role-based-access-control/best-practices),
[Scope](https://learn.microsoft.com/en-us/azure/role-based-access-control/scope-overview),
[Built-in roles](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles),
[Custom roles](https://learn.microsoft.com/en-us/azure/role-based-access-control/custom-roles).

- [ ] Assign to **groups**, not users or individual service principals; membership
      changes then need no role assignment change.
- [ ] Assign at the **narrowest scope** that works: resource, then resource group,
      then subscription. Management-group scope is for platform teams only.
- [ ] Use **built-in roles**; write a custom role only when no built-in fits, and
      keep `Actions` explicit (no `*`).
- [ ] Prefer data-plane roles (`Storage Blob Data Contributor`, `Key Vault Secrets
      User`, `AcrPull`) over control-plane `Contributor` for workloads.
- [ ] Limit `Owner` to at most three principals per subscription, all humans, all
      behind PIM.
- [ ] Use [ABAC conditions](https://learn.microsoft.com/en-us/azure/role-based-access-control/conditions-overview)
      to narrow blob access by container or tag when roles are too coarse.
- [ ] Delegate role-assignment rights with constrained
      [Role Based Access Control Administrator](https://learn.microsoft.com/en-us/azure/role-based-access-control/delegate-role-assignments-overview)
      instead of `User Access Administrator`.
- [ ] Review assignments regularly:
      `az role assignment list --all --include-inherited -o table`
      ([List role assignments](https://learn.microsoft.com/en-us/azure/role-based-access-control/role-assignments-list-cli)).

Assign a role with the CLI ([Assign roles with CLI](https://learn.microsoft.com/en-us/azure/role-based-access-control/role-assignments-cli)):

```bash
az role assignment create \
  --assignee-object-id "$GROUP_OBJECT_ID" --assignee-principal-type Group \
  --role "Storage Blob Data Contributor" \
  --scope "/subscriptions/$SUB/resourceGroups/rg-app-prod-weu/providers/Microsoft.Storage/storageAccounts/stappprodweu"
```

Use `--assignee-object-id` with `--assignee-principal-type` rather than a
display name; it avoids the Graph lookup and the replication race that causes
`PrincipalNotFound` right after creation
([Troubleshoot RBAC](https://learn.microsoft.com/en-us/azure/role-based-access-control/troubleshooting)).

## Workload identity: the preference order

1. **System-assigned managed identity** for a single resource that needs access
   (a VM, Function, Container App). Lifecycle tied to the resource.
2. **User-assigned managed identity** when several resources share access or the
   identity must outlive the resource (recommended for AKS, CI, most workloads).
3. **Workload identity federation** for anything running outside Azure: GitHub
   Actions, AKS pods, other clouds. Entra ID trusts the external OIDC issuer and
   issues a token; no secret exists.
4. **Certificate credential** on an app registration if federation is impossible.
5. **Client secret**: last resort, short expiry, stored with agenix, rotated.

Sources: [Managed identities overview](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview),
[Managed identity best practices](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/managed-identity-best-practice-recommendations),
[Workload identity federation](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation),
[Secure service accounts](https://learn.microsoft.com/en-us/entra/architecture/secure-service-accounts),
[App registration security best practices](https://learn.microsoft.com/en-us/entra/identity-platform/security-best-practices-for-app-registration).

### GitHub Actions to Azure without secrets

Source: [Connect from Azure with OpenID Connect](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect),
[Federated credential on a user-assigned managed identity](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-create-trust-user-assigned-managed-identity).

```bash
az identity create -g rg-app-prod-weu -n id-app-deploy-prod
az identity federated-credential create --identity-name id-app-deploy-prod -g rg-app-prod-weu \
  --name github-main --issuer https://token.actions.githubusercontent.com \
  --subject "repo:<org>/<repo>:ref:refs/heads/main" --audiences api://AzureADTokenExchange
```

Then in the workflow use `azure/login` with `client-id`, `tenant-id`,
`subscription-id` and `permissions: id-token: write`. Pin the `subject` to a
branch or environment; a `repo:*` subject lets any branch deploy. For Terraform
set `use_oidc = true` in the provider and backend (see [terraform.md](terraform.md)).
For an app registration instead of a managed identity, use
`az ad app federated-credential create` ([reference](https://learn.microsoft.com/en-us/cli/azure/ad/app/federated-credential)).

### AKS: Entra ID and workload identity

Sources: [AKS workload identity](https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview),
[Deploy with workload identity](https://learn.microsoft.com/en-us/azure/aks/workload-identity-deploy-cluster),
[Entra ID integration](https://learn.microsoft.com/en-us/azure/aks/enable-authentication-microsoft-entra-id),
[Azure RBAC for Kubernetes authorization](https://learn.microsoft.com/en-us/azure/aks/manage-azure-rbac),
[kubelogin](https://learn.microsoft.com/en-us/azure/aks/kubelogin-authentication),
[ACR integration](https://learn.microsoft.com/en-us/azure/aks/cluster-container-registry-integration),
[Cluster security best practices](https://learn.microsoft.com/en-us/azure/aks/operator-best-practices-cluster-security).

- [ ] `--enable-aad --enable-azure-rbac --disable-local-accounts`: humans
      authenticate with Entra ID via `kubelogin`, authorisation is Azure RBAC
      (`Azure Kubernetes Service RBAC Reader/Writer/Admin` at namespace scope).
- [ ] `--enable-oidc-issuer --enable-workload-identity`: pods get Azure tokens
      through a federated credential on a user-assigned identity, bound with the
      `azure.workload.identity/client-id` service-account annotation.
- [ ] `--attach-acr <acr>`: the kubelet identity gets `AcrPull`; no image-pull secrets.
- [ ] Never use `--admin` credentials in CI; use a group with the namespace-scoped role.

## Human access

- [ ] MFA for every user; Microsoft enforces it for portal and CLI sign-in
      ([Mandatory MFA](https://learn.microsoft.com/en-us/entra/identity/authentication/concept-mandatory-multifactor-authentication)).
- [ ] Conditional Access policies for device compliance and location
      ([Conditional Access](https://learn.microsoft.com/en-us/entra/identity/conditional-access/overview)).
- [ ] Privileged roles are **eligible**, not permanent, via PIM with justification
      and time limits ([PIM](https://learn.microsoft.com/en-us/entra/id-governance/privileged-identity-management/pim-configure)).
- [ ] Two cloud-only emergency access accounts, excluded from Conditional Access,
      monitored ([Emergency access accounts](https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/security-emergency-access)).
- [ ] Least privilege for directory roles too
      ([Entra role best practices](https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/best-practices),
      [Permissions reference](https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/permissions-reference)).
- [ ] Prefer dynamic groups keyed on attributes for RBAC membership
      ([Dynamic group rules](https://learn.microsoft.com/en-us/entra/identity/users/groups-create-rule)).

## Key Vault and Storage access

- [ ] Key Vault uses the **RBAC permission model** (`enable_rbac_authorization = true`),
      not access policies; grant `Key Vault Secrets User` to the workload identity
      ([Key Vault RBAC guide](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide),
      [Key Vault best practices](https://learn.microsoft.com/en-us/azure/key-vault/general/best-practices),
      [Security features](https://learn.microsoft.com/en-us/azure/key-vault/general/security-features)).
- [ ] Storage: disable Shared Key, use Entra ID data-plane roles, restrict network
      access ([Prevent Shared Key](https://learn.microsoft.com/en-us/azure/storage/common/shared-key-authorization-prevent),
      [Authorize with Entra ID](https://learn.microsoft.com/en-us/azure/storage/blobs/authorize-access-azure-active-directory),
      [Storage network security](https://learn.microsoft.com/en-us/azure/storage/common/storage-network-security)).
- [ ] ACR: pull with managed identity, never admin user
      ([ACR authentication](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-authentication),
      [ACR with managed identity](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-authentication-managed-identity)).

## Audit

- Activity log for control-plane changes (`az monitor activity-log list`)
  ([Activity log](https://learn.microsoft.com/en-us/azure/azure-monitor/essentials/activity-log)).
- Entra audit logs for directory changes
  ([Audit logs](https://learn.microsoft.com/en-us/entra/identity/monitoring-health/concept-audit-logs)).
- Monitor privileged accounts per the Entra security operations guide
  ([Privileged accounts](https://learn.microsoft.com/en-us/entra/architecture/security-operations-privileged-accounts)).

## Agent sessions

Log in with `az login` as yourself. For an AI agent session prefer a separate
account or identity holding only `Reader` on the target subscription; upgrade
to `Contributor` on a single resource group for the duration of an apply, via
PIM where available. The `azure-mcp` server inherits whatever `az login` has.
