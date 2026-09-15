# Cloudflare security

Identity, tokens, transport security and audit. Everything here applies before the first `terraform apply`.

## Tokens, not keys

| Credential | Scope | Restrictable | Use |
|---|---|---|---|
| API token | Chosen permissions on chosen accounts/zones | IP filter, TTL, permission set | Everything ([create token](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/)) |
| Global API Key | Every permission of the user | No | Never. "Not recommended for new customers" ([API keys](https://developers.cloudflare.com/fundamentals/api/get-started/keys/)) |
| Origin CA key | Origin certificate issuance only | No | Only if you issue origin certs by API ([CA keys](https://developers.cloudflare.com/fundamentals/api/get-started/ca-keys/)) |

Terraform, wrangler and flarectl all accept the legacy `CLOUDFLARE_API_KEY` + `CLOUDFLARE_EMAIL` pair. Reject it in review; the provider docs mark `api_key` as the outdated method ([provider docs](https://github.com/cloudflare/terraform-provider-cloudflare/blob/main/docs/index.md)).

## The two tokens this project uses

| Env var | Who uses it | How it is created | Where it lives |
|---|---|---|---|
| `CLOUDFLARE_READ_TOKEN` | Agents, MCP servers, flarectl reads | Template **Read all resources** (all read permissions on account, zone and user resources) plus `Account Resources: Read` so account-scoped listings work ([templates](https://developers.cloudflare.com/fundamentals/api/reference/template/)) | agenix, `secret-add CLOUDFLARE_READ_TOKEN` |
| `CLOUDFLARE_API_TOKEN` | Terraform provider, wrangler, CI | Custom token: only the permissions the project's resources need, on only the target account/zones | agenix, `secret-add CLOUDFLARE_API_TOKEN` |

Rules:

- The agent never receives `CLOUDFLARE_API_TOKEN`. `secret-run --only CLOUDFLARE_READ_TOKEN -- claude` is the only way to start an agent session.
- The deploy token lists its permissions in the PR that first uses it, so a reviewer can compare them with the resources in the plan.
- "Edit" in a token means create, read, update, delete and list. Pick "Read" wherever the resource is only referenced (for example `Zone: Zone: Read` for a `data "cloudflare_zone"` lookup) ([permissions reference](https://developers.cloudflare.com/fundamentals/api/reference/permissions/)).

### Typical deploy-token permission sets

| Project | Permissions |
|---|---|
| DNS + zone settings | `Zone: Zone: Read`, `Zone: DNS: Edit`, `Zone: Zone Settings: Edit`, `Zone: SSL and Certificates: Edit` |
| WAF and rate limiting | add `Zone: Zone WAF: Edit` |
| Workers + KV/R2/D1 | `Account: Workers Scripts: Edit`, `Account: Workers KV Storage: Edit`, `Account: Workers R2 Storage: Edit`, `Account: D1: Edit`, `Zone: Workers Routes: Edit` |
| Tunnel + Access | `Account: Cloudflare Tunnel: Edit`, `Account: Access: Apps and Policies: Edit`, `Zone: DNS: Edit` for the tunnel CNAME |

Exact names come from the [permissions reference](https://developers.cloudflare.com/fundamentals/api/reference/permissions/) or the List permission groups API; verify before creating the token, do not guess.

## Account-owned vs user tokens

- **User tokens** live under *My Profile > API Tokens* and act as that person. They die when the person is removed from the account.
- **Account-owned tokens** live under *Manage Account > Account API Tokens* and are service principals with their own permissions; Cloudflare recommends them for "durable integrations" such as CI/CD. Creating them needs Super Administrator ([account-owned tokens](https://developers.cloudflare.com/fundamentals/api/get-started/account-owned-tokens/)).
- Some products do not yet accept account tokens (Page Rules, Registrar, Turnstile and others are listed on that page). If Terraform returns an authentication error on such a resource, that is the first thing to check.

Default: account-owned for `CLOUDFLARE_API_TOKEN` and for any MCP token; user token only where a product forces it.

## Restrict every token

Set both when creating a token ([restrict tokens](https://developers.cloudflare.com/fundamentals/api/how-to/restrict-tokens/)):

- **Client IP filtering** — CIDR "Is in" rules for the CI runner egress and the office/VPN range. A leaked token is useless from anywhere else.
- **TTL** — `notBefore` / `notAfter`. Tokens without a TTL never expire. Put a calendar reminder on the expiry; rotate with `secret-add` and a new dashboard token.

Verify a token before storing it:

```bash
curl -s -H "Authorization: Bearer <paste>" https://api.cloudflare.com/client/v4/user/tokens/verify
```

The secret is shown once at creation. Paste it straight into `secret-add`; never into a file, a chat or a shell history line.

The same restrictions can be expressed in Terraform for tokens the platform team issues to other systems (`cloudflare_api_token` with `condition.request_ip` and `expires_on`, see [terraform.md](terraform.md)), but the two tokens this project itself runs on are created by hand so their secrets never enter state.

## Account hardening

From [account security](https://developers.cloudflare.com/fundamentals/account/account-security/):

- Two-factor authentication for every member; SSO for organisations.
- Least-privilege member roles; no extra Super Administrators.
- **Zone holds** on production zones so nobody can move the domain to another account.
- Review **active sessions** and **leaked password notifications**.

## Audit logs

Audit Logs record account-level actions and zone configuration changes for 18 months, viewable in the dashboard or by API; Enterprise can Logpush them ([Audit Logs v2](https://developers.cloudflare.com/fundamentals/account/account-security/audit-logs/), [v1](https://developers.cloudflare.com/fundamentals/account/account-security/review-audit-logs/)). Check them:

- after every `terraform apply` in production (the token name shows as the actor, which is why each token has a descriptive name),
- after any MCP session run with a write token,
- when a token is suspected leaked, filtering by the token's actor before revoking it.

## Transport security

| Setting | Value | Why |
|---|---|---|
| SSL/TLS encryption mode | **Full (strict)** | Cloudflare validates the origin certificate; Flexible and Full accept downgrades or self-signed certs ([SSL modes](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/), [Full (strict)](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/)) |
| Minimum TLS version | `1.2` | Rejects TLS 1.0/1.1 clients ([minimum TLS](https://developers.cloudflare.com/ssl/edge-certificates/additional-options/minimum-tls/)) |
| Always Use HTTPS | on | Redirects HTTP at the edge |
| Authenticated Origin Pulls | on for origins reachable outside a tunnel | Origin accepts TLS only from Cloudflare ([AOP](https://developers.cloudflare.com/ssl/origin-configuration/authenticated-origin-pull/)) |
| HSTS | max-age 6 months, include subdomains, **no preload on first rollout** | See below ([HSTS](https://developers.cloudflare.com/ssl/edge-certificates/additional-options/http-strict-transport-security/)) |

### HSTS caveat

Once HSTS is served, browsers refuse plain HTTP for the whole `max-age`. Cloudflare's own warning: if you remove HTTPS before disabling HSTS or before the original max-age elapses, "your website becomes inaccessible". Things that count as removing HTTPS: switching a record from proxied to DNS-only, pausing Cloudflare, changing nameservers, redirecting HTTPS to HTTP. Preload requires a 12-month max-age and a browser-list submission that cannot be quickly undone. So: enable HSTS only on zones that are proxied for good, start with a short max-age, and treat preload as a separate, later decision.

## Secrets at runtime

- Worker secrets: `wrangler secret put NAME`; values are write-only afterwards ([secrets](https://developers.cloudflare.com/workers/configuration/secrets/)). Local values in `.dev.vars`, git-ignored.
- Tunnel credentials: the connector token for remotely-managed tunnels, or the `tunnel_secret`, is a secret. Store it with `secret-add`, pass it to `cloudflared` via `secret-run`, and never put it in Terraform variables committed to the repo.
- R2 API tokens (S3 access key/secret) for the state backend: `Object Read & Write` on the state bucket only ([R2 tokens](https://developers.cloudflare.com/r2/api/tokens/)).

Generic handling: [secrets skill](../../secrets/SKILL.md).
