---
status: draft
issue: 4
author: olafkfreund
---

# Intent: Add Cloudflare, Hetzner and DigitalOcean providers

## Problem

The templates cover AWS, Azure, GCP, OCI and Kubernetes. Many projects also run on, or sit in front of, three platforms these templates don't support yet:

- **Cloudflare:** DNS, WAF, Workers, R2, Tunnels and Zero Trust.
- **Hetzner Cloud:** low-cost compute and networking, often used for Kubernetes clusters and self-hosted services.
- **DigitalOcean:** Droplets, App Platform, DOKS and managed databases.

For these today, people install the CLIs by hand, write Terraform without provider-specific guidance, and give agents no MCP access or best-practice skills. Mixed stacks such as "AWS + Cloudflare DNS" or "Hetzner + Kubernetes" can't be composed with `nix run … -- <providers>`.

## Proposed outcome

`nix run github:olafkfreund/cloud-projects-templates -- cloudflare hetzner digitalocean`, alone or combined with the existing providers, and `nix flake init -t …#<provider>` produce the same kind of project as the existing providers:

- **Tools:** the provider CLI and helpers in the devenv shell (e.g. `wrangler` and `cloudflared`, `hcloud`, `doctl`), with an `enterTest` that checks their versions.
- **Skill:** `.claude/skills/<provider>/` with a `SKILL.md` and references for best practices, architecture, security and IAM/tokens, a CLI cheatsheet, Terraform, and MCP. Every claim links to the provider's official docs.
- **MCP:**
  - **Cloudflare and DigitalOcean:** official MCP servers in `.mcp.json`, least privilege or read-only by default, and never with embedded credentials.
  - **Hetzner:** has no official MCP server, so nothing is configured, and the skill says so.
- **Secrets:** API tokens stored as agenix-format secrets (`CLOUDFLARE_API_TOKEN`, `HCLOUD_TOKEN`, `DIGITALOCEAN_ACCESS_TOKEN`), used via `secret-run --only …`.
- **Templates:** a generated `templates/<provider>`, and CI running `devenv test` for each provider on Linux and macOS.

Issue #4 closes when all three providers pass CI and are documented in the README.

## Affected users and systems

- **Users** of this repo who deploy to Cloudflare, Hetzner or DigitalOcean, including those who combine them with AWS, Azure, GCP, OCI or Kubernetes.
- **Repo files:** `modules/`, `skills/`, `templates/`, `flake.nix` (provider list), the CI matrix, `README.md` and `AGENTS.md`.
- **Unchanged:** existing providers, generated projects and the init script's behaviour.

## Constraints

- **Follow the existing pattern** from `AGENTS.md` ("Adding a provider"). No changes to `pkgs/init.sh` unless a provider truly needs one.
- **Official sources only:**
  - Packages come from nixpkgs, and no unfree packages are added.
  - MCP servers are official vendor servers pinned to exact versions. Cloudflare's hosted servers are remote URLs, so the "exact version" is the documented endpoint.
- **Least privilege by default:**
  - These platforms authenticate with API tokens rather than CLI SSO, so the "read-only" boundary is the token's scope.
  - The skills must show how to create read-only or narrowly scoped tokens, and MCP config must use read-only modes wherever the server offers one.
- **No tokens outside agenix.** No tokens in files, `.mcp.json` or tfvars: tokens only come from agenix via environment variables.
- **Skill format:** the Agent Skills spec (name and description only in frontmatter, name equal to the directory name, `SKILL.md` at most 500 lines, each reference at most 300).
- **CI must stay green on Linux.** macOS stays informative.

## Open questions

1. **Cloudflare MCP:** Cloudflare offers several remote MCP servers (docs, bindings, observability, DNS analytics, and so on) that use OAuth, plus an API-token route. Which ones do we configure by default? Proposal: docs plus a read-only subset, confirmed during spec research.
2. **DigitalOcean MCP:** `@digitalocean/mcp` via `npx`, limited to a read-only or narrow service set if supported. OK?
3. **Hetzner:** no official MCP server. Skip MCP (proposed), or accept a community server?
4. **Scope:** do you want any more providers in this issue, such as Scaleway or Linode/Akamai, or keep it to these three?

## Decisions (approver, 2026-09-15: proposals accepted)

1. **Cloudflare MCP:** the docs server plus a read-only subset of Cloudflare's official servers. The exact servers are chosen in the spec after research.
2. **DigitalOcean MCP:** `@digitalocean/mcp` via `npx`, limited to read-only or narrow services where supported.
3. **Hetzner:** no MCP server, because there is no official one. The skill documents this.
4. **Scope:** Cloudflare, Hetzner and DigitalOcean only.
