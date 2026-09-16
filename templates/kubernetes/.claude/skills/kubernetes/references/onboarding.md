# Kubernetes automated onboarding

From the Git project root inside the generated project shell:

```sh
cloud-onboard-kubernetes --context production --expected-server https://api.example.com --expected-principal reader --namespaces app --environment production
```

Replace example scope values. Use existing read-only credentials. Run
`cloud-onboard-kubernetes --help` for the exact argument contract.
The same arguments work with `just onboard kubernetes ...` inside the shell
or `nix run github:olafkfreund/cloud-projects-templates#onboard-kubernetes -- ...`
from a Git root. The flake app does not decrypt agenix secrets automatically.

## Coverage and permissions

Through `kubectl --context`, read Namespace metadata and list
Pods, Deployments, StatefulSets, DaemonSets, Services, Ingresses and
NetworkPolicies separately in each selected namespace. Use bounded list chunks
and selected output fields; never `get all`, Secret/ConfigMap reads, events,
logs or unrestricted YAML. Fields: UID/owner relationships, desired/ready counts,
container security-context booleans, request/limit presence, probe presence,
host namespace flags, Service exposure type and Ingress TLS-secret reference
presence (not secret names/content). Check explicit privileged=true,
allowPrivilegeEscalation=true and hostPID/hostIPC/hostNetwork=true as failed
baseline configuration; explicit false satisfies only that field. Missing
security settings need manual review of defaults/admission, not a fabricated
pass. Missing requests/limits/probes and desired-ready shortfall require review;
shortfall is a point-in-time observation, not a diagnosed outage. No
NetworkPolicies after a complete namespace list yields manual review; their
presence is never a pass for effective isolation. Permissions: selected
Namespace GET, namespaced GET/LIST for these resource kinds, identity review.
No cluster-wide workload listing, Nodes, RBAC dumps, scanner jobs or Trivy
execution in the automated collector.


## Reports

Reports use [schema version 2](../../cloud-onboarding/references/report-format.md)
and preserve earlier runs. Exit 0 means supported collection completed, even
when findings fail; 2 means a partial report; 1 means invocation, identity or
output failure. Denied reads, missing fields and truncated lists are never
passes. The environment labels the report, not a resource filter.

The collector is a bounded baseline, not complete inventory or compliance
certification. Keep reports private and ignored. Workload recovery, IAM, cost,
resilience and governance always retain manual review. No cloud mutation or
service activation is performed.

Official reference: [provider documentation](https://kubernetes.io/docs/concepts/security/pod-security-standards/).
