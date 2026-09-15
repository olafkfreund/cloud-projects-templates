# Identity and access: RBAC, ServiceAccounts, workload identity

Two questions for every access decision: *who* (a human, a CI job, a pod, an agent) and
*to what* (the Kubernetes API, or a cloud API from inside a pod). Sources verified 2026-09-15.

## RBAC least privilege

Source: [RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/),
[RBAC good practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/),
[Authorization](https://kubernetes.io/docs/reference/access-authn-authz/authorization/).

- Prefer `Role` + `RoleBinding` (namespaced) over `ClusterRole` + `ClusterRoleBinding`.
  A `ClusterRole` bound with a `RoleBinding` is fine: it reuses the definition, scoped to a
  namespace.
- Bind to **groups** from the cloud identity provider, not to individual users. Removing a
  person then happens in the IdP, not in every cluster.
- Never `cluster-admin` for a workload or a day-to-day human role. Break-glass admin is a
  separate group with audit alerts on use.
- Deny-list the dangerous verbs: `escalate`, `bind`, `impersonate`, `create` on
  `pods/exec`, `secrets` `list`/`watch` (lists return the data), `create` on
  `certificatesigningrequests`, `update` on `nodes/proxy`. Any role granting these is a
  privilege-escalation path and needs a written reason.
- Prefer named resources (`resourceNames`) when the target set is fixed.
- Built-in aggregate roles (`view`, `edit`, `admin`) are good starting points; `view` cannot
  read Secrets, which is exactly what an agent or dashboard needs.
- Check with `kubectl auth can-i --list --as=system:serviceaccount:NS:SA` and
  `kubectl auth can-i create pods --as=user@example.com`
  ([kubectl auth can-i](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/)).
- Wildcards in `verbs`, `resources` or `apiGroups` fail review.

Read-only role for an agent, dashboard or MCP server:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata: {name: agents-view}
roleRef: {apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: view}
subjects:
  - {kind: Group, name: k8s-agents, apiGroup: rbac.authorization.k8s.io}
```

Scope it to one namespace by swapping `ClusterRoleBinding` for a `RoleBinding`.

## ServiceAccounts

Source: [Service accounts](https://kubernetes.io/docs/concepts/security/service-accounts/),
[Configure service accounts](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/),
[Managing service accounts](https://kubernetes.io/docs/reference/access-authn-authz/service-accounts-admin/).

- One ServiceAccount per workload; never the namespace `default` SA (set
  `automountServiceAccountToken: false` on it).
- `automountServiceAccountToken: false` on pods that do not call the Kubernetes API.
  A mounted token in a compromised container is a foothold.
- Use bound, projected, expiring tokens (the default since 1.22); never create long-lived
  `Secret`-type SA tokens.
- Grant the SA a Role only for what the code actually calls; most apps need nothing.
- For CI: short-lived tokens via the cloud identity (OIDC federation from GitHub Actions
  etc.), never a kubeconfig stored in CI secrets
  ([Authentication](https://kubernetes.io/docs/reference/access-authn-authz/authentication/),
  [Authentication hardening](https://kubernetes.io/docs/concepts/security/hardening-guide/authentication-mechanisms/)).

## Workload identity: pods calling cloud APIs

Rule: a pod gets a cloud identity through the platform's OIDC/token exchange, tied to
`namespace/serviceaccount`. Never mount cloud access keys, never use the node's instance
role for application traffic (every pod on the node would inherit it; block the instance
metadata endpoint from pods).

### EKS: Pod Identity (preferred) or IRSA

- **EKS Pod Identity**: install the `eks-pod-identity-agent` add-on, create an IAM role with
  the `pods.eks.amazonaws.com` trust, then a *pod identity association* linking cluster +
  namespace + SA to the role. No annotation on the SA is needed and the role trust policy
  does not embed the cluster OIDC issuer, so one role works across clusters.
  [Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html).
- **IRSA**: the older method; IAM role trust references the cluster OIDC provider and the
  SA gets `eks.amazonaws.com/role-arn`. Still required for some add-ons and for cross-account
  patterns that Pod Identity does not cover.
  [IRSA](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html).
- Humans and CI: IAM principals mapped through **access entries** (not the `aws-auth`
  ConfigMap) with access policies such as `AmazonEKSViewPolicy` or `AmazonEKSAdminPolicy`,
  or to RBAC groups.
  [Access entries](https://docs.aws.amazon.com/eks/latest/userguide/access-entries.html),
  [Grant access](https://docs.aws.amazon.com/eks/latest/userguide/grant-k8s-access.html),
  [EKS IAM best practices](https://docs.aws.amazon.com/eks/latest/best-practices/identity-and-access-management.html).
- kubeconfig: `aws eks update-kubeconfig --name CLUSTER --region REGION`; the exec plugin
  runs `aws eks get-token` at every call, so nothing sensitive lands in the file
  ([Create kubeconfig](https://docs.aws.amazon.com/eks/latest/userguide/create-kubeconfig.html)).

### AKS: Microsoft Entra Workload ID

- Enable OIDC issuer and workload identity on the cluster; create a user-assigned managed
  identity (or app registration); add a *federated identity credential* with subject
  `system:serviceaccount:NS:SA`; annotate the SA with `azure.workload.identity/client-id`
  and label the pod `azure.workload.identity/use: "true"`.
  [Workload identity overview](https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview).
- Humans: Entra ID authentication with **Azure RBAC for Kubernetes authorization** (roles
  like `Azure Kubernetes Service RBAC Reader/Writer/Admin` scoped to a namespace or
  cluster) or Entra groups bound in Kubernetes RBAC. Disable local accounts.
  [Entra integration](https://learn.microsoft.com/en-us/azure/aks/enable-authentication-microsoft-entra-id),
  [Azure RBAC](https://learn.microsoft.com/en-us/azure/aks/manage-azure-rbac),
  [Kubernetes RBAC with Entra](https://learn.microsoft.com/en-us/azure/aks/azure-ad-rbac),
  [Identity best practices](https://learn.microsoft.com/en-us/azure/aks/operator-best-practices-identity).
- kubeconfig: `az aks get-credentials -g RG -n CLUSTER` then
  `kubelogin convert-kubeconfig -l azurecli` so tokens come from the `az` login, not a
  cached secret ([kubelogin](https://learn.microsoft.com/en-us/azure/aks/kubelogin-authentication)).

### GKE: Workload Identity Federation for GKE

- Enable Workload Identity on the cluster and `GKE_METADATA` on node pools (Autopilot has it
  on). Grant IAM roles directly to the principal
  `principal://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/PROJECT_ID.svc.id.goog/subject/ns/NS/sa/SA`;
  no Google service account impersonation is needed for most cases.
  [Workload Identity concepts](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity),
  [How-to](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-identity).
- Humans: Google Cloud IAM roles (`roles/container.viewer`, `roles/container.developer`,
  `roles/container.admin`) for coarse access, Kubernetes RBAC bound to Google groups for
  namespace scope.
  [IAM for GKE](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/iam),
  [RBAC on GKE](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/role-based-access-control),
  [RBAC best practices](https://docs.cloud.google.com/kubernetes-engine/docs/best-practices/rbac).
- kubeconfig: `gcloud container clusters get-credentials CLUSTER --location LOC`; requires
  `gke-gcloud-auth-plugin` (in the gcp module)
  ([Cluster access](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl)).

### OKE: workload identity

- Enhanced clusters only. Write an IAM policy whose principal is the workload:
  `Allow any-user to manage object-family in compartment C where all { request.principal.type = 'workload', request.principal.namespace = 'NS', request.principal.service_account = 'SA', request.principal.cluster_id = 'ocid1.cluster…' }`.
  The OCI SDK in the pod uses `OkeWorkloadIdentityAuthenticationDetailsProvider`.
  [Granting workloads access to OCI resources](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contenggrantingworkloadaccesstoresources.htm).
- Humans: OCI IAM policies control who can `use` the cluster; by default they only get the
  discovery roles inside Kubernetes, so add RBAC bindings for OCI users/groups by OCID.
  [Access control](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengaboutaccesscontrol.htm),
  [OKE policy configuration](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengpolicyconfig.htm).
- kubeconfig: `oci ce cluster create-kubeconfig --cluster-id OCID --file $KUBECONFIG
  --token-version 2.0.0`; the exec plugin calls `oci ce cluster generate-token`
  ([Download kubeconfig](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengdownloadkubeconfigfile.htm)).

## Human access checklist

- [ ] Cloud identity is the only way in; local/static accounts disabled.
- [ ] Groups, not users, in every binding; `view` for most people, `edit` per namespace for
      owners, break-glass admin group with alerting.
- [ ] `kubectl exec`, `port-forward` and `secrets` read restricted to on-call roles.
- [ ] Kubeconfigs are generated by the cloud CLI on demand and are in `.gitignore`.
- [ ] Audit log query exists for "who ran what as cluster-admin last 30 days".
- [ ] Agent identities (MCP, dashboards, CI read jobs) bound to `view` only; see `mcp.md`.
