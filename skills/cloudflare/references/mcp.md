# Cloudflare MCP servers

Two servers are configured in the generated project's `.mcp.json` (merged from `modules/cloudflare/mcp.json`). Neither embeds a credential. Read-only is enforced by the **token**, not by the server: Cloudflare's API server has no server-side read-only mode.

## Configuration (as shipped)

```json
{
  "mcpServers": {
    "cloudflare-docs": { "type": "http", "url": "https://docs.mcp.cloudflare.com/mcp" },
    "cloudflare-api": {
      "command": "npx",
      "args": ["-y", "mcp-remote@0.14.2", "https://mcp.cloudflare.com/mcp", "--header", "Authorization:${CF_MCP_AUTH}"],
      "env": { "CF_MCP_AUTH": "Bearer ${CLOUDFLARE_READ_TOKEN}" }
    }
  }
}
```

Start the agent with the read token decrypted into its environment:

```bash
secret-run --only CLOUDFLARE_READ_TOKEN -- claude
```

### `cloudflare-docs` — Documentation server

`https://docs.mcp.cloudflare.com/mcp`, listed under [Cloudflare's own MCP servers](https://developers.cloudflare.com/agents/model-context-protocol/cloudflare/servers-for-cloudflare/). No auth, read-only, searches developers.cloudflare.com. Use it to verify API fields, plan limits and resource names before writing Terraform instead of relying on memory.

### `cloudflare-api` — Cloudflare API server ("Code Mode")

`https://mcp.cloudflare.com/mcp` is Cloudflare's consolidated API server. Instead of exposing thousands of tools it uses a search-and-execute pattern: the model writes JavaScript against the typed OpenAPI spec inside a sandbox ([servers for Cloudflare](https://developers.cloudflare.com/agents/model-context-protocol/cloudflare/servers-for-cloudflare/), [Code Mode](https://developers.cloudflare.com/agents/tools/codemode/)). It accepts either OAuth or an API token as a Bearer `Authorization` header ([mcp-server-cloudflare README](https://github.com/cloudflare/mcp-server-cloudflare)).

**There is no read-only flag.** Whatever the token can do, the agent can do. That is why the shipped config takes `CLOUDFLARE_READ_TOKEN`, a token created from the "Read all resources" template plus `Account Resources: Read` ([token templates](https://developers.cloudflare.com/fundamentals/api/reference/template/)), and why the deploy token `CLOUDFLARE_API_TOKEN` is never referenced in `.mcp.json`. A write attempted through the read token gets a 403 from the API, which is the intended outcome.

### Why `mcp-remote` and not `"type": "http"` with a header

Claude Code expands `${VAR}` in `url` and `headers` of remote servers, but deliberately reads credential-like variables as **empty** there so a project's `.mcp.json` cannot exfiltrate them ([Claude Code MCP docs](https://code.claude.com/docs/en/mcp)). A stdio server's `env` block is not blanked. `mcp-remote` is a community stdio-to-HTTP bridge ([npm](https://www.npmjs.com/package/mcp-remote), [README](https://github.com/geelen/mcp-remote)); it forwards `--header` values on every request. Its README also documents the `Authorization:${VAR}` form with no spaces: some clients mangle spaces inside `args`, so the header value with its space lives in `env` ([mcp-remote README](https://github.com/geelen/mcp-remote)). The version is pinned (`0.14.2`, [npm registry](https://registry.npmjs.org/mcp-remote/0.14.2)) because it is a third-party bridge that sees the token; bump it deliberately, not via `@latest`.

### Verified: OAuth fallback on a bad token

Tested with `mcp-remote@0.14.2`: if `CLOUDFLARE_READ_TOKEN` is invalid, expired or missing, Cloudflare answers 401 and `mcp-remote` **falls back to browser OAuth**, printing:

```
Please authorize this client by visiting https://mcp.cloudflare.com/authorize?...
```

There is no flag to disable that fallback. **Do not approve the prompt.** The OAuth grant is chosen interactively and can carry broader, write-capable scopes, which silently bypasses the read-only token boundary. Instead:

```bash
# 1. create a fresh "Read all resources" + "Account Resources: Read" token in the dashboard
secret-add CLOUDFLARE_READ_TOKEN          # 2. store it (overwrites the old value)
secret-run --only CLOUDFLARE_READ_TOKEN -- claude   # 3. restart the agent
```

Then run `/mcp` and confirm `cloudflare-api` is connected without an authorize URL having been printed.

## Alternative: OAuth without a token

```json
{ "mcpServers": { "cloudflare-api": { "type": "http", "url": "https://mcp.cloudflare.com/mcp" } } }
```

Run `/mcp` in Claude Code and complete the browser login ([Claude Code MCP docs](https://code.claude.com/docs/en/mcp)). Scopes are picked interactively at consent time, so they cannot be pinned in the repo, which is why this is documented but not shipped. If you use it, pick the narrowest read scopes offered and treat the session as write-capable until proven otherwise.

## Optional read-only product servers

Cloudflare publishes product-specific servers ([list](https://developers.cloudflare.com/agents/model-context-protocol/cloudflare/servers-for-cloudflare/)). These are safe to add to a project's `.mcp.json` with the same `mcp-remote` pattern and `CLOUDFLARE_READ_TOKEN`:

| Name | URL | Reads |
|---|---|---|
| `cloudflare-observability` | `https://observability.mcp.cloudflare.com/mcp` | Workers logs and analytics |
| `cloudflare-radar` | `https://radar.mcp.cloudflare.com/mcp` | Internet traffic insights |
| `cloudflare-dns-analytics` | `https://dns-analytics.mcp.cloudflare.com/mcp` | DNS query analytics |
| `cloudflare-auditlogs` | `https://auditlogs.mcp.cloudflare.com/mcp` | Account audit log queries |

Not read-only, do not add without understanding they change state: **Workers Bindings** (`bindings.mcp.cloudflare.com`, creates KV/R2/D1), **Workers Builds** (`builds.mcp.cloudflare.com`, triggers builds), **Container** (`containers.mcp.cloudflare.com`, runs sandboxes). With the read token they mostly fail; with a write token they act.

## Write opt-in

Write access is per project, never in the shared module. Steps:

1. Create a separate account-owned token scoped to exactly the resources the agent may change (for example `Zone: DNS: Edit` on one zone), with an IP filter and TTL ([restrict tokens](https://developers.cloudflare.com/fundamentals/api/how-to/restrict-tokens/)). Do not reuse `CLOUDFLARE_API_TOKEN`.
2. `secret-add CLOUDFLARE_MCP_WRITE_TOKEN`.
3. In the project's own `.mcp.json` add a second server, for example `cloudflare-api-write`, identical to `cloudflare-api` but with `"CF_MCP_AUTH": "Bearer ${CLOUDFLARE_MCP_WRITE_TOKEN}"`.
4. Start with `secret-run --only CLOUDFLARE_READ_TOKEN,CLOUDFLARE_MCP_WRITE_TOKEN -- claude`.

**Warning:** with a write token every Code Mode call is a real change: DNS records, rulesets, Workers and Access policies can be created or deleted with no confirmation step and no server-side guard. Keep the write server in the project, keep the token scope minimal, revoke it when the task ends, and check [audit logs](https://developers.cloudflare.com/fundamentals/account/account-security/audit-logs/) afterwards.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `cloudflare-api` shows `! Needs authentication` or prints an authorize URL | Token rejected; OAuth fallback | See "Verified: OAuth fallback" above; never approve |
| Reads work, a write returns 403 | Working as designed | Use Terraform with `CLOUDFLARE_API_TOKEN` or the write opt-in |
| `npx` cannot find `mcp-remote` | Offline or npm cache | `npx -y mcp-remote@0.14.2 --help` once online; the version is pinned in `.mcp.json` |
| Header arrives empty | `${CF_MCP_AUTH}` unset because agent was not started under `secret-run` | `secret-run --only CLOUDFLARE_READ_TOKEN -- claude` |
| Docs server answers but API server times out | `mcp.cloudflare.com` needs a valid `Authorization` header; docs server needs none | Check the token with `/user/tokens/verify` (see [cli-cheatsheet.md](cli-cheatsheet.md)) |
