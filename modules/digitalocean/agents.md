## DigitalOcean

- **Skill:** `.claude/skills/digitalocean`, covering architecture, PAT scopes, doctl and Terraform.
- **Tokens:**
  - Agents: `DIGITALOCEAN_READ_TOKEN`, a personal access token with the **Read Only** scope and an expiry.
  - Deploys: `DIGITALOCEAN_ACCESS_TOKEN`, with custom scopes and an expiry.
- **MCP:**
  - `digitalocean-docs` needs no auth.
  - `digitalocean` has **no read-only mode**, so the token is the boundary. Start agents with `secret-run --only DIGITALOCEAN_READ_TOKEN -- claude`.
