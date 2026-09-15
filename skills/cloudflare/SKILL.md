---
name: cloudflare
description: Cloudflare best practices and architecture for writing, reviewing and deploying DNS, edge security and serverless resources with Terraform (cloudflare/cloudflare provider v5), wrangler, cloudflared, flarectl and read-only MCP servers. Use when a task touches Cloudflare zones, DNS records, DNSSEC, proxied records, WAF managed rules, rate limiting, SSL/TLS modes, Workers, Pages, R2, D1, KV, Cloudflare Tunnels (cloudflared), Zero Trust Access, API tokens, wrangler deploys, R2 remote state, cf-terraforming imports, or the cloudflare-docs / cloudflare-api MCP servers. Covers least-privilege API tokens (never the Global API Key), account vs user tokens, reference architectures, Terraform v5 syntax only (cloudflare_dns_record, cloudflare_ruleset, cloudflare_zero_trust_*), S3-compatible R2 backend, CLI cheatsheet and MCP configuration.
---

# Cloudflare

Rules for every Cloudflare task in this project. Read the linked reference before touching the matching area.

## Non-negotiables

1. **API tokens only, never the Global API Key.** The key has every permission of the user and cannot be restricted; Cloudflare says it is "not recommended for new customers" ([API keys](https://developers.cloudflare.com/fundamentals/api/get-started/keys/), [create a token](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/)). See [references/security.md](references/security.md).
2. **Two tokens, two jobs.** Agents and MCP use `CLOUDFLARE_READ_TOKEN` (the "Read all resources" template plus `Account Resources: Read`). Deploys use `CLOUDFLARE_API_TOKEN` (Terraform provider and wrangler read it natively) scoped to the specific zones, accounts and permissions the project needs ([templates](https://developers.cloudflare.com/fundamentals/api/reference/template/), [permissions](https://developers.cloudflare.com/fundamentals/api/reference/permissions/)). Never point an agent at the write token.
3. **Prefer account-owned tokens** for anything durable (CI, Terraform, MCP). They are service principals, not tied to a person who may leave ([account-owned tokens](https://developers.cloudflare.com/fundamentals/api/get-started/account-owned-tokens/)). Add IP filters and a TTL ([restrict tokens](https://developers.cloudflare.com/fundamentals/api/how-to/restrict-tokens/)).
4. **Secrets stay in agenix.** Store with `secret-add NAME`, use with `secret-run --only NAME -- <cmd>`. Never print, echo or write a token to disk. Worker runtime secrets go in `wrangler secret put`, never in `wrangler.toml` or code ([Worker secrets](https://developers.cloudflare.com/workers/configuration/secrets/)). See [secrets skill](../secrets/SKILL.md).
5. **Shell gotcha when a tool wants a different variable name.** Map inside the command: `secret-run --only CLOUDFLARE_READ_TOKEN -- bash -c 'CF_API_TOKEN=$CLOUDFLARE_READ_TOKEN flarectl zone list'`. Never `-- env X="$Y" cmd`: the outer shell expands `$Y` before `secret-run` decrypts it, so the value is empty.
6. **Terraform provider `cloudflare/cloudflare ~> 5.0`, v5 syntax only.** v5 is a breaking rewrite: `cloudflare_dns_record` (not `cloudflare_record`), `cloudflare_zero_trust_*`, nested objects instead of blocks ([v5 upgrade guide](https://github.com/cloudflare/terraform-provider-cloudflare/blob/main/docs/guides/version-5-upgrade.md)). Never write v4 examples. Conventions: [references/terraform.md](references/terraform.md); generic practice: [terraform skill](../terraform/SKILL.md).
7. **Remote state in R2** through the S3 backend with `region = "auto"` and the R2 `skip_*` flags, credentials from an R2 API token passed as `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` via agenix ([R2 remote backend](https://developers.cloudflare.com/terraform/advanced-topics/remote-backend/)). Never hard-code `access_key`/`secret_key` in the backend block.
8. **SSL/TLS Full (strict), proxied records, DNSSEC on.** Origin cert validated ([SSL modes](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/)), origin IP hidden ([proxy status](https://developers.cloudflare.com/dns/proxy-status/)), zone signed ([DNSSEC](https://developers.cloudflare.com/dns/dnssec/)).
9. **No inbound ports.** Expose origins through Cloudflare Tunnel (`cloudflared` makes outbound-only connections) and put Access in front of anything private ([Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/), [Access policies](https://developers.cloudflare.com/cloudflare-one/policies/access/)).
10. **MCP servers are read-only by token scope, not by a server flag.** The Cloudflare API server has no read-only mode; the token is the boundary. Write access is a deliberate per-project opt-in. If `mcp-remote` prints "Please authorize this client by visiting https://mcp.cloudflare.com/authorize…", the read token was rejected and it fell back to browser OAuth: do not approve it (OAuth scopes can be write-capable); rotate `CLOUDFLARE_READ_TOKEN` instead. See [references/mcp.md](references/mcp.md).

## Workflow

```bash
secret-run --only CLOUDFLARE_READ_TOKEN -- bash -c \
  'curl -s -H "Authorization: Bearer $CLOUDFLARE_READ_TOKEN" https://api.cloudflare.com/client/v4/user/tokens/verify'   # who am I
secret-run --only CLOUDFLARE_READ_TOKEN -- claude                                    # agent session, read-only
secret-run --only CLOUDFLARE_API_TOKEN,R2_ACCESS_KEY_ID,R2_SECRET_ACCESS_KEY -- bash -c \
  'AWS_ACCESS_KEY_ID=$R2_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY=$R2_SECRET_ACCESS_KEY terraform init'
terraform plan -out=plan.tfplan   # same wrapper as init; the provider reads CLOUDFLARE_API_TOKEN itself
tflint --recursive && trivy config .
terraform apply plan.tfplan
secret-run --only CLOUDFLARE_API_TOKEN -- wrangler deploy                            # Workers, after Terraform owns the bindings
```

Before `apply`: read the plan, confirm the account and zone IDs match the target, and check nothing is destroyed unintentionally (DNS records and rulesets recreate with downtime). Never apply from a dirty working tree.

## Review checklist

Run this on every PR that touches Cloudflare.

- [ ] `terraform fmt -check`, `terraform validate`, `tflint`, `trivy config .` pass with no HIGH/CRITICAL.
- [ ] Provider pinned `~> 5.0`; no v4 resource names (`cloudflare_record`, `cloudflare_access_*`, `cloudflare_tunnel`, `cloudflare_zone_settings_override`).
- [ ] Backend is S3-on-R2 with `region = "auto"`, `use_path_style`, all `skip_*` flags; no inline keys.
- [ ] No token, key or `tunnel_secret` in `.tf`, `.tfvars`, `wrangler.toml` or `.mcp.json`; `.dev.vars` is git-ignored.
- [ ] Every `cloudflare_dns_record` for a web origin is `proxied = true`; `cloudflare_zone_dnssec` present.
- [ ] `cloudflare_zone_setting` `ssl = "strict"`, `min_tls_version` at least `1.2`, `always_use_https = "on"` ([minimum TLS](https://developers.cloudflare.com/ssl/edge-certificates/additional-options/minimum-tls/)).
- [ ] Managed WAF ruleset executed in `http_request_firewall_managed`; rate limit on login/API paths ([managed rules](https://developers.cloudflare.com/waf/managed-rules/), [rate limiting](https://developers.cloudflare.com/waf/rate-limiting-rules/)).
- [ ] Private hostnames sit behind a tunnel plus an Access application with an explicit `allow` policy; no `bypass` without a comment saying why.
- [ ] HSTS only when the zone is permanently HTTPS; preload never on a first rollout ([HSTS](https://developers.cloudflare.com/ssl/edge-certificates/additional-options/http-strict-transport-security/)).
- [ ] Deploy token permissions listed in the PR; read token untouched.

## Architecture defaults

Use these unless the spec says otherwise, and say why when you deviate. Detail: [references/architecture.md](references/architecture.md).

| Area | Default | Why |
|---|---|---|
| Accounts | One account per environment (staging, prod), separate domains | Account-level resources leak across environments otherwise ([Terraform best practices](https://developers.cloudflare.com/terraform/advanced-topics/best-practices/)) |
| DNS | Full zone on Cloudflare, DNSSEC, A/AAAA/CNAME proxied, CAA + SPF/DKIM/DMARC set | Hides origin, blocks spoofing ([record types](https://developers.cloudflare.com/dns/manage-dns-records/reference/dns-record-types/)) |
| Edge security | Managed ruleset + OWASP, custom rules, rate limiting, Full (strict) | Layered defence ([Security architecture](https://developers.cloudflare.com/reference-architecture/architectures/security/)) |
| Compute | Workers with static assets; Pages only for existing projects | Cloudflare: "Start new projects with Workers" ([Pages](https://developers.cloudflare.com/pages/)) |
| Storage | R2 for objects, D1 for relational, KV for read-heavy config, Durable Objects when you need consistency | KV is eventually consistent ([how KV works](https://developers.cloudflare.com/kv/concepts/how-kv-works/)) |
| Origin access | Tunnel with at least two `cloudflared` replicas; Access in front | Four outbound connections per replica, no open ports ([tunnel availability](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-availability/)) |
| Audit | Audit Logs v2 reviewed; Logpush for Enterprise | 18-month retention, all account changes ([audit logs](https://developers.cloudflare.com/fundamentals/account/account-security/audit-logs/)) |

## Tools in this shell

| Tool | Use it for |
|---|---|
| `wrangler` | Workers, Pages, KV, R2, D1 deploys and inspection; reads `CLOUDFLARE_API_TOKEN` ([env vars](https://developers.cloudflare.com/workers/wrangler/system-environment-variables/)) |
| `cloudflared` | Create, route and run tunnels; `cloudflared tunnel login` for local management |
| `flarectl` | Quick zone/DNS reads; reads `CF_API_TOKEN`, so map it inside `bash -c` |
| `terraform`, `tflint`, `trivy` | IaC, lint, security scan |

Cheatsheet: [references/cli-cheatsheet.md](references/cli-cheatsheet.md).

## References

- [references/architecture.md](references/architecture.md) — reference architectures, zones and DNS, WAF, Workers/Pages, R2/D1/KV, Tunnels, Zero Trust Access
- [references/security.md](references/security.md) — token templates, least privilege, account vs user tokens, IP/TTL restrictions, audit logs, SSL/TLS, HSTS
- [references/cli-cheatsheet.md](references/cli-cheatsheet.md) — wrangler, cloudflared, flarectl, raw API with `secret-run`
- [references/terraform.md](references/terraform.md) — provider v5, R2 backend, resource patterns, imports, gotchas
- [references/mcp.md](references/mcp.md) — `cloudflare-docs` and `cloudflare-api` servers, auth, why mcp-remote, write opt-in
