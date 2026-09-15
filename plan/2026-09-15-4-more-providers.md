---
status: draft
issue: 4
spec: spec/2026-09-15-4-more-providers.md
---

# Plan: Add Cloudflare, Hetzner and DigitalOcean providers

This plan can be implemented without opening the intent or spec. Every approved decision is copied below.

## Approved decisions

**D1. Scope.** Add providers `cloudflare`, `hetzner` and `digitalocean`, following `AGENTS.md` ("Adding a provider").
- **Unchanged:** `modules/common`, existing providers, the init script's composition logic, and the flake checks.
- **Changed shared files:** `flake.nix` (`providers`), `.github/workflows/ci.yml` (matrix), `README.md`, root `AGENTS.md` if it lists providers, and `pkgs/init.sh` (warnings only).

**D2. Files per provider:** `modules/<p>/{devenv.nix,agents.md}`, `modules/<p>/mcp.json` (not for Hetzner), `skills/<p>/SKILL.md`, `skills/<p>/references/{architecture,security,cli-cheatsheet,terraform,mcp}.md`, and the generated `templates/<p>/`.

**D3. Packages** (nixos-unstable, free, cached):

| Module | Packages | `enterTest` |
|---|---|---|
| cloudflare | `wrangler cloudflared flarectl` | `wrangler --version`, `cloudflared --version`, `flarectl --version` |
| hetzner | `hcloud` | `hcloud version` |
| digitalocean | `doctl` | `doctl version` |

Not added: `cloudflare-cli` (third party) and `packer` (unfree).

**D4. Tokens.** Agents and MCP only ever use read-only secrets. Write tokens are separate.

| Provider | Agent / MCP (read-only) | Deploy (write) | Read-only token recipe |
|---|---|---|---|
| Cloudflare | `CLOUDFLARE_READ_TOKEN` | `CLOUDFLARE_API_TOKEN` (Terraform, wrangler) | "Read all resources" template + `Account Resources: Read` |
| Hetzner | `HCLOUD_TOKEN` (Read project token) | `HCLOUD_TOKEN_RW` (Read & Write) | Project token, Read permission |
| DigitalOcean | `DIGITALOCEAN_READ_TOKEN` | `DIGITALOCEAN_ACCESS_TOKEN` (doctl, Terraform) | PAT with Read Only scope (`api:read`), with expiry |

*Correction 1:* the spec's table lists `HCLOUD_TOKEN` as the deploy token, but its paragraph makes it the Read token and uses `HCLOUD_TOKEN_RW` for writes. This plan follows the paragraph, which is the read-only-for-agents design.

*Correction 2:* the spec's example `secret-run --only HCLOUD_TOKEN_RW -- env HCLOUD_TOKEN="$HCLOUD_TOKEN_RW" terraform apply` doesn't work, because the outer shell expands `$HCLOUD_TOKEN_RW` before `secret-run` decrypts it, so the value is empty. Skills and docs must map the variable inside the command:
- `secret-run --only HCLOUD_TOKEN_RW -- bash -c 'HCLOUD_TOKEN=$HCLOUD_TOKEN_RW terraform apply'`
- flarectl the same way: `bash -c 'CF_API_TOKEN=$CLOUDFLARE_READ_TOKEN flarectl …'`

**D5. MCP servers:**

`modules/cloudflare/mcp.json`:
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

`modules/digitalocean/mcp.json`:
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

**Hetzner:** no `mcp.json`. The skill's `mcp.md` explains that there's no official server, names the community servers with a warning never to use them with write tokens, and recommends `hcloud` with the Read token.

**Why:**
- **No read-only flags exist**, so the token scope is the boundary.
- **The `mcp-remote` stdio bridge avoids Claude Code blanking credential-like variables in remote headers.**
- **OAuth is documented as an alternative only**, because its scopes can't be pinned in the repo.

**Write opt-in** is documented in each skill's `mcp.md`: put a write token in the project's own `.mcp.json`, with a warning.

**D6. Init warnings.** Add two branches to the existing `case $p in` block in `pkgs/init.sh`:
- `cloudflare) echo "WARNING: the Cloudflare API MCP server has no read-only mode; store a 'Read all resources' token as CLOUDFLARE_READ_TOKEN." >&2 ;;`
- `digitalocean) echo "WARNING: the DigitalOcean MCP server has no read-only mode; store a Read Only token as DIGITALOCEAN_READ_TOKEN." >&2 ;;`

**D7. Skills.** Frontmatter has only `name` (equal to the directory name) and `description`. `SKILL.md` stays at or under 500 lines, and each reference at or under 300. Every claim links official docs.

| Skill | `architecture.md` | `security.md` | `terraform.md` |
|---|---|---|---|
| cloudflare | developers.cloudflare.com/reference-architecture: zones and DNS, WAF, Workers, R2, Tunnels, Zero Trust | token templates, least privilege, account vs user tokens, never Global API Key | `cloudflare/cloudflare ~> 5.0` (v5 only, no v4 examples); R2 state via the S3 backend (`endpoints.s3`, `region="auto"`, `use_path_style`, `skip_credentials_validation`, `skip_metadata_api_check`, `skip_region_validation`, `skip_requesting_account_id`, `skip_s3_checksum`) |
| hetzner | projects, networks, firewalls, placement groups, load balancers, Kubernetes on Hetzner | Read vs Read & Write project tokens, SSH keys, firewalls by default | `hetznercloud/hcloud ~> 1.69`; Hetzner Object Storage S3 backend, marked semi-verified |
| digitalocean | Droplets, VPC, cloud firewalls, load balancers, DOKS, App Platform, managed DBs, Spaces | PAT scopes (Full / Read Only / Custom), mandatory expiry, teams | `digitalocean/digitalocean ~> 2.100`; Spaces S3 backend with `use_lockfile = true` |

