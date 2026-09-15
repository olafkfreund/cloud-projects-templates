# DigitalOcean MCP servers

Two servers are configured in the generated project's `.mcp.json` (merged from `modules/digitalocean/mcp.json`). Both are pinned; neither embeds a credential. Read-only is enforced by the token, not by the server.

## Configuration (as shipped)

```json
{
  "mcpServers": {
    "digitalocean-docs": { "type": "http", "url": "https://docs.mcp.digitalocean.com/mcp" },
    "digitalocean": {
      "command": "npx",
      "args": ["-y", "@digitalocean/mcp@1.0.70", "--services", "accounts,droplets,doks,apps,databases,networking,spaces,volumes,insights"],
      "env": { "DIGITALOCEAN_API_TOKEN": "${DIGITALOCEAN_READ_TOKEN}" }
    }
  }
}
```

### `digitalocean-docs` — documentation server

Remote HTTP server at `https://docs.mcp.digitalocean.com/mcp`. Searches and reads docs.digitalocean.com; no token, and the Authorization header "can be omitted" for it ([configure remote MCP](https://docs.digitalocean.com/reference/mcp/configure-mcp/)). Use it to verify API fields, limits and how-to steps before writing Terraform, instead of relying on memory.

### `digitalocean` — API server (local stdio)

Source: [digitalocean-labs/mcp-digitalocean](https://github.com/digitalocean-labs/mcp-digitalocean), npm package [`@digitalocean/mcp`](https://www.npmjs.com/package/@digitalocean/mcp), documented at [use local MCP](https://docs.digitalocean.com/reference/mcp/use-local-mcp/). The token is read from `DIGITALOCEAN_API_TOKEN`; the `${DIGITALOCEAN_READ_TOKEN}` reference is resolved by Claude Code from the environment the agent was started with.

| Setting | Value | Effect |
|---|---|---|
| `@digitalocean/mcp@1.0.70` | pinned version | `npx -y` caches by version; do not switch to `@latest` (supply chain, and 1.0.70 is what the init check validated) |
| `--services …` | `accounts,droplets,doks,apps,databases,networking,spaces,volumes,insights` | Loads only these tool groups, keeping the tool list small for the model |
| `DIGITALOCEAN_API_TOKEN` | `${DIGITALOCEAN_READ_TOKEN}` | Read Only PAT (`api:read`) with expiry; the API refuses every write |

**There is no read-only flag.** The server exposes create/delete tools for Droplets, databases, volumes, registries and more ([MCP tools](https://docs.digitalocean.com/reference/mcp/mcp-tools/)); the only thing stopping them is the token's scope. That is why `DIGITALOCEAN_READ_TOKEN` must be a **Read Only** token and never a Full Access one (see [security.md](security.md)). `--services` limits which tools exist; it does not limit what a tool may do.

Available `--services` values (from the [repository README](https://github.com/digitalocean-labs/mcp-digitalocean)): `accounts`, `apps`, `databases`, `dedicated-inference`, `docr`, `docs`, `doks`, `droplets`, `functions`, `genai-batchinference`, `genai-custom-models`, `genai-evaluation`, `genai-inferencerouter`, `inference-modelcatalog`, `insights`, `marketplace`, `networking`, `nfs`, `spaces`, `vector-databases`, `volumes`. Add `docr` or `functions` in the project's `.mcp.json` if a task needs them; `docs` is redundant with `digitalocean-docs`.

## Why local stdio and not the hosted endpoints

DigitalOcean also hosts one remote server per service at `https://<service>.mcp.digitalocean.com/mcp`, authenticated with an `Authorization: Bearer <token>` header ([configure remote MCP](https://docs.digitalocean.com/reference/mcp/configure-mcp/)). We do not ship those because the header value would have to be built from an environment variable, and Claude Code may blank credential-like variables in remote-server headers, so the connection fails silently. The local `npx` server reads the token from its own `env` block, which works. Switch to the hosted servers only if you have verified header expansion in your client version; the token rules stay the same.

## Authentication

Start the agent with the read token in its environment. The MCP child inherits it and `${DIGITALOCEAN_READ_TOKEN}` resolves:

```bash
secret-run --only DIGITALOCEAN_READ_TOKEN -- claude
```

Nothing is written to `.mcp.json` or disk. The token must be:

- a personal access token with the **Read Only** scope (`api:read`) ([create a PAT](https://docs.digitalocean.com/reference/api/create-personal-access-token/)),
- created with an expiry, ideally from a **Resource Viewer** account so even a scope mistake cannot write ([predefined roles](https://docs.digitalocean.com/platform/teams/roles/predefined/)),
- stored with `secret-add DIGITALOCEAN_READ_TOKEN`, never in shell rc files.

Read Only still returns some sensitive data (database connection strings via `databases`, kubeconfig via `doks`). If the agent does not need those, drop the service from `--services` in the project's `.mcp.json`.

## Opting in to writes (per project)

Only when a project needs the agent to change DigitalOcean resources, and only in that project's own `.mcp.json`:

1. Create a **Custom Scopes** token with exactly the `resource:action` scopes the task needs and a short expiry ([scopes](https://docs.digitalocean.com/reference/api/scopes/)). Store it as `DIGITALOCEAN_MCP_WRITE_TOKEN` with `secret-add`.
2. Change `mcpServers.digitalocean.env.DIGITALOCEAN_API_TOKEN` to `${DIGITALOCEAN_MCP_WRITE_TOKEN}` and trim `--services` to the groups the task touches.
3. Start the agent with `secret-run --only DIGITALOCEAN_MCP_WRITE_TOKEN -- claude`, in a non-production team or project.
4. Record the change and the reason in the PR that introduces it; revoke the token when the work is done.

**Warning.** With a write token the agent can create, resize, power off and delete Droplets, databases, volumes and clusters, and change firewalls, with no confirmation step from the server. Mistakes are not reversible by `git revert`. Prefer the alternative: keep the MCP server read-only, have the agent write Terraform, and apply through `secret-run --only DIGITALOCEAN_ACCESS_TOKEN -- terraform apply` after review. Never put a Full Access token in any `.mcp.json`.

## Verification

```bash
claude mcp list                                        # digitalocean and digitalocean-docs connected
# in the agent: "list my Droplets"                     → succeeds (read)
# in the agent: "create a Droplet named test"          → API returns 403 (Read Only token)
```

The plan's manual check: run `secret-run --only DIGITALOCEAN_READ_TOKEN -- claude` in a generated project, confirm `/mcp` shows both servers, a list works and a create is refused.

## Troubleshooting

- **`401 Unable to authenticate you` in tool output**: the agent was started without `secret-run --only DIGITALOCEAN_READ_TOKEN`, or the token expired. Check the expiry on the Tokens page and restart the agent (MCP children inherit the environment at start).
- **`403` on a read**: the token was made from an account whose role cannot see that resource; Read Only follows the team role.
- **A write succeeded**: the token is not Read Only. Revoke it immediately, check the security history, and re-create with `api:read` ([view security history](https://docs.digitalocean.com/platform/teams/how-to/view-security-history/)).
- **Tool missing**: its service is not in `--services`; add it in the project's `.mcp.json`.
- **`npx` downloads every start**: the version pin is missing; restore `@digitalocean/mcp@1.0.70`. `npx -y` needs Node in the devenv shell.
- **`digitalocean-docs` fails to connect**: it is a remote HTTP server; check outbound HTTPS. It needs no token, so an auth error means a proxy is injecting headers.
