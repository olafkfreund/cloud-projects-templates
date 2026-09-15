# Well-architected Kubernetes workloads and clusters

Checks grouped by pillar. Each item says what to do, why, and where the rule comes from.
Sources verified 2026-09-15. Managed-service guides:
[EKS Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/introduction.html),
[AKS best practices](https://learn.microsoft.com/en-us/azure/aks/best-practices),
[GKE best practices](https://docs.cloud.google.com/kubernetes-engine/docs/best-practices),
[OKE best practices: security](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengbestpractices_topic-Security-best-practices.htm),
[cluster management](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengbestpractices_topic-Cluster-Management-best-practices.htm),
[networking](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengbestpractices_topic-Networking-best-practices.htm),
[storage](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengbestpractices_topic-Storage-best-practices.htm).

## Reliability

- **Set requests on every container.** The scheduler places pods by requests; a pod without
  them is BestEffort and the first to be evicted under node pressure.
  [Resource management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/),
  [Pod QoS](https://kubernetes.io/docs/concepts/workloads/pods/pod-qos/),
  [Node-pressure eviction](https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/).
- **Memory limit = memory request.** Memory is incompressible; an overcommitted node OOM-kills
  pods. Equal values give Guaranteed QoS for that resource. CPU limits are optional: CPU is
  throttled, not killed, and a limit far above the request wastes headroom
  ([EKS reliability: applications](https://docs.aws.amazon.com/eks/latest/best-practices/application.html)).
- **Readiness probes on every Service-backed pod.** Without one, traffic reaches a pod that is
  still starting. Probes check only the container's own health, never a dependency, or one
  outage cascades. Liveness only when a restart actually fixes the failure; startup probes for
  slow initialisation so liveness doesn't kill a booting pod.
  [Configure probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).
- **PodDisruptionBudget on every multi-replica workload.** Node drains, upgrades and the
  cluster autoscaler honour PDBs; without one an upgrade can take every replica down at
  once. Set `maxUnavailable: 1` or `minAvailable`, never a PDB that blocks all eviction on a
  single-replica app (it blocks node upgrades).
  [Configure a PDB](https://kubernetes.io/docs/tasks/run-application/configure-pdb/),
  [Safely drain a node](https://kubernetes.io/docs/tasks/administer-cluster/safely-drain-node/).
- **Spread replicas.** `topologySpreadConstraints` across `topology.kubernetes.io/zone` and
  `kubernetes.io/hostname` with `whenUnsatisfiable: DoNotSchedule` for prod. Anti-affinity
  is the older, coarser tool.
  [Topology spread](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/),
  [AKS multi-region](https://learn.microsoft.com/en-us/azure/aks/operator-best-practices-multi-region).
- **Graceful shutdown.** SIGTERM -> app stops accepting, drains, exits. Add a `preStop`
  sleep of a few seconds so endpoint removal propagates before the process stops, and set
  `terminationGracePeriodSeconds` above the drain time.
  [Container lifecycle hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/),
  [Pod lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/).
- **Rolling updates with `maxUnavailable: 0`, `maxSurge: 1`** for user-facing services, so
  capacity never drops during a rollout.
  [Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/).
- **Priority classes.** Give platform components (ingress, DNS, metrics) a higher
  `priorityClassName` than tenant workloads so they win under pressure.
  [Pod priority and preemption](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/).
- **Autoscale nodes and pods.** HPA for pods; cluster autoscaler, Karpenter (EKS), node
  auto-provisioning (AKS, GKE) or the OKE cluster autoscaler for nodes. HPA and VPA on the
  same metric fight each other.
  [HPA](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/),
  [Autoscaling overview](https://kubernetes.io/docs/concepts/workloads/autoscaling/),
  [Karpenter on EKS](https://docs.aws.amazon.com/eks/latest/userguide/karpenter.html),
  [AKS node autoprovisioning](https://learn.microsoft.com/en-us/azure/aks/node-autoprovision),
  [GKE node auto-provisioning](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/node-auto-provisioning),
  [OKE cluster autoscaler](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengusingclusterautoscaler.htm).
- **Stay within the version skew policy.** kubectl and kubelet at most one minor from the API
  server; managed services force-upgrade end-of-life versions.
  [Version skew policy](https://kubernetes.io/releases/version-skew-policy/),
  [EKS versions](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html),
  [AKS upgrade](https://learn.microsoft.com/en-us/azure/aks/upgrade-cluster),
  [GKE release channels](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/release-channels),
  [OKE upgrades](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengupgradingk8smasternode.htm).
- **StatefulSets and storage.** Use a StorageClass with `volumeBindingMode: WaitForFirstConsumer`
  so the volume lands in the pod's zone; back up PVs outside the cluster.
  [Persistent volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/),
  [AKS storage](https://learn.microsoft.com/en-us/azure/aks/operator-best-practices-storage).

## Security

- **Pod Security Standards, `restricted`, enforced per namespace** via the label
  `pod-security.kubernetes.io/enforce: restricted`; use `warn`/`audit` first on legacy
  namespaces. PodSecurityPolicy is gone.
  [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/),
  [Pod Security Admission](https://kubernetes.io/docs/concepts/security/pod-security-admission/),
  [Namespace labels](https://kubernetes.io/docs/tasks/configure-pod-container/enforce-standards-namespace-labels/),
  [EKS pod security](https://docs.aws.amazon.com/eks/latest/best-practices/pod-security.html),
  [AKS pod security](https://learn.microsoft.com/en-us/azure/aks/developer-best-practices-pod-security),
  [GKE PodSecurity](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/podsecurityadmission).
- **Container securityContext** that satisfies `restricted`: `runAsNonRoot`,
  `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, `seccompProfile:
  RuntimeDefault`, `readOnlyRootFilesystem: true` (mount an `emptyDir` for scratch).
  [Security context](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/),
  [Kernel security constraints](https://kubernetes.io/docs/concepts/security/linux-kernel-security-constraints/).
- **Default-deny NetworkPolicy per namespace**, ingress and egress, then allow-list. Requires
  a CNI that enforces policy (VPC CNI with network policy on EKS, Azure CNI / Cilium on AKS,
  Dataplane V2 on GKE, VCN-native + Calico on OKE).
  [Network policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/),
  [EKS network security](https://docs.aws.amazon.com/eks/latest/best-practices/network-security.html),
  [AKS network policies](https://learn.microsoft.com/en-us/azure/aks/use-network-policies),
  [GKE network policy](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/network-policy),
  [OKE Calico](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengsettingupcalico.htm).
- **Images: pin by digest, scan, sign, private registry.** A tag is mutable; a digest is
  content-addressed. Scan in CI with `trivy image`, sign with cosign, admit only signed
  images (Kyverno, Binary Authorization on GKE).
  [Images](https://kubernetes.io/docs/concepts/containers/images/),
  [EKS image security](https://docs.aws.amazon.com/eks/latest/best-practices/image-security.html),
  [GKE Binary Authorization](https://docs.cloud.google.com/binary-authorization/docs/overview),
  [cosign](https://docs.sigstore.dev/cosign/signing/signing_with_containers/),
  [trivy k8s](https://trivy.dev/latest/docs/target/kubernetes/).
- **Secrets never in git and never plain in the cluster if avoidable.** Enable encryption at
  rest (KMS-backed on every managed service), sync from the cloud secret store with External
  Secrets or the CSI driver, and keep `Secret` RBAC narrow (`get` on named secrets, no `list`).
  [Secrets good practices](https://kubernetes.io/docs/concepts/security/secrets-good-practices/),
  [Encrypt data at rest](https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/),
  [EKS secrets](https://docs.aws.amazon.com/eks/latest/best-practices/data-encryption-and-secrets-management.html),
  [AKS CSI secrets](https://learn.microsoft.com/en-us/azure/aks/csi-secrets-store-driver),
  [GKE Secret Manager CSI](https://docs.cloud.google.com/secret-manager/docs/secret-manager-managed-csi-component),
  [OKE encrypting data](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengencryptingdata.htm).
- **Private API endpoint, audit logs, admission policy.** Restrict the endpoint to your
  network or CIDRs, ship audit logs, and enforce org rules with
  ValidatingAdmissionPolicy or Kyverno (no `latest`, required labels, required probes).
  [Securing a cluster](https://kubernetes.io/docs/tasks/administer-cluster/securing-a-cluster/),
  [Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/),
  [ValidatingAdmissionPolicy](https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/),
  [Kyverno](https://kyverno.io/docs/),
  [EKS endpoint access](https://docs.aws.amazon.com/eks/latest/userguide/cluster-endpoint.html),
  [AKS private clusters](https://learn.microsoft.com/en-us/azure/aks/private-clusters),
  [GKE private clusters](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/private-cluster-concept),
  [GKE hardening](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/hardening-your-cluster),
  [OKE security](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/oke_security.htm).
- **RBAC and identity:** see `iam.md`. Run through the
  [Kubernetes security checklist](https://kubernetes.io/docs/concepts/security/security-checklist/)
  before go-live.

## Cost

- **Right-size requests from observed usage.** Use VPA in recommendation mode, or the cloud
  cost tools, and revisit quarterly. Over-requesting is the biggest waste in most clusters.
  [VPA](https://github.com/kubernetes/autoscaler/tree/master/vertical-pod-autoscaler),
  [EKS cost optimisation](https://docs.aws.amazon.com/eks/latest/best-practices/cost-optimization.html),
  [GKE cost-effective apps](https://docs.cloud.google.com/architecture/best-practices-for-running-cost-effective-kubernetes-applications-on-gke),
  [AKS resource management](https://learn.microsoft.com/en-us/azure/aks/developer-best-practices-resource-management).
- **Bin-pack with the node autoscaler** and use spot/preemptible node pools for
  stateless, PDB-protected workloads, tainted so only tolerant pods land there.
  [EKS compute cost](https://docs.aws.amazon.com/eks/latest/best-practices/cost-opt-compute.html),
  [Taints and tolerations](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/).
- **ResourceQuota + LimitRange per namespace** so one team cannot consume the cluster and
  pods without requests get sane defaults.
  [Resource quotas](https://kubernetes.io/docs/concepts/policy/resource-quotas/),
  [Limit ranges](https://kubernetes.io/docs/concepts/policy/limit-range/).
- **Scale to zero what can be.** CronJobs over always-on pollers; dev namespaces scaled
  down off-hours; Autopilot (GKE) or virtual nodes where pod-billing beats node-billing.
  [GKE Autopilot](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/autopilot-overview).
- **Labels for showback**: `app.kubernetes.io/part-of`, team and cost-centre labels on
  namespaces and workloads.
  [Recommended labels](https://kubernetes.io/docs/concepts/overview/working-with-objects/common-labels/).

## Operational excellence

- **GitOps.** Argo CD or Flux reconciles git into the cluster; nobody applies to prod by
  hand. See `landing-zone.md`.
- **Server-side apply and `kubectl diff`** in CI; `--dry-run=server` catches admission
  rejections before merge.
  [Server-side apply](https://kubernetes.io/docs/reference/using-api/server-side-apply/).
- **Observability**: metrics-server for HPA and `kubectl top`, Prometheus-style metrics,
  JSON logs on stdout, traces with a context header.
  [Logging architecture](https://kubernetes.io/docs/concepts/cluster-administration/logging/),
  [Resource metrics pipeline](https://kubernetes.io/docs/tasks/debug/debug-cluster/resource-metrics-pipeline/),
  [EKS control-plane logs](https://docs.aws.amazon.com/eks/latest/userguide/control-plane-logs.html).
- **Deprecation hygiene.** Check API removals before every upgrade
  ([deprecation guide](https://kubernetes.io/docs/reference/using-api/deprecation-guide/));
  add-ons via managed add-ons or GitOps
  ([EKS add-ons](https://docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html),
  [Kubernetes addons](https://kubernetes.io/docs/concepts/cluster-administration/addons/)).
- **Deployment safeguards / policy at admission** to stop known-bad manifests early
  ([AKS deployment safeguards](https://learn.microsoft.com/en-us/azure/aks/deployment-safeguards)).
- **Runbook per service**: how to roll back, scale, drain, and who is paged.

## Performance

- **Requests match real steady-state usage**; CPU limits only where noisy neighbours matter.
- **Topology-aware routing and zone-local traffic** to cut cross-zone latency and egress cost
  ([Service](https://kubernetes.io/docs/concepts/services-networking/service/)).
- **Gateway API over Ingress** for new work: typed routes, shared gateways, per-namespace
  route ownership.
  [Gateway API](https://kubernetes.io/docs/concepts/services-networking/gateway/),
  [gateway-api.sigs.k8s.io](https://gateway-api.sigs.k8s.io/).
- **Cluster scalability limits**: watch object counts, Service/endpoint churn and IP
  exhaustion (VPC CNI prefix delegation, Azure CNI overlay).
  [EKS scalability](https://docs.aws.amazon.com/eks/latest/best-practices/scalability.html),
  [GKE scalability](https://docs.cloud.google.com/kubernetes-engine/docs/best-practices/scalability),
  [EKS VPC CNI](https://docs.aws.amazon.com/eks/latest/best-practices/aws-vpc-cni.html),
  [Azure CNI overlay](https://learn.microsoft.com/en-us/azure/aks/azure-cni-overlay),
  [OKE pod networking](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengpodnetworking.htm).
- **Reserve node resources** for kubelet and the OS so pods can't starve the node
  ([Reserve compute resources](https://kubernetes.io/docs/tasks/administer-cluster/reserve-compute-resources/)).

## Minimal compliant Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  labels: {app.kubernetes.io/name: api, app.kubernetes.io/part-of: shop}
spec:
  replicas: 3
  strategy: {type: RollingUpdate, rollingUpdate: {maxUnavailable: 0, maxSurge: 1}}
  selector: {matchLabels: {app.kubernetes.io/name: api}}
  template:
    metadata:
      labels: {app.kubernetes.io/name: api}
    spec:
      serviceAccountName: api
      automountServiceAccountToken: false
      terminationGracePeriodSeconds: 30
      securityContext: {runAsNonRoot: true, seccompProfile: {type: RuntimeDefault}}
      topologySpreadConstraints:
        - {maxSkew: 1, topologyKey: topology.kubernetes.io/zone, whenUnsatisfiable: DoNotSchedule,
           labelSelector: {matchLabels: {app.kubernetes.io/name: api}}}
      containers:
        - name: api
          image: registry.example.com/shop/api@sha256:0000000000000000000000000000000000000000000000000000000000000000
          ports: [{containerPort: 8080, name: http}]
          resources:
            requests: {cpu: 250m, memory: 256Mi}
            limits: {memory: 256Mi}
          readinessProbe: {httpGet: {path: /readyz, port: http}, periodSeconds: 5}
          livenessProbe: {httpGet: {path: /livez, port: http}, periodSeconds: 10, failureThreshold: 3}
          startupProbe: {httpGet: {path: /livez, port: http}, failureThreshold: 30, periodSeconds: 2}
          lifecycle: {preStop: {sleep: {seconds: 5}}}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: {drop: ["ALL"]}
          volumeMounts: [{name: tmp, mountPath: /tmp}]
      volumes: [{name: tmp, emptyDir: {}}]
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata: {name: api}
spec:
  maxUnavailable: 1
  selector: {matchLabels: {app.kubernetes.io/name: api}}
```
