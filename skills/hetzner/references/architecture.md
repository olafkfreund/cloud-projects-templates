# Hetzner Cloud architecture

What the platform gives you, what it does not, and the defaults this project uses. Sources are the official docs at docs.hetzner.com and the hetznercloud GitHub organisation, checked 2026-09-15.

## Projects: the isolation boundary

A project groups servers, networks, volumes, buckets and so on. Members have roles (owner, admin, member, restricted); admins manage members, API tokens and S3 credentials. Default limit 20 projects per account ([Cloud FAQ](https://docs.hetzner.com/cloud/general/faq/)). API tokens are generated inside a project and only see that project ([Generating an API token](https://docs.hetzner.com/cloud/api/getting-started/generating-api-token/)).

There is no organisation/account-level policy layer, no cross-project network peering, and no per-resource IAM. Consequences:

- **One project per workload per environment** (`shop-prod`, `shop-staging`). A token leak then exposes one environment.
- Resources that must talk over a private network must live in the same project and network zone.
- Object Storage credentials are also per project and, by default, valid for every bucket in it ([Object Storage overview](https://docs.hetzner.com/storage/object-storage/overview/)); keep Terraform state in its own project if other teams share buckets.

## Locations and network zones

Six locations in four network zones ([Locations](https://docs.hetzner.com/cloud/general/locations/), [Networks FAQ](https://docs.hetzner.com/cloud/networks/faq/)):

| Zone | Locations |
|---|---|
| `eu-central` | `fsn1` Falkenstein, `nbg1` Nuremberg, `hel1` Helsinki |
| `us-east` | `ash` Ashburn |
| `us-west` | `hil` Hillsboro |
| `ap-southeast` | `sin` Singapore |

A private network's subnets are bound to a network zone, and every server in that subnet must be in a location of that zone. Floating IPs are bound to a zone too. There is no cross-zone private networking; cross-zone traffic goes over public IPs (encrypt it yourself, for example WireGuard). Object Storage exists only in `fsn1`, `nbg1` and `hel1`.

Default: build in `eu-central`, spread replicated services across two of its locations when the workload tolerates the latency, and treat multi-zone as a separate deployment.

## Private networks and subnets

Networks are free, IPv4 only, and accept any RFC 1918 range (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`). Limits: 50 subnets, 100 routes, 100 attached resources per network ([Networks overview](https://docs.hetzner.com/cloud/networks/overview/), [Networks FAQ](https://docs.hetzner.com/cloud/networks/faq/)). `172.31.1.1` is reserved as the public interface gateway.

Pattern: network `10.0.0.0/8`; subnet `10.0.1.0/24` for load balancers and bastion, `10.0.2.0/24` for application servers, `10.0.3.0/24` for data servers, type `cloud`. Servers that do not need to be reachable from the internet are created with public IPv4 disabled; outbound traffic then needs a NAT route via a gateway server, so decide early whether the tier needs egress at all.

## Firewalls

Stateful, applied to servers, default deny inbound and allow outbound. Limits: 5 firewalls per server, 50 per project, 500 effective rules per firewall ([Firewalls overview](https://docs.hetzner.com/cloud/firewalls/overview/)). Attach by **label selector** so any server carrying `role=web` inherits the `web` firewall without a manual step. Firewalls filter the public interface; traffic inside a private network is not filtered by them, so the private network is the trust boundary and firewalls are the perimeter.

Baseline set: `bastion` (22 from office/VPN CIDRs), `web` (80/443 from anywhere, only if the server is a public LB target that must be public), `internal` (no inbound rules at all). Load balancers are not covered by firewalls; restrict their services instead.

## Load balancers

Distribute to public or private IPv4 targets with round robin or least connections; joining a private network gives the LB a private IPv4 so targets need no public IP ([Load balancers overview](https://docs.hetzner.com/cloud/load-balancers/overview/)). Targets can be individual servers or a label selector, which pairs well with placement groups and autoscaled node pools. Terminate TLS on the LB with a managed certificate (`hcloud_managed_certificate`) and keep the target protocol HTTP inside the private network.

## Placement groups

One type: **spread**, which places every member on a different physical host. Limits: one group per server, 10 servers per group, 50 groups per project ([Placement groups](https://docs.hetzner.com/cloud/placement-groups/overview/)). Use one per replicated service (web tier, etcd/control plane, database replicas). It protects against a single host failure, not a location failure.

## Volumes

Network block storage, 10 GB to 10 TB in 1 GB steps, replicated three times, attached to at most one server at a time, up to 16 per server, bound to a location ([Volumes overview](https://docs.hetzner.com/cloud/volumes/overview/)). Create them in the same location as the server; they cannot move between locations. Backups and snapshots do **not** include volumes, so data on volumes needs its own backup path (database dumps to Object Storage, or filesystem snapshots you manage).

## Primary and floating IPs

- **Primary IP**: the server's own public IPv4/IPv6. Can exist unassigned and be moved between powered-off servers; one v4 and one v6 per server; IPv4 is billed, IPv6 is free ([Primary IPs](https://docs.hetzner.com/cloud/servers/primary-ips/overview/)). Set `public_net { ipv4_enabled = false, ipv6_enabled = true }` on private-only servers.
- **Floating IP**: project-level address that can be reassigned to any server in the same network zone at any time, one server at a time; the OS must be configured to answer for it ([Floating IPs](https://docs.hetzner.com/cloud/floating-ips/overview/)). Use it for failover of a single-instance service; use a load balancer for anything with more than one backend.

## Backups and snapshots

Backups are automatic daily disk copies, seven rotating slots per server, enabled per server. Snapshots are manual, kept until deleted, default 30 per account ([Backups and snapshots](https://docs.hetzner.com/cloud/servers/backups-snapshots/overview/)). Both exclude volumes. Enable backups on every stateful server; take a snapshot before an in-place upgrade; use snapshots as golden images for `hcloud_server.image`.

## Kubernetes on Hetzner

Hetzner has no managed Kubernetes. You run the cluster and integrate it with two official components:

- [hcloud-cloud-controller-manager](https://github.com/hetznercloud/hcloud-cloud-controller-manager): node lifecycle, `Service type=LoadBalancer` backed by Hetzner load balancers, and routes over a private network. Requires `kubelet --cloud-provider=external`, a secret `hcloud` in `kube-system` with key `token` (and `network` for private networking), Helm repo `https://charts.hetzner.cloud`, chart `hcloud/hcloud-cloud-controller-manager` with `networking.enabled=true` and `networking.clusterCIDR` ([quickstart](https://github.com/hetznercloud/hcloud-cloud-controller-manager/blob/main/docs/guides/quickstart.md), [private network setup](https://github.com/hetznercloud/hcloud-cloud-controller-manager/blob/main/docs/guides/private-network-setup.md)). Pick a CNI with native routing (the guide names Cilium `routing-mode: native`). Suggested ranges: network `10.0.0.0/8`, node subnet `10.0.0.0/24`, cluster CIDR `10.244.0.0/16`, service CIDR `10.43.0.0/16` ([private networks explanation](https://github.com/hetznercloud/hcloud-cloud-controller-manager/blob/main/docs/explanation/private-networks.md)).
- [csi-driver](https://github.com/hetznercloud/csi-driver): ReadWriteOnce PersistentVolumes on Hetzner volumes, same `hcloud` secret, chart `hcloud/hcloud-csi` ([quickstart](https://github.com/hetznercloud/csi-driver/blob/main/docs/kubernetes/guides/quickstart.md)). Volume limits above apply per node (16 volumes, 10 GB minimum).

Both need a **Read & Write** token; give the cluster its own token so it can be rotated independently of CI.

Distribution: [k3s](https://docs.k3s.io/installation) or [Talos on Hetzner](https://docs.siderolabs.com/talos/latest/platform-specific-installations/cloud-platforms/hetzner/). Community Terraform modules (kube-hetzner, hcloud-talos, hcloud-kubernetes) are listed in [awesome-hcloud](https://github.com/hetznercloud/awesome-hcloud); they are community projects, review them before use. Cluster conventions beyond the Hetzner integration: [kubernetes skill](../../kubernetes/SKILL.md).

## What Hetzner does not manage

No managed Kubernetes, no managed database, no managed cache or queue, no secrets manager, no IAM beyond project roles and token permission levels, no audit-log API. Implications for a spec:

- Databases run on servers with a volume, a spread placement group, daily backups and dumps to Object Storage. Budget the operations time.
- Runtime secrets live in the application's own store (for example a Vault or SOPS setup you run); Terraform inputs come through `secret-run`.
- Auditing is what you log yourself plus the console's activity view; see [security.md](security.md).
- Cost is predictable and low, but the design must accept single-region operation and self-managed data services. If the workload needs a managed database or multi-region failover, say so in the spec and choose another provider for that piece.
