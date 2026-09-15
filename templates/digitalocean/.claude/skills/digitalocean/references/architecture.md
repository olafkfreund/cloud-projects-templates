# DigitalOcean architecture

Defaults for laying out a workload on DigitalOcean. Each section says what to do, why, and where the official page is. Generic Kubernetes practice lives in the [kubernetes skill](../../kubernetes/SKILL.md).

## Teams and projects

- **Team** = billing boundary and role boundary. One team per company or business unit; members get a role (Owner, Biller, Billing Viewer, Member, Modifier, Resource Viewer) ([teams](https://docs.digitalocean.com/platform/teams/), [predefined roles](https://docs.digitalocean.com/platform/teams/roles/predefined/)). Tokens inherit the creator's role, so a token is never more powerful than its owner.
- **Project** = grouping of resources inside a team. One project per workload per environment (`shop-prod`, `shop-staging`). Resources not assigned land in the default project, so set `project_id` in Terraform ([projects](https://docs.digitalocean.com/products/projects/), [digitalocean_project](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/project)).
- Projects do not isolate anything (no network or permission boundary). Isolation comes from VPCs, firewalls and tokens.

## Regions

Pick one region per environment and keep VPC, Droplets, DOKS, databases and load balancers in it: a VPC is bound to one datacenter and "resources you add to the VPC network must be in the same region" ([create a VPC](https://docs.digitalocean.com/products/networking/vpc/how-to/create/)). Spaces regions are a separate list (e.g. `nyc3`, `ams3`, `fra1`, `sgp1`, `sfo3`); state buckets are regional too. Multi-region is a global load balancer plus VPC peering, not a single stretched VPC ([global load balancer](https://docs.digitalocean.com/products/networking/load-balancers/how-to/create-global-load-balancer/), [VPC peering](https://docs.digitalocean.com/products/networking/vpc/how-to/create-peering/)).

## VPC per environment

DigitalOcean's own guidance: "create a VPC network for each of your development, staging, and production environments" and put separate tenants in their own VPCs ([VPC best practices](https://docs.digitalocean.com/products/networking/vpc/concepts/best-practices/)).

- Let DigitalOcean generate the IP range unless you must peer with something; ranges cannot overlap other networks in the account ([create](https://docs.digitalocean.com/products/networking/vpc/how-to/create/)).
- VPC traffic is isolated from the internet and other VPCs and is not billed as bandwidth ([VPC](https://docs.digitalocean.com/products/networking/vpc/)).
- Private-only Droplets and isolated DOKS workers reach the internet through a managed NAT gateway; verify outbound connectivity from every backend before relying on it ([NAT gateway](https://docs.digitalocean.com/products/networking/vpc/how-to/create-nat-gateway/)).
- Point backends at the VPC-local DNS resolver to avoid rate limiting ([local DNS resolver](https://docs.digitalocean.com/products/networking/vpc/how-to/use-local-dns-resolver/)).
- Do not use the region's default VPC for anything but throwaway experiments; Terraform-managed VPCs are the source of truth ([digitalocean_vpc](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/vpc)).

## Cloud firewalls by tag

Cloud firewalls "block all traffic that isn't expressly permitted by a rule" ([firewalls](https://docs.digitalocean.com/products/networking/firewalls/)). Design them by role, not by host:

| Firewall | Applied to tag | Inbound |
|---|---|---|
| `<env>-web` | `<env>-web` | 80/443 from the load balancer only (`load_balancer_uid`), never from `0.0.0.0/0` |
| `<env>-app` | `<env>-app` | app port from tag `<env>-web` |
| `<env>-db-client` | `<env>-app` | none extra; used as a database trusted source |
| `<env>-mgmt` | every tag | 22 from the office/VPN CIDR or a bastion tag only |

A Droplet with several tags gets the rules of every matching firewall ([organising firewalls](https://docs.digitalocean.com/products/networking/firewalls/concepts/organization/)). Sources can be tags, Droplet IDs, load balancer UIDs, Kubernetes cluster IDs or CIDRs ([configure rules](https://docs.digitalocean.com/products/networking/firewalls/how-to/configure-rules/)). Since August 2026 firewalls also have explicit deny rules that win over allows; use them for known-bad ranges, not as a substitute for the default deny.

## Load balancers

- **Regional load balancer** is the only public entry for Droplet-based workloads. Target Droplets by tag so scaling is a tag change, terminate TLS with a managed Let's Encrypt certificate (renewed automatically), enable `redirect_http_to_https`, and let health checks remove bad backends ([features](https://docs.digitalocean.com/products/networking/load-balancers/details/features/), [SSL termination](https://docs.digitalocean.com/products/networking/load-balancers/how-to/ssl-termination/)).
- **Internal load balancer** (no public IP, reachable only inside the VPC) between tiers.
- **Network load balancer** for raw TCP/UDP; **global load balancer** for multi-region ([load balancers](https://docs.digitalocean.com/products/networking/load-balancers/)).
- Enable PROXY protocol only if the backend understands it; otherwise pass client IPs through `X-Forwarded-For`.
- DOKS gets load balancers from `Service type=LoadBalancer` annotations; do not create those in Terraform as well.

## Droplets vs App Platform vs DOKS

| Choose | When | Notes |
|---|---|---|
| **App Platform** | HTTP services, workers, static sites built from a Git repo or image; no OS to run | App spec in Git, attach to a VPC via `vpc.id` (one VPC per app, excludes dedicated egress IPs), scale by component ([App Platform](https://docs.digitalocean.com/products/app-platform/), [app spec](https://docs.digitalocean.com/products/app-platform/reference/app-spec/), [VPC](https://docs.digitalocean.com/products/app-platform/how-to/enable-vpc/)) |
| **DOKS** | You already run Kubernetes manifests/Helm, need operators, sidecars, or many services | Managed control plane, HA option (cannot be turned off once on), VPC-native networking, RBAC on by default, control-plane firewall, isolated workers without public IPv4 ([DOKS](https://docs.digitalocean.com/products/kubernetes/), [features](https://docs.digitalocean.com/products/kubernetes/details/features/), [create](https://docs.digitalocean.com/products/kubernetes/how-to/create-clusters/)) |
| **Droplets** | Stateful or licensed software, custom kernels, GPUs, anything the two above cannot run | Cloud-init, SSH keys only, metrics agent, backups, in a VPC behind a firewall ([Droplets](https://docs.digitalocean.com/products/droplets/), [recommended setup](https://docs.digitalocean.com/products/droplets/getting-started/recommended-droplet-setup/)) |

Order of preference is App Platform, DOKS, Droplets: each step down adds patching and paging you own.

DOKS specifics: turn on HA for production, use `auto_upgrade` with `surge_upgrade` and a maintenance window, one node pool per workload class with the cluster autoscaler ([autoscaling](https://docs.digitalocean.com/products/kubernetes/how-to/autoscaling/), [upgrade](https://docs.digitalocean.com/products/kubernetes/how-to/upgrade-cluster/)), and fetch kubeconfig with `doctl kubernetes cluster kubeconfig save`, which issues a revocable OAuth token on current versions ([connect](https://docs.digitalocean.com/products/kubernetes/how-to/connect-to-cluster/)).

## Managed databases

- Create the cluster inside the environment VPC and connect over the private hostname; "only resources in the same VPC network as the cluster can connect using the private hostname" ([connect](https://docs.digitalocean.com/products/databases/postgresql/how-to/connect/)).
- Add **trusted sources** (tags, Droplets, DOKS clusters, Apps, CIDRs; up to 100 rules) so nothing else can reach it, and verify TLS with `sslmode=verify-full` ([secure](https://docs.digitalocean.com/products/databases/postgresql/how-to/secure/)).
- Production gets a standby node for automatic failover. Daily backups plus 7-day point-in-time restore are included ([features](https://docs.digitalocean.com/products/databases/postgresql/details/features/)).
- Separate database users per application, never the `doadmin` user in app config ([digitalocean_database_user](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/database_user)).

## Spaces and CDN

- Buckets are `private`; serve public assets through the CDN endpoint (`<bucket>.<region>.cdn.digitaloceanspaces.com`) with a custom domain and Let's Encrypt certificate rather than `public-read` on the bucket ([enable CDN](https://docs.digitalocean.com/products/spaces/how-to/enable-cdn/)).
- Turn on versioning for state and anything humans upload; add lifecycle rules for logs ([digitalocean_spaces_bucket](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/spaces_bucket)).
- One access key per application, per-bucket permissions (Read or Read/Write/Delete). Per-bucket keys do not work with bucket policies, so pick one model per bucket ([manage access](https://docs.digitalocean.com/products/spaces/how-to/manage-access/)).
- Limits: 100 buckets and 200 access keys per account, 5 GB per upload ([limits](https://docs.digitalocean.com/products/spaces/details/limits/)). Cold Storage buckets cannot use the CDN.

## Container registry

One private registry per team. Enable the DOKS integration so clusters pull without a hand-made secret, schedule garbage collection (or enable the automatic preview) to stop paying for orphaned layers, and push from CI with a scoped token ([DOCR](https://docs.digitalocean.com/products/container-registry/), [use with Docker and Kubernetes](https://docs.digitalocean.com/products/container-registry/how-to/use-registry-docker-kubernetes/), [digitalocean_container_registry](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/container_registry)).

## Backups and snapshots

- **Backups**: automatic Droplet disk images at 4h/6h/12h/daily/weekly intervals, usage-based pricing. Enable on every stateful Droplet; useless for DOKS nodes and App Platform ([backups](https://docs.digitalocean.com/products/backups/), [enable](https://docs.digitalocean.com/products/backups/how-to/enable/)).
- **Snapshots**: on-demand Droplet or volume images kept indefinitely, copyable to other regions, transferable between teams. Take one before a risky in-place change; convert a backup to a snapshot to keep it ([snapshots](https://docs.digitalocean.com/products/snapshots/), [convert](https://docs.digitalocean.com/products/backups/how-to/convert-to-snapshot/)).
- Neither can be downloaded; export application data separately if you need an off-platform copy.
- Managed databases have their own backups; Spaces has versioning. Test a restore per environment at least once.

## Monitoring and alerts

- Install the metrics agent on every Droplet (`--enable-monitoring` or `monitoring = true`); it is free and feeds alert policies ([monitoring](https://docs.digitalocean.com/products/monitoring/)).
- Alert policies for CPU, memory, disk and load, delivered to email and Slack ([digitalocean_monitor_alert](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/monitor_alert)).
- Uptime checks (HTTP/HTTPS/ICMP) on every public endpoint, with latency and certificate-expiry alerts ([uptime](https://docs.digitalocean.com/products/uptime/), [digitalocean_uptime_check](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/uptime_check)).
- App Platform and DOKS expose their own metrics and alerts; wire those to the same channels so one on-call view exists.
- Review the team's security history after any incident ([security history](https://docs.digitalocean.com/platform/teams/how-to/view-security-history/)).
