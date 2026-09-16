# Hetzner Cloud security

Token handling, server access, network perimeter and audit. Official sources checked 2026-09-15.

## Tokens: scope by project and by purpose

A token belongs to one project and has one of two permissions: **Read** (GET only) or **Read & Write** (GET, POST, PUT, DELETE). Every API request carries it as `Authorization: Bearer <token>`; it is shown once at creation ([Generating an API token](https://docs.hetzner.com/cloud/api/getting-started/generating-api-token/), [API reference](https://docs.hetzner.cloud/reference/cloud)). There is no finer scope, no IP allow-list and no expiry, so the token's project and permission level are the whole access model.

Rules in this project:

| Purpose | Permission | Secret name | Who uses it |
|---|---|---|---|
| Agent inspection, `terraform plan`, reviews | Read | `HCLOUD_TOKEN` | Claude, developers, PR checks |
| `terraform apply`, `hcloud` mutations | Read & Write | `HCLOUD_TOKEN_RW` | CI deploy job, break-glass by a human |
| Kubernetes CCM + CSI | Read & Write | in-cluster secret `hcloud` | The cluster only |

- One token per purpose and per consumer. Name the token in the console after the consumer (`ci-deploy`, `claude-read`, `k8s-ccm`) so revocation is targeted.
- Never share a token between projects (impossible) or between environments (do not create a prod token for a staging pipeline "for convenience").
- Store with `secret-add HCLOUD_TOKEN` / `secret-add HCLOUD_TOKEN_RW`; use with `secret-run --only NAME -- cmd`. Never `echo`, never write to `.env`, never `terraform.tfvars`, never `hcloud context create` on a shared machine (it writes the token to `~/.config/hcloud/cli.toml`, see [CLI configuration](https://github.com/hetznercloud/cli/blob/main/docs/reference/configuration.md)).
- Mapping the write token: `secret-run --only HCLOUD_TOKEN_RW -- bash -c 'HCLOUD_TOKEN=$HCLOUD_TOKEN_RW terraform apply plan.tfplan'`. Single quotes are mandatory; with double quotes the outer shell expands the variable before decryption and the child sees an empty token. See [secrets skill](../../secrets/SKILL.md).

### Rotation

Tokens do not expire, so rotate on a schedule (quarterly) and immediately on: a member leaving, a token appearing in any log or CI output, a laptop loss, or a dependency compromise. Procedure: create the new token, `secret-add` it under the same name, run one read command to prove it works, delete the old token in the console. For the cluster token, update the `hcloud` secret and restart the CCM and CSI controllers. Keep a `tokens.md` in the ops repo listing token name, purpose, permission and last rotation date; never the value.

## Server access: SSH keys only

Create servers with `ssh_keys` set. Hetzner then sends no root password, and recent images disable root password authentication by default ([Servers FAQ](https://docs.hetzner.com/cloud/servers/faq/)). Do not re-enable `PasswordAuthentication` in `sshd_config`, do not add keys through the console after creation (not possible anyway, [Creating a server](https://docs.hetzner.com/cloud/servers/getting-started/creating-a-server/)); manage keys with `hcloud_ssh_key` in Terraform and rotate them with a server rebuild or cloud-init.

- One `hcloud_ssh_key` per person or per CI system, labelled with the owner.
- Reach servers through a bastion on the private network, or through the console's VNC only in an emergency. No public port 22 on application or data servers.
- Harden the OS with cloud-init (`user_data`): unattended upgrades, `fail2ban` or equivalent on the bastion, no root login except by key.

## Network perimeter: firewalls by label selector

Firewalls block all inbound and allow all outbound by default ([Firewalls overview](https://docs.hetzner.com/cloud/firewalls/overview/)). Attach them with `apply_to { label_selector = "role=web" }` so a server is protected the moment it is labelled, and so an unlabelled server has no path in. Review rules:

- No `0.0.0.0/0` or `::/0` source except 80/443 on servers that must be public. Prefer a load balancer with private targets so no application server is public.
- Port 22 only from named CIDRs (office, VPN) and only on the bastion.
- Firewalls do not filter private-network traffic. Keep tiers in separate subnets and enforce intra-network policy on the host (nftables) or in Kubernetes (NetworkPolicy).
- Load balancers are not firewalled; expose only the services you mean to and terminate TLS on the LB with a managed certificate.

## Object Storage credentials

S3 keys are per project and by default valid for every bucket in that project; up to 200 keys per account ([Object Storage overview](https://docs.hetzner.com/storage/object-storage/overview/), [Generating S3 keys](https://docs.hetzner.com/storage/object-storage/getting-started/generating-s3-keys/)). Restrict a key to one bucket with a deny-all bucket policy that allow-lists `p<project_id>:<access_key>` ([S3 credentials FAQ](https://docs.hetzner.com/storage/object-storage/faq/s3-credentials)). Terraform state contains secrets in plain text, so the state bucket gets its own key pair, versioning on, and ideally its own project.

## Protection flags

Set `delete_protection = true` and `rebuild_protection = true` on production servers, and `delete_protection` on volumes, networks, load balancers, primary and floating IPs. A Read & Write token can still flip the flag, but the change becomes a visible, deliberate step in a plan.

## Audit

Hetzner exposes no audit-log API. What you have:

- The console's activity history per project (manual, per project).
- `hcloud` and Terraform run in CI with logs retained; every apply is a PR with the plan attached.
- Selected-field inventory reports (see [cli-cheatsheet.md](cli-cheatsheet.md)) kept private and Git-ignored. Review metadata sensitivity before sharing; do not commit unrestricted snapshots.
- `terraform plan` on a schedule with the Read token; a non-empty plan is drift, alert on it.

Quarterly review: list tokens and S3 keys per project, confirm each maps to a live consumer in `tokens.md`, delete the rest; list `hcloud ssh-key list` and remove keys of departed people; check firewalls for widened rules.
