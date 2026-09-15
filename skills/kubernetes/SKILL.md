---
name: kubernetes
description: Kubernetes (k8s) best practices for writing, reviewing and deploying workloads on EKS, AKS, GKE, OKE or any cluster. Use when the task touches kubectl, Helm charts, Kustomize overlays, YAML manifests (Deployment, StatefulSet, Job, Service, Ingress/Gateway), RBAC, ServiceAccounts and workload identity (EKS Pod Identity/IRSA, AKS Workload Identity, GKE Workload Identity Federation, OKE workload identity), NetworkPolicy, Pod Security Standards, resource requests/limits, liveness/readiness/startup probes, PodDisruptionBudgets, HPA, GitOps with Argo CD or Flux, cluster provisioning with Terraform, or the read-only kubernetes MCP server. Covers reliability, security, cost and operations checklists with links to kubernetes.io and the EKS, AKS, GKE and OKE best-practice guides.
---

# Kubernetes

Applies to every cluster this project talks to: managed (EKS, AKS, GKE, OKE) or self-hosted.
Cloud-specific skills (`aws`, `azure`, `gcp`, `oci`) cover the account side; this skill covers
what runs inside the cluster and how the cluster is provisioned. Verified 2026-09-15.

## Non-negotiables

1. **Never commit a kubeconfig or a plaintext `Secret`.** Kubeconfigs carry credentials;
   `Secret` data is only base64. Use [External Secrets](https://external-secrets.io/latest/),
   [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets) or the
   [Secrets Store CSI driver](https://secrets-store-csi-driver.sigs.k8s.io/), and follow the
   [Kubernetes secrets good practices](https://kubernetes.io/docs/concepts/security/secrets-good-practices/).
   Local secrets go through agenix: `secret-add NAME`, then `secret-run --only NAME -- cmd`.
   Never print a secret or write it to disk.
2. **Read before write.** `kubectl get`/`describe`/`diff` first; `kubectl apply --dry-run=server`
   before `apply`; `helm diff` or `helm template` before `helm upgrade`. The MCP server is
   read-only by default (`references/mcp.md`).
3. **Declarative only.** Everything is a file in git, applied with `kubectl apply -k`, Helm or a
   GitOps controller ([declarative management](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/declarative-config/)).
   `kubectl edit`, `scale`, `set image` on a live cluster are for incidents, and must be
   followed by a commit that makes git match.
4. **Pin by digest, not tag.** `image: repo/app@sha256:…` so a rollout is reproducible and a
   re-pushed tag cannot change what runs ([images](https://kubernetes.io/docs/concepts/containers/images/)).
   Never use `:latest`.
5. **Least privilege everywhere.** No `cluster-admin` for humans or workloads, one
   ServiceAccount per workload, `automountServiceAccountToken: false` unless the pod calls
   the API ([RBAC good practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/)).
6. **Clusters are Terraform.** Provisioned with `terraform`; generic practice is in the `terraform` skill.
   Cluster state and workload state live in separate root modules (`references/terraform.md`).

## Workload checklist

Apply to every Deployment, StatefulSet, DaemonSet, Job and CronJob you write or review.
The why and the sources are in [`references/well-architected.md`](references/well-architected.md).

- [ ] `resources.requests` **and** `limits` on every container (memory limit = request for
      Guaranteed QoS; CPU limit optional but request mandatory).
- [ ] `readinessProbe` on anything behind a Service; `livenessProbe` only if a restart fixes
      the failure mode; `startupProbe` for slow starters. Probes never call downstream services.
- [ ] `replicas >= 2`, a `PodDisruptionBudget` with `minAvailable`/`maxUnavailable`, and
      `topologySpreadConstraints` across `topology.kubernetes.io/zone` and `kubernetes.io/hostname`.
- [ ] Rolling update strategy with `maxUnavailable: 0` for user-facing services, plus a
      `preStop` sleep and `terminationGracePeriodSeconds` >= app drain time.
- [ ] `securityContext`: `runAsNonRoot: true`, `allowPrivilegeEscalation: false`,
      `readOnlyRootFilesystem: true`, `capabilities.drop: ["ALL"]`,
      `seccompProfile.type: RuntimeDefault`. Passes the **restricted** Pod Security Standard.
- [ ] Image pinned by digest, from a registry you control, scanned (`trivy image`) and signed.
- [ ] One ServiceAccount per workload; `automountServiceAccountToken: false` by default.
- [ ] Config in ConfigMaps, secrets via External Secrets / CSI; env var names documented.
- [ ] Recommended labels (`app.kubernetes.io/name`, `.../instance`, `.../version`,
      `.../part-of`, `.../managed-by`) on every object.
- [ ] HPA on CPU/memory or custom metrics for stateless services; no HPA on Jobs.
- [ ] Logs to stdout/stderr as JSON; no log files inside the container.

## Namespace and cluster checklist

- [ ] Every namespace: `pod-security.kubernetes.io/enforce: restricted` label (or
      `baseline` with a dated exception), a `ResourceQuota`, a `LimitRange` with defaults,
      and a default-deny ingress **and** egress `NetworkPolicy`.
- [ ] Cluster API endpoint private or IP-restricted; audit logging on; control-plane logs
      shipped; encryption at rest for Secrets.
- [ ] Nodes: auto-upgrade/auto-repair on, managed node groups or node auto-provisioning,
      no SSH, minimal OS image, one Kubernetes minor behind latest at most.
- [ ] Add-ons installed by GitOps, not by hand: metrics-server, ingress/Gateway controller,
      cert-manager, External Secrets, policy engine (Kyverno / ValidatingAdmissionPolicy).
- [ ] Human access via cloud identity (IAM, Entra ID, Google groups, OCI IAM) mapped to
      RBAC groups; no static tokens, no shared kubeconfigs. See [`references/iam.md`](references/iam.md).

## Workflow for a change

1. Confirm context: `kubectl config current-context` and `kubens -c`. Never assume.
2. Write the manifest, chart values or Kustomize overlay in the repo.
3. Validate offline: `kustomize build overlays/dev | kubectl apply --dry-run=client -f -`,
   `helm lint`, `helm template … | trivy config -`, `trivy k8s --report summary` for live clusters.
4. Validate against the API: `kubectl apply --dry-run=server -k …` then `kubectl diff -k …`.
5. Apply to dev, watch: `kubectl rollout status deploy/NAME`, `stern NAME`, `k9s`.
6. Promote through environments by git (GitOps) or the same command with a different overlay.
7. Rollback plan before you start: `kubectl rollout undo` or `helm rollback NAME REV`.

## Reviewing manifests

Reject a PR that has any of: `:latest` or an unpinned tag; missing requests/limits; a
`privileged: true` or `hostNetwork`/`hostPID`/`hostPath` without a written justification;
`cluster-admin` or wildcard `verbs: ["*"]` / `resources: ["*"]` in RBAC; a `Secret` with
`data:`/`stringData:` filled in; a `NodePort` Service on a cloud cluster; a Deployment with
`replicas: 1` in prod; a probe hitting a downstream dependency; `imagePullPolicy: Always`
combined with a digest (pointless) or `Never` (breaks scheduling on new nodes).

## Tools in the devenv shell

`kubectl`, `helm`, `kustomize`, `k9s`, `kubectx`/`kubens`, `stern`, `terraform`, `trivy`.
Auth plugins come from the cloud module you enabled: `aws eks get-token` (aws),
`kubelogin` (azure), `gke-gcloud-auth-plugin` (gcp), `oci ce cluster create-kubeconfig` (oci).
Commands and flags: [`references/cli-cheatsheet.md`](references/cli-cheatsheet.md).

## References

| File | Use it for |
|---|---|
| [`references/well-architected.md`](references/well-architected.md) | Reliability, security, cost, operations and performance checks for workloads and clusters, with sources |
| [`references/landing-zone.md`](references/landing-zone.md) | Namespaces vs clusters, environments, multi-tenancy, GitOps with Argo CD / Flux, platform add-ons |
| [`references/iam.md`](references/iam.md) | RBAC least privilege, ServiceAccounts, workload identity on EKS, AKS, GKE and OKE, human access |
| [`references/cli-cheatsheet.md`](references/cli-cheatsheet.md) | kubectl, helm, kustomize, k9s, kubectx/kubens, stern, trivy |
| [`references/terraform.md`](references/terraform.md) | Provisioning clusters with Terraform, kubernetes/helm provider caveats, state layout |
| [`references/mcp.md`](references/mcp.md) | The read-only `kubernetes` MCP server, its flags, auth and the write opt-in |

Managed-service guides, in order of preference when they disagree with a generic rule:
[EKS Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/introduction.html),
[AKS best practices](https://learn.microsoft.com/en-us/azure/aks/best-practices),
[GKE best practices](https://docs.cloud.google.com/kubernetes-engine/docs/best-practices),
[OKE security best practices](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengbestpractices_topic-Security-best-practices.htm)
and the [Kubernetes security checklist](https://kubernetes.io/docs/concepts/security/security-checklist/).
