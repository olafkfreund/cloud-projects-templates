## Kubernetes

- **Skill:** `.claude/skills/kubernetes`, covering workload and cluster best practice, RBAC and GitOps.
- **Access:** the current kubeconfig context. Use a context bound to the `view` ClusterRole for agent sessions. Never commit kubeconfigs.
- **MCP:** `kubernetes` runs with `--read-only --disable-multi-cluster`.
