# Cloudflare architecture

How the pieces fit, and the defaults this project uses. Start from Cloudflare's [reference architectures](https://developers.cloudflare.com/reference-architecture/) for anything larger than one zone.

## Reference architectures to read first

| Need | Document |
|---|---|
| Edge security for web apps | [Cloudflare Security Architecture](https://developers.cloudflare.com/reference-architecture/architectures/security/) |
| Many zones, one WAF policy | [Streamlined WAF deployment across zones](https://developers.cloudflare.com/reference-architecture/design-guides/streamlined-waf-deployment-across-zones-and-applications/) |
| Replace VPN / private app access | [Evolving to SASE](https://developers.cloudflare.com/reference-architecture/architectures/sase/), [Designing ZTNA access policies](https://developers.cloudflare.com/reference-architecture/design-guides/designing-ztna-access-policies/), [Zero Trust for startups](https://developers.cloudflare.com/reference-architecture/design-guides/zero-trust-for-startups/) |
| Serverless API / full-stack app | [Serverless global APIs](https://developers.cloudflare.com/reference-architecture/diagrams/serverless/serverless-global-apis/), [Fullstack applications](https://developers.cloudflare.com/reference-architecture/diagrams/serverless/fullstack-application/) |
| Object storage across clouds | [Egress-free storage in multi-cloud](https://developers.cloudflare.com/reference-architecture/diagrams/storage/egress-free-storage-multi-cloud/), [Storing user generated content](https://developers.cloudflare.com/reference-architecture/diagrams/storage/storing-user-generated-content/) |
| Strong consistency at the edge | [Durable Objects control/data plane](https://developers.cloudflare.com/reference-architecture/diagrams/storage/durable-object-control-data-plane-pattern/) |
| Data protection | [Securing data in transit](https://developers.cloudflare.com/reference-architecture/diagrams/security/securing-data-in-transit/), [at rest](https://developers.cloudflare.com/reference-architecture/diagrams/security/securing-data-at-rest/) |

## Accounts and zones

- **One Cloudflare account per environment** with its own domain (`example.com` prod, `example-staging.com` staging). Account-level resources (Workers, R2, Access, tunnels, rulesets at account scope) are shared inside an account, so a staging change can hit prod otherwise ([Terraform best practices](https://developers.cloudflare.com/terraform/advanced-topics/best-practices/)).
- A **zone** is one domain. `type = "full"` means Cloudflare is authoritative DNS (nameservers changed at the registrar); `partial` (CNAME setup) and `secondary` exist for special cases ([create a partial zone](https://developers.cloudflare.com/terraform/how-to/create-partial-zone/)). Default: full.
- Zone IDs are stable; names can be re-registered. Reference zones by ID from `data "cloudflare_zone"`.

## DNS

- **Proxied records** (orange cloud) route A/AAAA/CNAME traffic through Cloudflare and answer with anycast IPs, hiding the origin. Only A, AAAA and CNAME can be proxied; MX, TXT and the rest are always DNS-only ([proxy status](https://developers.cloudflare.com/dns/proxy-status/)). Default for every web origin: proxied. A DNS-only record on a web origin exposes its IP to anyone who queries.
- **DNSSEC**: enable on the zone, then add the DS record at the registrar (Cloudflare Registrar does it for you). Algorithm 13 (ECDSA P-256/SHA-256) ([DNSSEC](https://developers.cloudflare.com/dns/dnssec/)).
- **Hygiene records**: CAA restricting issuers, SPF, DKIM and DMARC even for domains that never send mail (a `v=spf1 -all` and a reject DMARC stop spoofing) ([record types](https://developers.cloudflare.com/dns/manage-dns-records/reference/dns-record-types/)).
- TTL `1` (automatic) on proxied records; explicit TTLs only on DNS-only records where you plan cutovers.

## Edge security

Layers, in request order:

1. **DDoS**: always on, managed by Cloudflare; only tune the DDoS managed ruleset if you have a reason ([DDoS managed rulesets in Terraform](https://developers.cloudflare.com/terraform/additional-configurations/ddos-managed-rulesets/)).
2. **WAF managed rules**: execute the Cloudflare Managed Ruleset and the OWASP Core Ruleset in the `http_request_firewall_managed` phase. Free plans get the Free Managed Ruleset automatically; Pro and up get the full sets ([managed rules](https://developers.cloudflare.com/waf/managed-rules/), [Terraform example](https://developers.cloudflare.com/terraform/additional-configurations/waf-managed-rulesets/)). Deploy managed rules as `log` first on a busy zone, read the events, then switch to block.
3. **Custom rules**: block, challenge or skip on your own expressions; 5 rules on Free, 20 on Pro, more above ([custom rules](https://developers.cloudflare.com/waf/custom-rules/)). Keep an allow-list rule for known scanners and health checkers above the blocks.
4. **Rate limiting**: characteristics (IP on Free/Pro; ASN, country, JA3/JA4, custom on Enterprise), period and a mitigation timeout; put one on login, signup, password reset and expensive API paths ([rate limiting rules](https://developers.cloudflare.com/waf/rate-limiting-rules/), [Terraform example](https://developers.cloudflare.com/terraform/additional-configurations/rate-limiting-rules/)).
5. **TLS to origin**: Full (strict) plus Authenticated Origin Pulls or, better, a tunnel so there is no reachable origin at all ([SSL modes](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/)).

Rulesets are evaluated per phase; give every rule a `ref` so reorders do not change its ID.

## Compute: Workers and Pages

- **Workers** is the platform: serverless functions at every PoP, deployed with `wrangler deploy` ([Workers](https://developers.cloudflare.com/workers/)). Static sites and SPAs use Workers **static assets** ([static assets](https://developers.cloudflare.com/workers/static-assets/)).
- **Pages** still works for existing projects, but Cloudflare's own guidance is "Start new projects with Workers" because Workers covers the Pages use cases with a broader feature set ([Pages](https://developers.cloudflare.com/pages/)). Do not create new Pages projects.
- Split of responsibility: Terraform creates the account resources a Worker binds to (KV namespaces, R2 buckets, D1 databases, routes, custom domains); `wrangler` bundles and uploads the code and manages versions and rollbacks ([Workers IaC](https://developers.cloudflare.com/workers/platform/infrastructure-as-code/)).
- Secrets are bindings set by `wrangler secret put`, write-only afterwards ([secrets](https://developers.cloudflare.com/workers/configuration/secrets/)).
- Patterns with diagrams: [A/B testing](https://developers.cloudflare.com/reference-architecture/diagrams/serverless/a-b-testing-using-workers/), [serverless ETL](https://developers.cloudflare.com/reference-architecture/diagrams/serverless/serverless-etl/), [image content management](https://developers.cloudflare.com/reference-architecture/diagrams/serverless/serverless-image-content-management/).

## Storage: R2, D1, KV

| Store | Model | Consistency | Use for | Not for |
|---|---|---|---|---|
| **R2** ([docs](https://developers.cloudflare.com/r2/)) | S3-compatible object storage, no egress fees | Strong per object | Assets, uploads, backups, Terraform state, multi-cloud data | Many small hot reads (use KV) |
| **D1** ([docs](https://developers.cloudflare.com/d1/)) | Serverless SQLite; read replicas available | Strong on primary | Relational app data, per-tenant DBs | Very large single databases; check [limits](https://developers.cloudflare.com/d1/) |
| **KV** ([docs](https://developers.cloudflare.com/kv/)) | Global key-value, cached at the edge | **Eventual**, up to 60 s or more between locations, negative lookups cached too ([how KV works](https://developers.cloudflare.com/kv/concepts/how-kv-works/)) | Config, feature flags, sessions that tolerate staleness, read-heavy lookups | Counters, locks, anything transactional (use Durable Objects) |

R2 specifics: pick `location` at creation (it is best effort and immutable), use lifecycle rules for expiry, enable event notifications when a Worker should react to uploads ([event notifications](https://developers.cloudflare.com/reference-architecture/diagrams/storage/event-notifications-for-storage/)). R2 API tokens are separate from Cloudflare API tokens and yield S3 keys ([R2 tokens](https://developers.cloudflare.com/r2/api/tokens/)).

## Origin connectivity: Cloudflare Tunnel

`cloudflared` runs next to the origin and opens **outbound-only** connections to Cloudflare; nothing listens on a public IP, so the firewall keeps all inbound ports closed ([Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/)).

- **Remotely managed tunnels** (created in the dashboard, API or Terraform with `config_src = "cloudflare"`) keep the ingress rules in Cloudflare; the host only needs the connector token ([create a remote tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/)). Default.
- **Locally managed tunnels** keep `config.yml` on the host; use when the host must control routing offline ([create a local tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/create-local-tunnel/)).
- Each replica opens four connections to two or more data centres; run at least two replicas per tunnel, and separate tunnels with a load balancer when you need steering ([tunnel availability](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-availability/)).
- A tunnel publishes a hostname (CNAME to `<UUID>.cfargotunnel.com`) or a private CIDR for WARP clients. Public hostnames go through the zone's WAF like any proxied record.
- Non-HTTP: SSH, RDP and arbitrary TCP work through the same tunnel and can be gated by Access ([clientless access](https://developers.cloudflare.com/learning-paths/clientless-access/concepts/)).

## Zero Trust: Access

Cloudflare One is the SASE platform; **Access** is the part that authenticates every request to an application before it reaches the origin ([Cloudflare One](https://developers.cloudflare.com/cloudflare-one/), [self-hosted app](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/)).

- An **application** is a hostname (plus optional path) with a type (`self_hosted`, `saas`, `ssh`, `rdp`, …). **Policies** attach to it with a precedence.
- Policy actions ([Access policies](https://developers.cloudflare.com/cloudflare-one/policies/access/)): `allow` (with include / require / exclude rules), `block`, `bypass` (no auth, no logging: only for public health endpoints, always with a comment), `service_auth` (service tokens or mTLS for machines, no IdP login).
- Evaluation order: Service Auth and Bypass first, then Block and Allow, top to bottom; the first Allow or Block match wins.
- Selectors: identity (email, IdP group, login method), network (IP, country), device (posture, WARP), external evaluation.
- Pattern for an internal tool: tunnel to the origin, Access application on the hostname, `allow` for the IdP group, `service_auth` policy for CI, no `bypass`. Guide: [designing ZTNA access policies](https://developers.cloudflare.com/reference-architecture/design-guides/designing-ztna-access-policies/).
- Machine-to-machine through Access uses service tokens; wrangler and cloudflared accept `CLOUDFLARE_ACCESS_CLIENT_ID`/`_SECRET` ([wrangler env vars](https://developers.cloudflare.com/workers/wrangler/system-environment-variables/)).

## Putting it together: default web app

```
visitor ──HTTPS──▶ Cloudflare edge (DNSSEC zone, proxied record)
                     ├─ DDoS, WAF managed + custom rules, rate limits
                     ├─ Access (for /admin and internal hosts)
                     ├─ Worker (API, static assets)  ──▶ KV / D1 / R2
                     └─ Tunnel ──outbound only──▶ cloudflared x2 ──▶ origin :8080
```

Everything above the tunnel is Terraform (`cloudflare/cloudflare ~> 5.0`); the Worker bundle is `wrangler deploy`; the host runs `cloudflared` as a service with a token from agenix. State lives in R2. Details: [terraform.md](terraform.md), [security.md](security.md), [cli-cheatsheet.md](cli-cheatsheet.md).
