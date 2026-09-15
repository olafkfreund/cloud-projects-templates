# Cluster landing zone: tenancy, environments, GitOps, platform add-ons

How to lay out clusters and namespaces so teams are isolated, environments are reproducible
and nothing reaches prod without passing through git. Sources verified 2026-09-15.

## Namespaces vs clusters

Kubernetes multi-tenancy is a spectrum; pick the isolation level per tenant, not per cluster
([Multi-tenancy](https://kubernetes.io/docs/concepts/security/multi-tenancy/),
[EKS multi-tenancy](https://docs.aws.amazon.com/eks/latest/best-practices/multi-tenancy.html),
[EKS tenant isolation](https://docs.aws.amazon.com/eks/latest/best-practices/tenant-isolation.html),
[AKS cluster isolation](https://learn.microsoft.com/en-us/azure/aks/operator-best-practices-cluster-isolation),
[GKE multi-tenancy](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/multitenancy-overview),
[GKE enterprise multi-tenancy](https://docs.cloud.google.com/kubernetes-engine/docs/best-practices/enterprise-multitenancy)).

| Need | Choose | Why |
|---|---|---|
| Teams in one org, trusted code | **Namespace per team/app** in a shared cluster | Cheapest; RBAC + quotas + NetworkPolicy + PSS give "soft" isolation |
| Prod vs non-prod | **Separate clusters** | Upgrades, blast radius and access rules differ; a dev mistake must not touch prod |
| Untrusted or regulated tenants | **Separate clusters** (or node pools with taints + sandboxing at minimum) | Namespaces share the kernel and control plane; soft isolation is not a security boundary |
| Different regions / data residency | Cluster per region | Data and latency; use DNS or a global LB in front |

Rules:

- One namespace per application per environment in shared clusters; never `default`.
  [Namespaces](https://kubernetes.io/docs/concepts/overview/working-with-objects/namespaces/).
- Every namespace ships with the same "namespace kit", created by the platform, not the
  team: PSS labels, ResourceQuota, LimitRange, default-deny NetworkPolicies, a RoleBinding
  to the team's group, and required labels (team, cost-centre, environment).
  [Resource quotas](https://kubernetes.io/docs/concepts/policy/resource-quotas/),
  [Limit ranges](https://kubernetes.io/docs/concepts/policy/limit-range/),
  [PSS namespace labels](https://kubernetes.io/docs/tasks/configure-pod-container/enforce-standards-namespace-labels/).
- Platform components live in their own namespaces (`ingress`, `cert-manager`,
  `external-secrets`, `monitoring`, `argocd`/`flux-system`) with tighter RBAC and a higher
  PriorityClass ([Pod priority](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/)).
- Dedicated node pools for system add-ons (tainted `CriticalAddonsOnly`) and for special
  hardware (GPU, spot), selected by nodeSelector/tolerations
  ([AKS scheduler practices](https://learn.microsoft.com/en-us/azure/aks/operator-best-practices-advanced-scheduler),
  [Assign pods to nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/)).

## Environments

- Minimum: `dev`, `staging`, `prod`. `dev` may share a cluster with `staging`; `prod` is
  its own cluster with its own cloud account/subscription/project/compartment.
- Same manifests across environments, different overlays or values: Kustomize
  `base/` + `overlays/<env>/`, or one Helm chart + `values-<env>.yaml`. Anything that only
  exists in prod is a bug waiting to happen.
  [Kustomize](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/),
  [Helm values best practices](https://helm.sh/docs/chart_best_practices/values/).
- Promote by changing a digest in git, not by re-building. The image that passed staging is
  the image that ships.
- Cluster versions: prod trails non-prod by one release; upgrade non-prod first, wait a
  week, then prod.
  [GKE upgrading clusters](https://docs.cloud.google.com/kubernetes-engine/docs/best-practices/upgrading-clusters).

## GitOps with Argo CD or Flux

Why: a reconciler makes git the only write path to the cluster, gives drift detection and a
complete audit trail, and removes the need for CI to hold cluster credentials
([OpenGitOps principles](https://opengitops.dev/)).

Repository layout (works for both tools):

```
infra/                 # Terraform: clusters, node pools, IAM (see terraform.md)
platform/              # add-ons, one dir per component, Helm or Kustomize
  cert-manager/  external-secrets/  ingress/  monitoring/  policies/
apps/
  <app>/base/          # Kustomize base or chart
  <app>/overlays/dev|staging|prod/
clusters/
  <cluster>/           # Argo `Application`s / Flux `Kustomization`s that point at platform/ and apps/
```

Argo CD:

- Install declaratively and bootstrap with the app-of-apps pattern or ApplicationSets.
  [Declarative setup](https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/),
  [Cluster bootstrapping](https://argo-cd.readthedocs.io/en/stable/operator-manual/cluster-bootstrapping/).
- Separate config repos from source repos; one Application per app per environment;
  `prune: true` and `selfHeal: true` in prod so drift is reverted.
  [Argo CD best practices](https://argo-cd.readthedocs.io/en/stable/user-guide/best_practices/).
- Argo's own ServiceAccount is the one that needs cluster-wide write; humans get project
  scoped roles in Argo, not RBAC in the cluster.

Flux:

- `flux bootstrap` writes the controllers and their sync config to git; a `Kustomization`
  per layer (`infra` -> `platform` -> `apps`) with `dependsOn`.
  [Flux installation](https://fluxcd.io/flux/installation/),
  [Repository structure](https://fluxcd.io/flux/guides/repository-structure/).
- Use `HelmRelease` for charts and image automation only in non-prod.

Either way:

- CI runs `kustomize build` / `helm template`, `kubectl apply --dry-run=server`,
  `trivy config`, and policy tests on the PR. The reconciler applies after merge.
- Secrets: the reconciler reads `ExternalSecret` or `SealedSecret` objects from git and
  never a plaintext `Secret`
  ([External Secrets](https://external-secrets.io/latest/),
  [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets)).
- Break-glass: a documented procedure to pause reconciliation, fix by hand, then commit.

## Platform add-ons (install order)

| Layer | Component | Notes and source |
|---|---|---|
| 1 | CNI with NetworkPolicy, CoreDNS, kube-proxy, metrics-server | Managed add-ons where offered ([EKS add-ons](https://docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html)) |
| 2 | Node autoscaler | Karpenter / cluster autoscaler / NAP; see `well-architected.md` |
| 3 | Gateway or Ingress controller + cert-manager | [Gateway API](https://gateway-api.sigs.k8s.io/), [cert-manager](https://cert-manager.io/docs/) |
| 4 | External Secrets or Secrets Store CSI | Wired to the cloud secret store via workload identity (`iam.md`) |
| 5 | Policy engine | [Kyverno](https://kyverno.io/docs/) or [ValidatingAdmissionPolicy](https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/); enforce digests, labels, probes, no `latest` |
| 6 | Observability | Prometheus/OpenTelemetry collectors, log shipper to the cloud log service ([Logging](https://kubernetes.io/docs/concepts/cluster-administration/logging/)) |
| 7 | GitOps controller | Argo CD or Flux, then hand the rest of this table to it |

## Managed-service landing zones

- **EKS**: cluster per account/environment, private endpoint, IAM access entries, VPC CNI
  with prefix delegation, Karpenter, control-plane logs to CloudWatch.
  [EKS networking](https://docs.aws.amazon.com/eks/latest/best-practices/networking.html),
  [Access entries](https://docs.aws.amazon.com/eks/latest/userguide/access-entries.html).
- **AKS**: follow the AKS landing zone accelerator and baseline architecture: private
  cluster, Entra ID + Azure RBAC, Azure CNI overlay, Azure Policy, node autoprovisioning.
  [AKS landing zone accelerator](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/scenarios/app-platform/aks/landing-zone-accelerator),
  [AKS baseline](https://learn.microsoft.com/en-us/azure/architecture/reference-architectures/containers/aks/baseline-aks),
  [Well-Architected AKS guide](https://learn.microsoft.com/en-us/azure/well-architected/service-guides/azure-kubernetes-service),
  [Azure Policy for AKS](https://learn.microsoft.com/en-us/azure/aks/use-azure-policy).
- **GKE**: project per environment, Autopilot unless you need node control, private
  cluster, release channel, Dataplane V2, Workload Identity Federation, Binary Authorization.
  [GKE networking best practices](https://docs.cloud.google.com/kubernetes-engine/docs/best-practices/networking),
  [Dataplane V2](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/dataplane-v2),
  [Security overview](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/security-overview).
- **OKE**: compartment per environment, enhanced cluster, VCN-native pod networking with
  Calico, private API endpoint, NSGs on node and LB subnets, workload identity.
  [Enhanced clusters](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengworkingwithenhancedclusters.htm),
  [OKE cluster management](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengbestpractices_topic-Cluster-Management-best-practices.htm),
  [OKE networking](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengbestpractices_topic-Networking-best-practices.htm),
  [Securing OKE](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/oke_security.htm).
