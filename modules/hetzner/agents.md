## Hetzner Cloud

- **Skill:** `.claude/skills/hetzner`, covering architecture, project tokens, hcloud and Terraform.
- **Tokens:** API tokens are per project.
  - Agents and inspection: a **Read** token as `HCLOUD_TOKEN`.
  - Deploys: a Read & Write token as `HCLOUD_TOKEN_RW`, run as `secret-run --only HCLOUD_TOKEN_RW -- bash -c 'HCLOUD_TOKEN=$HCLOUD_TOKEN_RW terraform apply plan.tfplan'`.
- **MCP:** none configured, because Hetzner has no official server. Use `secret-run --only HCLOUD_TOKEN -- hcloud server list -o json`.
