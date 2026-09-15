# The `kubernetes` MCP server

The project's `.mcp.json` ships one Kubernetes server, read-only, pinned:

```json
{
  "mcpServers": {
    "kubernetes": {
      "command": "npx",
      "args": ["-y", "kubernetes-mcp-server@0.0.66", "--read-only", "--disable-multi-cluster"]
    }
  }
}
```

Upstream: [containers/kubernetes-mcp-server](https://github.com/containers/kubernetes-mcp-server)
(npm package `kubernetes-mcp-server`, a native Go binary; no kubectl or helm dependency).
Verified 2026-09-15.

## What the flags do

| Flag | Effect | Why it is on |
|---|---|---|
| `--read-only` | Refuses every write tool: create, update, patch, delete, exec, helm install/uninstall. Only get/list/describe/logs/events/top style tools remain. | Agents should propose manifests for you to apply through git, not mutate clusters directly. |
| `--disable-multi-cluster` | Ignores every context in the kubeconfig except the **current** one; equivalent to `cluster_provider_strategy = "disabled"` in the TOML config. | Stops an agent from wandering into prod because a prod context exists in the same kubeconfig. |
| `--disable-destructive` *(not set)* | Softer alternative to `--read-only`: allows create/apply but blocks delete and update-style destructive tools. Has no effect when `--read-only` is set. | Use it only for the write opt-in below. |

`npx -y` pins `0.0.66`; bump deliberately and re-read the changelog, since new tool sets
(Helm, Kiali, kcp) have been added between versions.

## Authentication

The server uses the **current context of your kubeconfig** (`$KUBECONFIG` or
`~/.kube/config`), exactly like `kubectl`. It inherits whatever that context's exec plugin
does, so:

1. Log in with the cloud CLI first (`aws sso login`, `az login`, `gcloud auth login`,
   `oci session authenticate`) and fetch the kubeconfig as described in
   `references/cli-cheatsheet.md`.
2. Run `kubectl config current-context` **before** starting the agent. The server pins to
   that context for its lifetime; switching with `kubectx` afterwards needs an MCP restart.
3. Point `KUBECONFIG` at a project-local file that only contains the non-prod context when
   working on app code; keep the prod kubeconfig in a separate file you only export for
   incident work.

No credentials are placed in `.mcp.json`. Never add `--kubeconfig` pointing at a committed
file, and never commit the kubeconfig itself.

## Give the agent identity `view` only

`--read-only` is enforced by the MCP process, not by the cluster. If the agent's session is
authenticated as you, it still *holds* your admin rights. Defence in depth: bind a
dedicated identity (a `k8s-agents` IdP group mapped through access entries / Entra /
Google groups / OCI IAM, or a dedicated ServiceAccount when running the server in-cluster)
to the built-in `view` ClusterRole, and use that identity's context for agent sessions.

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata: {name: agents-view}
roleRef: {apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: view}
subjects:
  - {kind: Group, name: k8s-agents, apiGroup: rbac.authorization.k8s.io}
```

`view` deliberately excludes `secrets` and `pods/exec`, which is the right shape for an
agent ([RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/),
[RBAC good practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/)).
Scope it to a namespace with a `RoleBinding` when the project owns only one namespace.
Upstream ships a guide for the in-cluster ServiceAccount variant in the repository's
`docs/getting-started-kubernetes.md`.

## Typical read-only session

- "List pods not Running in namespace X and show the events" -> `pods_list`, `events_list`.
- "Show the rendered Deployment `api` and tell me what violates the workload checklist" ->
  `resources_get`, then the agent reviews against `SKILL.md`.
- "Tail logs of the crashing container" -> `pods_log` with `previous: true`.
- The agent writes the fix as a manifest or Kustomize patch in the repo; **you** apply it via
  `kubectl diff` / `kubectl apply` or by merging into the GitOps repo.

## Write opt-in (project-local, deliberate)

Only when the project needs the agent to create objects, and only against non-prod:

1. In the project's own `.mcp.json` (never in the template repo) replace `--read-only` with
   `--disable-destructive`. Keep `--disable-multi-cluster`.
2. Make sure the current context is a dev cluster and the agent identity has at most `edit`
   in the target namespace, never `cluster-admin`.
3. Re-verify after each `devenv update`, because a regenerated `.mcp.json` merge keeps
   existing entries, so your local change persists silently.

**Warning.** `--disable-destructive` still allows `create` and `apply`, which can scale a
Deployment to 0, mount a hostPath, or create a `ClusterRoleBinding` if RBAC permits. It only
blocks the tools the server classifies as destructive (delete, update-style). It is not a
sandbox; RBAC is. Never enable it for a context that can reach prod, and never remove both
flags.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Forbidden` on list | Agent identity lacks `view` in that namespace | Bind `view` (above) or switch namespace |
| Server sees a stale/other cluster | Context switched after startup | Restart the MCP server (`claude mcp` reconnect) |
| `exec plugin: invalid apiVersion` / token errors | Cloud CLI not logged in or auth plugin missing | Log in with the cloud CLI; confirm `kubectl get ns` works in the same shell |
| Tool `resources_create_or_update` missing | `--read-only` active | Intended; write through git |
| `npx` downloads every start | No npm cache in the shell | Acceptable; version is pinned so behaviour is stable |
