## Cloudflare

- **Skill:** `.claude/skills/cloudflare`, covering reference architectures, token security, wrangler/cloudflared and Terraform provider v5.
- **Tokens:**
  - Agents: `CLOUDFLARE_READ_TOKEN`, from the "Read all resources" template plus `Account Resources: Read`.
  - Deploys: `CLOUDFLARE_API_TOKEN`, narrowly scoped.
  - Never use the Global API Key.
- **MCP:**
  - `cloudflare-docs` needs no auth.
  - `cloudflare-api` has **no read-only mode**, so the token is the boundary. Start agents with `secret-run --only CLOUDFLARE_READ_TOKEN -- claude`.
  - If a browser authorisation prompt appears, the token is invalid. **Don't approve it**; rotate the token instead.
