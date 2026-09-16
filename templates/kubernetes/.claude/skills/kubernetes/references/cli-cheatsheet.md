# CLI cheatsheet: kubectl, helm, kustomize, k9s, kubectx/kubens, stern, trivy

All tools are in the devenv shell. Always confirm the context first; the read/diff/apply
order in `SKILL.md` is mandatory. Sources: [kubectl quick reference](https://kubernetes.io/docs/reference/kubectl/quick-reference/),
[kubectl commands](https://kubernetes.io/docs/reference/generated/kubectl/kubectl-commands),
[Helm docs](https://helm.sh/docs/intro/using_helm/), [Kustomize reference](https://kubectl.docs.kubernetes.io/references/kustomize/).

## Context and auth

```bash
kubectl config current-context            # which cluster am I about to touch?
kubectl config get-contexts               # all contexts; never assume
kubectx                                    # switch context interactively / kubectx NAME
kubens                                     # switch default namespace / kubens NAME ; kubens -c prints current
kubectl auth whoami                        # identity the API server sees
kubectl auth can-i --list                  # what can I do here
kubectl auth can-i delete pods -n prod --as=system:serviceaccount:prod:api

# Fetch kubeconfig per cloud (exec plugins; nothing long-lived in the file)
aws eks update-kubeconfig --name C --region R
az aks get-credentials -g RG -n C && kubelogin convert-kubeconfig -l azurecli
gcloud container clusters get-credentials C --location L
oci ce cluster create-kubeconfig --cluster-id OCID --file "$KUBECONFIG" --token-version 2.0.0
```

Keep per-project kubeconfigs out of git: `export KUBECONFIG=$DEVENV_ROOT/.kube/config`
with `.kube/` in `.gitignore`
([multiple clusters](https://kubernetes.io/docs/tasks/access-application-cluster/configure-access-multiple-clusters/)).

## Read

```bash
kubectl get pods -A -o wide                          # everything, with node and IP
kubectl get deploy,sts,ds,job,cj -n NS
kubectl get pod NAME -o yaml | kubectl neat           # (neat is optional) strip managed fields
kubectl describe pod NAME                             # events at the bottom: read them first
kubectl get events -n NS --sort-by=.lastTimestamp
kubectl top pods -n NS --containers                   # needs metrics-server
kubectl top nodes
kubectl get pods -A --field-selector=status.phase!=Running
kubectl get pods -A -o custom-columns='NS:.metadata.namespace,POD:.metadata.name,IMG:.spec.containers[*].image'
kubectl api-resources --verbs=list -o name           # what kinds exist here
kubectl explain deploy.spec.strategy                  # schema docs offline
kubectl get netpol,pdb,hpa,resourcequota,limitrange -n NS
kubectl get ns -L pod-security.kubernetes.io/enforce
```

## Validate, diff, apply

```bash
kustomize build overlays/prod                            # render
kustomize build overlays/prod | kubectl apply --dry-run=client -f -   # schema check offline
kubectl apply --dry-run=server -k overlays/prod          # admission + validation, no write
kubectl diff -k overlays/prod                            # exit 1 = there is a diff
kubectl apply -k overlays/prod --server-side --field-manager=gitops
kubectl rollout status deploy/NAME -n NS --timeout=5m
kubectl rollout history deploy/NAME -n NS
kubectl rollout undo deploy/NAME -n NS [--to-revision=N]
kubectl rollout restart deploy/NAME -n NS                # rolling bounce (e.g. new ConfigMap)
```

[Declarative config](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/declarative-config/),
[Server-side apply](https://kubernetes.io/docs/reference/using-api/server-side-apply/),
[Kustomize in kubectl](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/).

## Debug

```bash
stern NAME -n NS                                 # tail logs across all pods matching NAME
stern -n NS -l app.kubernetes.io/name=api --since 10m -o json
stern --all-namespaces --exclude-container istio-proxy .   # everything except sidecars
kubectl logs deploy/NAME -n NS --previous       # crashed container's last output
kubectl logs POD -c CONTAINER -f --tail=200
kubectl exec -it POD -n NS -- sh                 # only if the image has a shell
kubectl debug -it POD --image=busybox:1.36 --target=CONTAINER   # ephemeral debug container
kubectl debug node/NODE -it --image=busybox:1.36                 # host shell via pod
kubectl port-forward svc/NAME 8080:80 -n NS
kubectl get endpointslices -n NS -l kubernetes.io/service-name=NAME   # is anything ready?
kubectl run tmp --rm -it --image=busybox:1.36 --restart=Never -- nslookup NAME.NS.svc
kubectl cordon NODE && kubectl drain NODE --ignore-daemonsets --delete-emptydir-data
kubectl uncordon NODE
k9s -n NS                                        # TUI: `:pods`, `l` logs, `d` describe, `s` shell, `ctrl-d` delete
k9s --readonly                                   # safe mode for browsing prod
```

[Debug running pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/),
[Debug applications](https://kubernetes.io/docs/tasks/debug/debug-application/),
[Debug clusters](https://kubernetes.io/docs/tasks/debug/debug-cluster/),
[k9s](https://k9scli.io/), [stern](https://github.com/stern/stern), [kubectx/kubens](https://github.com/ahmetb/kubectx).

## Helm

```bash
helm repo add NAME URL && helm repo update
helm search repo NAME --versions | head
helm show values REPO/CHART --version X.Y.Z > values.upstream.yaml   # read before overriding
helm pull oci://REGISTRY/CHART --version X.Y.Z                      # charts from OCI registries
helm lint ./chart -f values-prod.yaml
helm template REL ./chart -f values-prod.yaml -n NS | kubectl apply --dry-run=server -f -
helm template REL ./chart -f values-prod.yaml | trivy config -       # misconfig scan of rendered output
helm diff upgrade REL ./chart -f values-prod.yaml -n NS             # helm-diff plugin
helm upgrade --install REL ./chart -f values-prod.yaml -n NS --create-namespace \
  --version X.Y.Z --atomic --timeout 10m --wait
helm list -A ; helm history REL -n NS ; helm get values REL -n NS
helm rollback REL REV -n NS
helm uninstall REL -n NS --keep-history
```

Rules: pin `--version`; `--atomic` rolls back a failed upgrade; never `helm upgrade` a
release that GitOps owns (Argo/Flux will fight it); values files per environment, secrets
via External Secrets not `--set password=`.
[Charts](https://helm.sh/docs/topics/charts/), [Chart best practices](https://helm.sh/docs/chart_best_practices/),
[helm upgrade](https://helm.sh/docs/helm/helm_upgrade/), [helm rollback](https://helm.sh/docs/helm/helm_rollback/),
[helm template](https://helm.sh/docs/helm/helm_template/), [helm lint](https://helm.sh/docs/helm/helm_lint/),
[OCI registries](https://helm.sh/docs/topics/registries/), [Provenance](https://helm.sh/docs/topics/provenance/),
[helm-diff](https://github.com/databus23/helm-diff).

## Kustomize

```bash
kustomize build overlays/dev
kustomize build overlays/dev --enable-helm            # chart inflation inside kustomize
cd overlays/prod && kustomize edit set image api=registry/app@sha256:…   # promote a digest
kustomize edit set namespace shop-prod
kustomize cfg count overlays/prod                      # object counts by kind
```

Layout: `base/kustomization.yaml` with `resources:`; `overlays/<env>/kustomization.yaml`
with `resources: [../../base]`, `patches:`, `configMapGenerator`, `images:`. Prefer
`patches` (strategic merge / JSON6902) to copying whole files.
[Kustomization reference](https://kubectl.docs.kubernetes.io/references/kustomize/kustomization/),
[Kustomize guide](https://kubectl.docs.kubernetes.io/guides/introduction/kustomize/).

## Security scans

```bash
trivy image --severity HIGH,CRITICAL registry/app@sha256:…      # CVEs + secrets in the image
trivy config ./k8s                                               # misconfig in manifests/charts
trivy k8s --disable-node-collector --scanners misconfig --include-namespaces NS --report summary CONTEXT                                       # explicit context; no node jobs
trivy k8s --disable-node-collector --scanners misconfig --include-namespaces NS --report all CONTEXT
trivy fs --scanners secret .                                     # leaked kubeconfigs / tokens in the repo
kubectl get pods -A -o jsonpath='{range .items[*]}{.spec.containers[*].image}{"\n"}{end}' | grep -v '@sha256' # unpinned
```

[trivy k8s](https://trivy.dev/latest/docs/target/kubernetes/),
[trivy misconfiguration](https://trivy.dev/latest/docs/scanner/misconfiguration/).

## Batch and cron

```bash
kubectl create job manual-1 --from=cronjob/NAME -n NS   # run a CronJob now
kubectl get jobs -n NS --field-selector status.successful=0
kubectl patch cronjob NAME -n NS -p '{"spec":{"suspend":true}}'   # pause; commit the change too
```

[Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/),
[CronJobs](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/).

## Never

- `kubectl delete ns` or `delete --all` without `--dry-run=server` output pasted in the PR.
- `kubectl apply -f https://…` of an unpinned remote URL into a real cluster.
- `kubectl create secret … --from-literal=` outside a throwaway kind/dev cluster;
  local values go through `secret-run --only NAME -- kubectl …` and never echo.
- `kubectl config view --raw` or `cat ~/.kube/config` in a shared terminal or log.
- `helm install` into a namespace a GitOps controller manages.

## Onboarding discovery

Use the automated `cloud-onboard-kubernetes` collector first; see
[scope, examples, permissions and coverage](onboarding.md). The commands below
are supplementary manual investigation procedures, not additional automation.

```sh
kubectl --context "$CONTEXT" auth whoami
kubectl --context "$CONTEXT" auth can-i list pods --namespace "$NS"
kubectl --context "$CONTEXT" get pods --namespace "$NS" --chunk-size=100 \
  -o custom-columns='NAME:.metadata.name,PHASE:.status.phase,NODE:.spec.nodeName'
trivy k8s --disable-node-collector --scanners misconfig --include-namespaces "$NS" --report summary "$CONTEXT"
```

RBAC must allow the particular resources being listed; do not request Secret
reads or write permissions. kubectl follows chunked list pages; timeout, denied
kinds/namespaces, or unavailable API groups make coverage partial. Trivy node
checks are skipped because the node collector would create jobs. Review Trivy's
read permissions and scope for the pinned version before optional use; summary
output is not proof of complete CIS coverage. Do not save full pod YAML (it may
contain environment secrets), unrestricted events/logs, or Trivy raw resources.
Use the shared [report contract](../../cloud-onboarding/references/report-format.md).
Exec/debug pods, port forwarding, restarts, cordon/drain, and the mutating commands
elsewhere in this reference are outside onboarding.

Sources: [chunked API reads](https://kubernetes.io/docs/reference/using-api/api-concepts/#retrieving-large-results-sets-in-chunks),
[Trivy Kubernetes](https://trivy.dev/docs/latest/target/kubernetes/).
