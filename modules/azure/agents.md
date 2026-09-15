## Azure

- **Skill:** `.claude/skills/azure`, covering Well-Architected, CAF and landing zones, RBAC and Terraform.
- **Login:** `az login`, then `az account set --subscription <id>`. Prefer managed identities and workload identity federation over client secrets.
- **MCP:** `azure` runs with `--read-only`. Use an identity with the Reader role for agent sessions.
