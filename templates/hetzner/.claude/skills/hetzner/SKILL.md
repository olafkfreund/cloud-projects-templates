---
name: hetzner
description: Hetzner Cloud best practices for writing, reviewing and deploying infrastructure with Terraform and the hcloud CLI. Use when a task touches Hetzner Cloud projects, API tokens, servers, private networks and subnets, firewalls, load balancers, volumes, placement groups, primary IPs, floating IPs, backups and snapshots, Object Storage (S3-compatible, also as Terraform remote state), Kubernetes on Hetzner (hcloud-cloud-controller-manager, csi-driver, k3s, Talos), the hcloud CLI, or the Terraform hetznercloud/hcloud provider. Covers project-per-environment isolation, Read vs Read & Write tokens (HCLOUD_TOKEN vs HCLOUD_TOKEN_RW), SSH-key-only access, default-deny firewalls by label selector, the semi-verified Object Storage state backend, and why there is no Hetzner MCP server.
---

# Hetzner Cloud

Rules for every Hetzner Cloud task in this project. Read the linked reference before touching the matching area. Verified against official docs on 2026-09-15.

## Non-negotiables

1. **One project per workload per environment.** A project is the isolation boundary: its own resources, members, API tokens and S3 credentials ([Cloud FAQ](https://docs.hetzner.com/cloud/general/faq/)). Never mix prod and dev in one project. See [references/architecture.md](references/architecture.md).
2. **Read token for agents, Read & Write token for deploys.** Tokens are per project with two permission levels: Read (GET only) and Read & Write ([Generating an API token](https://docs.hetzner.com/cloud/api/getting-started/generating-api-token/)). Store a Read token as `HCLOUD_TOKEN` for inspection sessions; `hcloud` and the Terraform provider both read it. Store the Read & Write token as `HCLOUD_TOKEN_RW` and only map it to `HCLOUD_TOKEN` inside a `secret-run` command (see Workflow). See [references/security.md](references/security.md).
3. **Secrets stay in agenix.** `secret-add NAME`, then `secret-run --only NAME -- <cmd>`. Never print, echo, log or write a token to disk; never pass `token = "..."` to the provider or put it in tfvars. See [secrets skill](../secrets/SKILL.md).
4. **SSH keys only.** Create servers with an `hcloud_ssh_key`; Hetzner then sends no root password and current images disable root password authentication ([Servers FAQ](https://docs.hetzner.com/cloud/servers/faq/)). Never re-enable it.
5. **Firewall on every server, by label selector.** Hetzner firewalls default to deny all inbound, allow all outbound ([Firewalls overview](https://docs.hetzner.com/cloud/firewalls/overview/)). Attach via `apply_to { label_selector = ... }` so a new server matching the labels is covered automatically. No `0.0.0.0/0` on anything but 80/443 on a load balancer or `22` from a known CIDR.
6. **Terraform only, provider `hetznercloud/hcloud ~> 1.69`**, remote state on Hetzner Object Storage via the S3 backend. That backend recipe is semi-verified; treat CI as the single writer. See [references/terraform.md](references/terraform.md); generic practice: [terraform skill](../terraform/SKILL.md).
7. **No MCP server.** Hetzner ships none; community ones are unvetted. Agents inspect with `hcloud ... -o json` under the Read token. See [references/mcp.md](references/mcp.md).
8. **Know what Hetzner does not manage.** There is no managed Kubernetes, managed database or managed secrets store. You run them yourself (CCM + CSI on k3s/Talos, or a database on a server with volumes and backups). Say so in the spec before choosing Hetzner for a workload that needs them.

## Workflow

```bash
secret-add HCLOUD_TOKEN                                   # Read token, once per project
secret-add HCLOUD_TOKEN_RW                                # Read & Write token, once per project
secret-run --only HCLOUD_TOKEN -- hcloud server list      # verify project and token before anything else
secret-run --only HCLOUD_TOKEN -- terraform init          # backend creds: see references/terraform.md
secret-run --only HCLOUD_TOKEN -- terraform plan -out=plan.tfplan
tflint --recursive && trivy config .
secret-run --only HCLOUD_TOKEN_RW -- bash -c 'HCLOUD_TOKEN=$HCLOUD_TOKEN_RW terraform apply plan.tfplan'
```

Why `bash -c '...'` with single quotes: `secret-run` decrypts the secret into the child's environment. In `secret-run --only HCLOUD_TOKEN_RW -- env HCLOUD_TOKEN="$HCLOUD_TOKEN_RW" cmd` the outer shell expands `$HCLOUD_TOKEN_RW` before `secret-run` runs, so the provider gets an empty token. Single quotes defer the expansion to the child shell, where the value exists.

Before `apply`: confirm `hcloud server list` shows the intended project (token = project), read the plan, and check nothing is destroyed unintentionally. Never apply from a dirty working tree.

## Review checklist

- [ ] `terraform fmt -check`, `terraform validate`, `tflint`, `trivy config .` pass with no HIGH/CRITICAL.
- [ ] Provider pinned `~> 1.69`; no `token =` argument; state backend is Object Storage with the full `skip_*` set and the semi-verified note kept.
- [ ] Every `hcloud_server` has `ssh_keys`, a `firewall` reached by label selector, a `placement_group` when it is part of a replicated set, and `labels` (`project`, `environment`, `owner`, `managed_by=terraform`).
- [ ] Servers that do not need a public IP have `public_net { ipv4_enabled = false }` and sit on a private network with a subnet in the correct network zone ([Networks FAQ](https://docs.hetzner.com/cloud/networks/faq/)).
- [ ] Load balancer targets use `use_private_ip = true`; only the load balancer is public.
- [ ] Volumes are in the same location as their server; backups enabled on stateful servers; snapshots before risky changes ([Backups and snapshots](https://docs.hetzner.com/cloud/servers/backups-snapshots/overview/)).
- [ ] Tokens: only `HCLOUD_TOKEN` (Read) appears in agent/inspection contexts; `HCLOUD_TOKEN_RW` only inside `secret-run ... bash -c`.
- [ ] `delete_protection` and `rebuild_protection` on production servers, volumes and IPs.

## Architecture defaults

| Area | Default | Why |
|---|---|---|
| Isolation | One project per workload per environment; tokens and S3 credentials per project | Project is the only boundary ([Cloud FAQ](https://docs.hetzner.com/cloud/general/faq/)) |
| Location | `fsn1`/`nbg1`/`hel1` (eu-central) unless latency says otherwise; keep a network inside one zone | Networks and floating IPs are zone-bound ([Locations](https://docs.hetzner.com/cloud/general/locations/)) |
| Network | Private network `10.0.0.0/8`, one subnet per tier; public IPv4 only on load balancers and bastion | Private networks are free and RFC 1918 ([Networks overview](https://docs.hetzner.com/cloud/networks/overview/)) |
| Ingress | Hetzner load balancer with private targets, TLS via managed certificate | Only the LB is exposed ([Load balancers](https://docs.hetzner.com/cloud/load-balancers/overview/)) |
| Resilience | Spread placement group per replicated service (max 10 servers) | Different physical hosts ([Placement groups](https://docs.hetzner.com/cloud/placement-groups/overview/)) |
| Data | Volumes (10 GB to 10 TB, triple replicated) + daily backups + snapshots before change | Volumes are not covered by backups ([Volumes](https://docs.hetzner.com/cloud/volumes/overview/)) |
| Kubernetes | Self-managed (k3s or Talos) with hcloud-cloud-controller-manager and csi-driver; separate Read & Write token for the cluster | No managed offering ([CCM](https://github.com/hetznercloud/hcloud-cloud-controller-manager), [CSI](https://github.com/hetznercloud/csi-driver)) |
| Object Storage | One bucket per purpose, per-project S3 credentials, bucket policy for anything beyond the default | Keys are project-wide by default ([Object Storage](https://docs.hetzner.com/storage/object-storage/overview/)) |

## Tools in this shell

| Tool | Use it for |
|---|---|
| `hcloud` | Every API call and all agent inspection; see [references/cli-cheatsheet.md](references/cli-cheatsheet.md) |
| `terraform`, `tflint`, `trivy` | IaC, lint, security scan |
| `kubectl`, `helm` (only if the `kubernetes` provider is also selected) | CCM/CSI install and cluster inspection; see [kubernetes skill](../kubernetes/SKILL.md) |

## References

- [references/architecture.md](references/architecture.md) — projects, locations and zones, networks, firewalls, LBs, placement groups, volumes, IPs, backups, Kubernetes on Hetzner, what is not managed
- [references/security.md](references/security.md) — token scoping and rotation, SSH-only access, firewall by selector, audit
- [references/cli-cheatsheet.md](references/cli-cheatsheet.md) — `hcloud` contexts, read/inspect commands, JSON output
- [references/terraform.md](references/terraform.md) — provider, Object Storage backend (semi-verified), resource patterns, gotchas
- [references/mcp.md](references/mcp.md) — why no MCP server is configured, community servers, `hcloud` as the read path