`cli-cheatsheet.md` covers wrangler/cloudflared/flarectl, hcloud or doctl, and uses `secret-run --only … -- bash -c '…'` whenever a variable name has to be mapped.

**D8. CI.** Matrix `providers` adds `cloudflare`, `hetzner`, `digitalocean` and `"aws cloudflare"`. macOS stays informative.

## Steps

Each step is one commit `feat(<area>): … (#4)` on `feat/4-more-providers`. An `ACT` cites the step number.

0. **Check `mcp-remote` (spec risk 1) and `@digitalocean/mcp`.**
   - In a devenv shell with `PYTHONPATH` unset, send the MCP `initialize` request through `npx -y mcp-remote@0.14.2 https://mcp.cloudflare.com/mcp --header "Authorization:Bearer invalid"`.
     → verify: the bridge starts and passes the request on. An auth error from Cloudflare counts as a pass: it proves the header reached the server.
   - Send `initialize` to `npx -y @digitalocean/mcp@1.0.70 --services accounts` with `DIGITALOCEAN_API_TOKEN=invalid`.
     → verify: a JSON-RPC `result` comes back.
   - If `mcp-remote` can't pass the header, revise D5 to use the Cloudflare OAuth `type: http` server, and update this plan in the same commit.
1. **Cloudflare.** Add `modules/cloudflare/{devenv.nix,mcp.json,agents.md}` and the D6 warning.
   → verify:
   - `nix run . -- cloudflare --into $tmp`, then `devenv --override-input cloud "path:$(readlink -f .)" test` in `$tmp`, passes.
   - `jq` finds that every `${…}` in `.mcp.json` for `cloudflare-*` is `CLOUDFLARE_READ_TOKEN` or `CF_MCP_AUTH`.
2. **`skills/cloudflare/`** (D7). → verify: the `nix flake check` skills check passes, and `grep -rn '~> 4' skills/cloudflare` finds nothing.
3. **Hetzner.** Add `modules/hetzner/{devenv.nix,agents.md}` (no `mcp.json`) and `skills/hetzner/` (D7).
   → verify: `devenv test` passes, `test ! -e modules/hetzner/mcp.json`, and the generated project's `.mcp.json` only has `terraform`.
4. **DigitalOcean.** Add `modules/digitalocean/{devenv.nix,mcp.json,agents.md}`, the D6 warning, and `skills/digitalocean/` (D7).
   → verify: `devenv test` passes, and `jq -r '.mcpServers.digitalocean.env.DIGITALOCEAN_API_TOKEN'` equals `${DIGITALOCEAN_READ_TOKEN}`.
5. **Flake, templates and docs.**
   - Add the three providers to `providers` in `flake.nix`.
   - Generate them with `for p in cloudflare hetzner digitalocean; do nix run . -- $p --into templates/$p; done`.
   - Update `README.md`: the "What you get" table, the MCP restriction table (Cloudflare and DigitalOcean rows say "token scope: *_READ_TOKEN"; Hetzner says "none"), and a Providers line.
   → verify: `nix flake check` passes (`templates-fresh` and `skills`), and `nix flake init -t path:$(readlink -f .)#hetzner` in a temp git repo, followed by `devenv test`, passes.
6. **CI matrix** (D8). → verify: `actionlint` passes, and `nix run . -- aws cloudflare --into $tmp` produces `.mcp.json` keys `aws aws-docs cloudflare-api cloudflare-docs terraform` and passes `devenv test`.
7. **PR and close-out.**
   - Open a PR that links the intent, spec and plan.
   - CI must be green on Linux.
   - After merge, #4 closes via "Closes #4".
   → verify: the PR's required checks pass.

## Tests

```bash
R=$(readlink -f .)
nix flake check                                                    # templates-fresh + skills (10 skills)
for p in cloudflare hetzner digitalocean; do
  d=$(mktemp -d); nix run . -- $p --into "$d" && (cd "$d" && git add -A && devenv --override-input cloud "path:$R" test)
done
d=$(mktemp -d); nix run . -- aws cloudflare --into "$d"
jq -e '.mcpServers|keys == ["aws","aws-docs","cloudflare-api","cloudflare-docs","terraform"]' "$d/.mcp.json"
grep -ohE '\$\{[A-Z_]+' modules/cloudflare/mcp.json modules/digitalocean/mcp.json | sort -u   # only CF_MCP_AUTH, CLOUDFLARE_READ_TOKEN, DIGITALOCEAN_READ_TOKEN
test ! -e modules/hetzner/mcp.json
nix run nixpkgs#actionlint -- .github/workflows/ci.yml
```

Manual check, one-off, needs real read-only tokens:
1. Run `secret-run --only CLOUDFLARE_READ_TOKEN -- claude` in a generated Cloudflare project.
2. `/mcp` should show `cloudflare-api` connected.
3. A read, such as listing zones, works; a write is refused by the API.
4. Repeat with `DIGITALOCEAN_READ_TOKEN`.

## Rollback

- **Before merge:** revert or drop commits on the branch.
- **After merge:** `git revert` the squash commit. Existing projects are unaffected until `devenv update`, and projects that imported `cloud/modules/<new provider>` should drop that line from `devenv.yaml`.
- **Tokens aren't touched by a rollback.** Revoke any tokens created for testing at the provider.
