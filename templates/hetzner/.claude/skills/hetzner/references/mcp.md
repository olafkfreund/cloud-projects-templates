# Hetzner and MCP

**No MCP server is configured for Hetzner in this project, because Hetzner ships none.** The [hetznercloud GitHub organisation](https://github.com/orgs/hetznercloud/repositories?q=mcp) has no repository matching `mcp` (checked 2026-09-15), and the official docs at [docs.hetzner.com](https://docs.hetzner.com/) and the [API reference](https://docs.hetzner.cloud/) do not mention one. The generated project's `.mcp.json` therefore contains only the `terraform` server from the base template; `modules/hetzner` has no `mcp.json`.

## Community servers (not vetted)

Hetzner's own [awesome-hcloud](https://github.com/hetznercloud/awesome-hcloud) list names two community MCP servers under "Integrations":

| Name | Repository | Note |
|---|---|---|
| mcp-hetzner | [dkruyt/mcp-hetzner](https://github.com/dkruyt/mcp-hetzner) | Community. Not reviewed by this project. |
| mcp-hetzner-go | [MahdadGhasemian/mcp-hetzner-go](https://github.com/MahdadGhasemian/mcp-hetzner-go) | Community. Not reviewed by this project. |

Being listed in awesome-hcloud is not an endorsement by Hetzner, and neither project is maintained by Hetzner. Nobody on this project has audited what they do with the token or which endpoints they call.

If a user decides to add one anyway:

1. Put it in the project's own `.mcp.json`, never in the shared module, with a comment naming who added it and why.
2. Pin an exact version or commit.
3. **Only ever give it the Read token.** Reference it as `${HCLOUD_TOKEN}` in the server's `env`; never `HCLOUD_TOKEN_RW`. A Read token cannot create, change or delete anything ([Generating an API token](https://docs.hetzner.com/cloud/api/getting-started/generating-api-token/)), which is the only guarantee you have about an unreviewed server.
4. Start the agent as `secret-run --only HCLOUD_TOKEN -- claude` so the token exists only in that process tree.
5. Read the server's source for the token path before the first run; if it writes the token anywhere, or can be pointed at a different API endpoint from the model side, do not use it.

There is no write opt-in for Hetzner MCP. Mutations go through Terraform with `HCLOUD_TOKEN_RW` mapped inside `secret-run`, as in [terraform.md](terraform.md).

## What agents use instead: the hcloud CLI

For inspection, Claude runs the official CLI with the Read token and JSON output:

```bash
secret-run --only HCLOUD_TOKEN -- hcloud server list -o json
secret-run --only HCLOUD_TOKEN -- hcloud network describe <name> -o json
secret-run --only HCLOUD_TOKEN -- hcloud firewall list -o json
secret-run --only HCLOUD_TOKEN -- hcloud load-balancer describe <name> -o json
secret-run --only HCLOUD_TOKEN -- hcloud all list -o json
secret-run --only HCLOUD_TOKEN -- hcloud api /v1/actions?status=error
```

`hcloud` reads `HCLOUD_TOKEN` from the environment and needs no config file ([CLI configuration](https://github.com/hetznercloud/cli/blob/main/docs/reference/configuration.md)); `-o json` is documented in [using output options](https://github.com/hetznercloud/cli/blob/main/docs/guides/using-output-options.md). The full command set is in [cli-cheatsheet.md](cli-cheatsheet.md). This covers everything a read-only MCP server would offer, with the token scope enforced by Hetzner's API rather than by a third-party process.

For documentation lookups there is also no Hetzner docs MCP server; use the `terraform` MCP server for provider schema questions and fetch [docs.hetzner.com](https://docs.hetzner.com/) pages directly.

## Revisit

Check the [hetznercloud organisation](https://github.com/hetznercloud) and [awesome-hcloud](https://github.com/hetznercloud/awesome-hcloud) when this skill is next reviewed. If Hetzner publishes an official MCP server, add it to `modules/hetzner/mcp.json` pinned, with `${HCLOUD_TOKEN}` (Read) only, and update this page.
