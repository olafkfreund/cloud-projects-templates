# Provisioning clusters with Terraform

Kubernetes-specific Terraform practice only. Generic Terraform practice (state, backends,
modules, workflow) lives in the always-installed `terraform` skill: [`../terraform/SKILL.md`](../terraform/SKILL.md).
Sources verified 2026-09-15.

## Layout: cluster state and workload state are separate

```
infra/
  network/        # VPC/VNet/VCN, subnets, NAT, DNS         -> state A
  cluster/        # EKS/AKS/GKE/OKE, node pools, IAM, add-ons that need cloud IAM  -> state B
  platform/       # helm/kubernetes provider resources: bootstrap of GitOps controller only -> state C
apps/             # NOT Terraform: Kustomize/Helm reconciled by Argo CD or Flux
```

Why:

- The `kubernetes` and `helm` providers must be configured with cluster credentials at
  **plan** time. If the cluster is created in the same root module, the provider is
  configured from unknown values, and plans fail or behave unpredictably on create,
  replace and destroy. HashiCorp's provider docs say resources that provide the
  credentials should not live in the same module as the resources that use them
  ([kubernetes provider](https://registry.terraform.io/providers/hashicorp/kubernetes/latest/docs),
  [helm provider](https://registry.terraform.io/providers/hashicorp/helm/latest/docs)).
- Blast radius: `terraform destroy` on the cluster module must not be able to take a workload
  state with it, and a workload change must not need cluster-admin on the cloud API.
- Different cadences: the cluster changes monthly, workloads daily. Daily changes belong in
  GitOps, where `kubectl diff` and reconciliation are first-class; Terraform only bootstraps
  the GitOps controller and the handful of objects that need cloud IAM created in lockstep.

Pass outputs between states with `terraform_remote_state` or, better, with cloud data
sources (`aws_eks_cluster`, `azurerm_kubernetes_cluster`, `google_container_cluster`,
`oci_containerengine_cluster`) so state C does not need read access to state B's file
([remote state data](https://developer.hashicorp.com/terraform/language/state/remote-state-data),
[backends](https://developer.hashicorp.com/terraform/language/backend)).

## Modules

Use the maintained community modules rather than hand-writing every resource; they encode
the managed-service best practices and are updated with the API:

| Cloud | Module | Notes |
|---|---|---|
| EKS | [terraform-aws-modules/eks](https://registry.terraform.io/modules/terraform-aws-modules/eks/aws/latest) | Access entries, managed node groups, Pod Identity associations, add-ons |
| AKS | [Azure/aks](https://registry.terraform.io/modules/Azure/aks/azurerm/latest) | Entra + Azure RBAC, OIDC issuer, workload identity flags |
| GKE | [terraform-google-modules/kubernetes-engine](https://registry.terraform.io/modules/terraform-google-modules/kubernetes-engine/google/latest) | Submodules for private/Autopilot clusters, Workload Identity on by default |
| OKE | [oracle-terraform-modules/oke](https://registry.terraform.io/modules/oracle-terraform-modules/oke/oci/latest) | VCN, enhanced clusters, node pools, workload identity policies |

Pin module and provider versions (`version = "~> X.Y"`), commit `.terraform.lock.hcl`, and
run `tflint` and `trivy config` in the pre-commit hooks the common module installs.

## Cluster module checklist

- [ ] Private or CIDR-restricted API endpoint; public access off in prod.
- [ ] Control-plane/audit logging enabled and shipped to the cloud log service.
- [ ] Secrets encryption with a customer-managed key.
- [ ] Node pools: managed, auto-upgrade, auto-repair, minimal image, no public IP, no SSH
      key; separate system pool with `CriticalAddonsOnly` taint.
- [ ] Node autoscaling (Karpenter/NAP/cluster autoscaler) with a hard max.
- [ ] Network: CNI with NetworkPolicy support enabled, IP ranges sized for growth.
- [ ] Human access via cloud identity (access entries / Entra / IAM / OCI policies) as
      Terraform resources, so access is reviewed in PRs. See `iam.md`.
- [ ] Workload identity enabled (Pod Identity agent, OIDC issuer + workload identity,
      Workload Identity pool, enhanced cluster) as part of the cluster module.
- [ ] Outputs: cluster name, endpoint, CA, OIDC issuer, node SG/NSG ids. **Never** output a
      kubeconfig or token (it lands in state).
- [ ] Tags/labels: environment, owner, cost-centre, `managed-by=terraform`.

## kubernetes / helm provider caveats

- **Auth with an exec plugin, not a token in state.** Use `exec { … }` (`aws eks get-token`,
  `kubelogin get-token`, `gke-gcloud-auth-plugin`, `oci ce cluster generate-token`) or the
  cloud data source that returns a short-lived token
  ([aws_eks_cluster_auth](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/eks_cluster_auth)).
  A static `token = …` or `client_key` is written to state in plaintext.
- **`kubernetes_manifest` needs the CRD to exist at plan time.** It reads the OpenAPI
  schema from the cluster; CRDs and their instances cannot be created in one apply. Put CRDs
  (or the chart that installs them) in an earlier module or use `helm_release` with
  `skip_crds = false` first
  ([kubernetes_manifest](https://registry.terraform.io/providers/hashicorp/kubernetes/latest/docs/resources/manifest)).
- **`helm_release`**: pin `version`, set `atomic = true`, `wait = true`,
  `cleanup_on_fail = true`; the v3 provider uses `set = [{ name = …, value = … }]` list
  syntax and `values = [file("values.yaml")]`. Secrets go in `set_sensitive` **and** still
  end up in state, so prefer External Secrets over passing them at all
  ([helm_release](https://registry.terraform.io/providers/hashicorp/helm/latest/docs/resources/release)).
- **`kubernetes_secret` stores the value in state.** Don't. Create an `ExternalSecret`
  manifest instead, or let the app read from the cloud secret store via workload identity
  ([kubernetes_secret](https://registry.terraform.io/providers/hashicorp/kubernetes/latest/docs/resources/secret)).
- **Don't fight GitOps.** Once Argo CD or Flux owns a namespace, Terraform must not manage
  objects in it (both will reconcile). Terraform bootstraps the controller and its first
  `Application`/`GitRepository`; everything else comes from git.
- **Destroy order.** `terraform destroy` of the platform state before the cluster state, or
  finalizers on LoadBalancer Services and PVCs leave orphaned cloud resources. Delete
  Services of type LoadBalancer and PVCs first.
- `kubernetes_service_account` + `kubernetes_role_binding` are fine in Terraform when they
  must be created in lockstep with the cloud IAM role/identity they bind to
  ([kubernetes_service_account](https://registry.terraform.io/providers/hashicorp/kubernetes/latest/docs/resources/service_account)).

## Provider skeleton (platform state)

```hcl
data "aws_eks_cluster" "this" { name = var.cluster_name }   # or azurerm/google/oci equivalent

provider "kubernetes" {
  host                   = data.aws_eks_cluster.this.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.this.certificate_authority[0].data)
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", var.cluster_name]
  }
}

provider "helm" {
  kubernetes = {
    host                   = data.aws_eks_cluster.this.endpoint
    cluster_ca_certificate = base64decode(data.aws_eks_cluster.this.certificate_authority[0].data)
    exec = {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", var.cluster_name]
    }
  }
}

resource "helm_release" "argocd" {
  name             = "argocd"
  namespace        = "argocd"
  create_namespace = true
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = "X.Y.Z"      # pin
  atomic           = true
  wait             = true
  values           = [file("${path.module}/argocd-values.yaml")]
}
```

Swap the `aws` exec for `kubelogin get-token --login azurecli --server-id …` (AKS),
`gke-gcloud-auth-plugin` (GKE) or `oci ce cluster generate-token --cluster-id …` (OKE).

## Workflow

```bash
cd infra/cluster
terraform init
terraform fmt -recursive && terraform validate && tflint
secret-run --only TFE_TOKEN -- terraform plan -out=plan.tfplan   # only if a remote backend needs it
terraform show plan.tfplan | less                                 # read the whole plan
terraform apply plan.tfplan
terraform output -raw cluster_name                                # never `terraform output` a kubeconfig
```

Never commit `*.tfstate`, `*.tfplan` or a generated kubeconfig; the common module's hooks
reject private keys, and `trivy fs --scanners secret .` runs in CI.
