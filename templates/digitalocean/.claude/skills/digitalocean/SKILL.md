---
name: digitalocean
description: DigitalOcean best practices and architecture for writing, reviewing and deploying infrastructure with Terraform, doctl and a read-only MCP server. Use when a task touches DigitalOcean projects, Droplets, VPC, cloud firewalls, load balancers, DOKS Kubernetes, App Platform, managed databases, Spaces object storage, container registry, personal access tokens (Full / Read Only / Custom scopes), remote state on Spaces, the Terraform digitalocean provider, or the digitalocean/digitalocean-docs MCP servers. Covers a VPC-per-environment layout, deny-by-default firewalls by tag, database trusted sources, DOKS vs App Platform vs Droplets, token scoping with expiry, doctl cheatsheet, Terraform conventions (digitalocean/digitalocean ~> 2.100, S3 backend on Spaces with use_lockfile, tflint/trivy) and MCP configuration.
---

# DigitalOcean

Rules for every DigitalOcean task in this project. Read the linked reference before touching the matching area.

## Non-negotiables

1. **Two tokens, never one.** Agents and MCP use `DIGITALOCEAN_READ_TOKEN`, a personal access token with the **Read Only** scope (`api:read`) and an expiry. Deploys use `DIGITALOCEAN_ACCESS_TOKEN` with **Custom Scopes** as narrow as the change needs, also with an expiry. Never give an agent a Full Access token ([token scopes](https://docs.digitalocean.com/reference/api/create-personal-access-token/)). See [references/security.md](references/security.md).
2. **Secrets stay in agenix.** Store with `secret-add NAME`, use with `secret-run --only NAME -- <cmd>`. Map variable names *inside* the command: `secret-run --only DIGITALOCEAN_READ_TOKEN -- bash -c 'DIGITALOCEAN_ACCESS_TOKEN=$DIGITALOCEAN_READ_TOKEN doctl compute droplet list'`. Never `-- env X="$Y" cmd`: the outer shell expands `$Y` before decryption and the value is empty. Never print, echo or write a token to disk. Generic rules: [secrets skill](../secrets/SKILL.md).
3. **Terraform only, remote state on Spaces.** S3 backend with `endpoints.s3`, the `skip_*` flags and `use_lockfile = true` ([Spaces backend](https://docs.digitalocean.com/products/spaces/reference/terraform-backend/)). Provider `digitalocean/digitalocean ~> 2.100`. No local state. DigitalOcean specifics: [references/terraform.md](references/terraform.md); generic practice: [terraform skill](../terraform/SKILL.md).
4. **One VPC per environment, deny by default.** Every Droplet, DOKS cluster, database and internal load balancer lives in an environment VPC; cloud firewalls block everything not explicitly allowed and are attached by tag ([VPC best practices](https://docs.digitalocean.com/products/networking/vpc/concepts/best-practices/), [firewalls](https://docs.digitalocean.com/products/networking/firewalls/)).
5. **Databases only reachable from trusted sources** (tags, Droplets, DOKS, Apps or CIDRs) and over the private hostname ([secure a cluster](https://docs.digitalocean.com/products/databases/postgresql/how-to/secure/)).
6. **MCP servers are read-only by default.** The DigitalOcean MCP server has no read-only flag; the Read Only token is the boundary. Write access is a deliberate per-project opt-in. See [references/mcp.md](references/mcp.md).
7. **Tags on everything** (`project`, `env`, `managed-by:terraform`) and every resource in the right DigitalOcean project. Firewalls, load balancers and database trusted sources all key off tags.

## Workflow

```bash
secret-run --only DIGITALOCEAN_ACCESS_TOKEN -- doctl account get     # verify team and token before anything else
secret-run --only DIGITALOCEAN_ACCESS_TOKEN -- terraform init         # provider reads DIGITALOCEAN_ACCESS_TOKEN
secret-run --only DIGITALOCEAN_ACCESS_TOKEN -- terraform plan -out=plan.tfplan
tflint --recursive && trivy config .
secret-run --only DIGITALOCEAN_ACCESS_TOKEN -- terraform apply plan.tfplan
```

Spaces state needs the Spaces key pair too: `secret-run --only DIGITALOCEAN_ACCESS_TOKEN,AWS_ACCESS_KEY_ID,AWS_SECRET_ACCESS_KEY -- terraform init`. Before `apply`: read the plan, confirm `doctl account get` shows the intended team, and check nothing is destroyed unintentionally. Never apply from a dirty working tree.

## Review checklist

Run this on every PR that touches DigitalOcean infrastructure.

- [ ] `terraform fmt -check`, `terraform validate`, `tflint`, `trivy config .` pass with no HIGH/CRITICAL.
- [ ] Backend is the Spaces S3 backend with `use_lockfile = true`; no credentials in the backend block or provider block.
- [ ] Provider pinned `~> 2.100`; module versions pinned.
- [ ] Every Droplet has `vpc_uuid`, `ssh_keys`, `monitoring = true`, tags, and backups on if stateful ([digitalocean_droplet](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/droplet)).
- [ ] A `digitalocean_firewall` covers every Droplet tag; no `0.0.0.0/0` inbound except 80/443 on public entry points and never on 22 ([digitalocean_firewall](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/firewall)).
- [ ] Databases: `private_network_uuid` set, a `digitalocean_database_firewall` exists, production has a standby node ([features](https://docs.digitalocean.com/products/databases/postgresql/details/features/)).
- [ ] Spaces buckets `acl = "private"` with versioning; public content goes through the CDN endpoint, not `public-read` ([digitalocean_spaces_bucket](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/spaces_bucket)).
- [ ] DOKS: `ha = true` for production, `auto_upgrade` and `surge_upgrade` on, a maintenance window set ([digitalocean_kubernetes_cluster](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/kubernetes_cluster)).
- [ ] Load balancers use tag targets and a managed Let's Encrypt certificate; `redirect_http_to_https = true` ([digitalocean_loadbalancer](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/loadbalancer)).
- [ ] Alert policies exist for CPU, memory, disk and an uptime check for each public endpoint ([monitoring](https://docs.digitalocean.com/products/monitoring/), [uptime](https://docs.digitalocean.com/products/uptime/)).
- [ ] Tokens used by CI have custom scopes and an expiry; none are Full Access.

## Architecture defaults

Use these unless the spec says otherwise, and say why when you deviate. Detail: [references/architecture.md](references/architecture.md).

| Area | Default | Why |
|---|---|---|
| Organisation | One team per company, one DigitalOcean project per workload+environment | Billing and role boundary; projects group resources ([teams](https://docs.digitalocean.com/platform/teams/), [projects](https://docs.digitalocean.com/products/projects/)) |
| Network | One VPC per environment per region; managed NAT gateway for private egress | VPCs are isolated from the internet and each other ([VPC](https://docs.digitalocean.com/products/networking/vpc/)) |
| Perimeter | Cloud firewalls by tag, deny by default; regional load balancer as the only public entry | Firewalls block anything without a rule ([firewalls](https://docs.digitalocean.com/products/networking/firewalls/), [load balancers](https://docs.digitalocean.com/products/networking/load-balancers/)) |
| Compute | App Platform for web apps and workers; DOKS when you need Kubernetes; Droplets only for what neither fits | Least to patch first ([App Platform](https://docs.digitalocean.com/products/app-platform/), [DOKS](https://docs.digitalocean.com/products/kubernetes/)) |
| Data | Managed database with standby, in the VPC, trusted sources only; Spaces private with versioning + CDN | Daily backups and 7-day PITR come with managed DBs ([DB features](https://docs.digitalocean.com/products/databases/postgresql/details/features/), [Spaces](https://docs.digitalocean.com/products/spaces/)) |
| Images | One container registry per team, garbage collection scheduled, DOKS integration on | Private pulls without pasting credentials ([DOCR](https://docs.digitalocean.com/products/container-registry/)) |
| Recovery | Droplet backups on stateful Droplets, snapshots before risky changes | Backups are automatic; snapshots are kept indefinitely ([backups](https://docs.digitalocean.com/products/backups/), [snapshots](https://docs.digitalocean.com/products/snapshots/)) |
| Observability | Metrics agent on every Droplet, alert policies, uptime checks | Nobody watches graphs ([monitoring](https://docs.digitalocean.com/products/monitoring/)) |

## Tools in this shell

| Tool | Use it for |
|---|---|
| `doctl` | Every API call; reads `DIGITALOCEAN_ACCESS_TOKEN` ([doctl](https://github.com/digitalocean/doctl)); see [references/cli-cheatsheet.md](references/cli-cheatsheet.md) |
| `terraform`, `tflint`, `trivy` | IaC, lint, security scan; run Terraform through `secret-run` |
| `kubectl` (via the [kubernetes skill](../kubernetes/SKILL.md)) | After `doctl kubernetes cluster kubeconfig save <cluster>` |

## References

- [references/architecture.md](references/architecture.md) — projects, regions, VPC, firewalls, load balancers, compute choice, databases, Spaces, registry, backups, monitoring
- [references/security.md](references/security.md) — PAT scopes and expiry, team roles, SSH keys, firewalls, trusted sources, Spaces keys, security history
- [references/cli-cheatsheet.md](references/cli-cheatsheet.md) — doctl auth, read/inspect commands, `secret-run` patterns
- [references/terraform.md](references/terraform.md) — Spaces backend, provider, resource conventions, gotchas
- [references/mcp.md](references/mcp.md) — `digitalocean` and `digitalocean-docs` MCP servers, token boundary, write opt-in
