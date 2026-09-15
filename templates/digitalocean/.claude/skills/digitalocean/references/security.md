# DigitalOcean security

Identity, tokens and the network boundary. Secrets handling in general: [secrets skill](../../secrets/SKILL.md).

## Personal access tokens

Tokens are created under **Account → API → Tokens** and behave like passwords; never hard-code them ([create a PAT](https://docs.digitalocean.com/reference/api/create-personal-access-token/)). Three scope models:

| Scope | Alias | Grants | Use for |
|---|---|---|---|
| **Read Only** | `api:read` | Read access to everything the creator's team role can see | Agents, MCP servers, dashboards: `DIGITALOCEAN_READ_TOKEN` |
| **Custom Scopes** | resource:action pairs, e.g. `droplet:read`, `droplet:create`, `firewall:delete`, `kubernetes:access_cluster` | Exactly the listed scopes; does **not** grow when the role gains permissions | Deploys and CI: `DIGITALOCEAN_ACCESS_TOKEN` |
| **Full Access** | `api:write` | Everything the role allows, including deletes | Break-glass only; never stored in a project |

Rules:

1. **Every token has an expiry.** The token form has an Expiration field; pick the shortest that fits the rotation cadence and put the date in the secret's description. Rotate before it lapses.
2. **Agents get Read Only.** Read Only and Full Access tokens follow the team role, so a role change silently widens them; that is acceptable for reads, not for writes.
3. **Deploys get Custom Scopes.** Pick scopes from the [scopes list](https://docs.digitalocean.com/reference/api/scopes/) per resource the Terraform root manages (`vpc:*`, `droplet:*`, `firewall:*`, `load_balancer:*`, `database:*`, `kubernetes:*`, `project:*`, `tag:*` as needed). Leave out `database:view_credentials` and `kubernetes:access_cluster` unless the root reads credentials.
4. **One token per consumer.** Separate tokens for CI, each developer, each MCP host. Revoking one does not break the others.
5. **Never Full Access in a repo, CI variable or `.mcp.json`.**
6. **Restricting a role revokes those permissions from existing tokens immediately** ([create a PAT](https://docs.digitalocean.com/reference/api/create-personal-access-token/)); use that when off-boarding.

Both `doctl` and the Terraform provider read `DIGITALOCEAN_ACCESS_TOKEN`; the provider also reads `DIGITALOCEAN_TOKEN` first ([doctl](https://github.com/digitalocean/doctl), [provider docs](https://github.com/digitalocean/terraform-provider-digitalocean/blob/main/docs/index.md)). Pass them through `secret-run`, mapping names inside `bash -c` when a read token must appear as `DIGITALOCEAN_ACCESS_TOKEN`:

```bash
secret-run --only DIGITALOCEAN_READ_TOKEN -- bash -c 'DIGITALOCEAN_ACCESS_TOKEN=$DIGITALOCEAN_READ_TOKEN doctl compute droplet list'
```

Not `-- env DIGITALOCEAN_ACCESS_TOKEN="$DIGITALOCEAN_READ_TOKEN" doctl …`: the outer shell expands the variable before `secret-run` decrypts it, so the value is empty.

## Teams and roles

Six predefined roles ([predefined roles](https://docs.digitalocean.com/platform/teams/roles/predefined/)):

| Role | Resources | Billing | Team settings |
|---|---|---|---|
| Owner | Full | Full | Full |
| Member | Full | None | Read only |
| Modifier | Full except delete | None | Read only |
| Resource Viewer | Read only | None | Read only |
| Biller | None | Full | None |
| Billing Viewer | None | Read only | None |

- Give engineers **Modifier** by default; Owner only to two or three people. Custom roles exist for finer splits ([permissions](https://docs.digitalocean.com/platform/teams/roles/permissions/)).
- Create service tokens from a dedicated **Resource Viewer** account for read-only agents, so even a Full Access token from that account cannot write.
- Enable **secure sign-in** so every member must use 2FA, Google SSO or GitHub SSO ([team settings](https://docs.digitalocean.com/platform/teams/settings/)). Set the security contact email so token and login alerts reach a monitored inbox ([teams](https://docs.digitalocean.com/platform/teams/)).

## SSH keys

- Upload public keys to the team and reference them at Droplet creation; password login is never enabled ([SSH keys](https://docs.digitalocean.com/products/droplets/how-to/add-ssh-keys/)).
- Manage keys in Terraform with `digitalocean_ssh_key` and pass `ssh_keys` on every `digitalocean_droplet` ([digitalocean_ssh_key](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/ssh_key)).
- Port 22 is open only from a VPN/office CIDR or a bastion tag in the `mgmt` firewall; prefer the console or DOKS/App Platform (no SSH at all).
- Rotate a key by adding the new one, rebuilding or re-provisioning, then deleting the old one; DigitalOcean only injects keys at creation.

## Firewalls: default deny

Cloud firewalls block everything without an allow rule ([firewalls](https://docs.digitalocean.com/products/networking/firewalls/)). Every Droplet must be behind at least one firewall, attached by tag ([organisation](https://docs.digitalocean.com/products/networking/firewalls/concepts/organization/)):

- Inbound `0.0.0.0/0` only for 80/443 on Droplets that are themselves public entry points; behind a load balancer, allow only the load balancer.
- Inbound sources by tag or load balancer UID, not by IP, so scaling does not open holes.
- Outbound: allow what the workload needs (443, DNS, the database port to the DB tag). Leave outbound open only for build hosts.
- DOKS clusters have their own control-plane firewall for API access; restrict it to CI and office ranges ([features](https://docs.digitalocean.com/products/kubernetes/details/features/)).
- Review a Droplet's effective rules with `doctl compute firewall list-by-droplet <id>` ([doctl firewall](https://docs.digitalocean.com/reference/doctl/reference/compute/firewall/)).

## Database trusted sources

Managed databases accept connections only from their trusted sources list, which can hold Droplets, DOKS clusters, Apps, tags and CIDRs, up to 100 rules ([secure a cluster](https://docs.digitalocean.com/products/databases/postgresql/how-to/secure/)). Rules:

- Trusted sources are tags (`<env>-app`, a DOKS cluster ID), not developer laptops. Humans reach the DB through a bastion or `doctl databases` commands.
- Connect over the VPC private hostname only ([connect](https://docs.digitalocean.com/products/databases/postgresql/how-to/connect/)); the public hostname is a leftover from the console, not an endpoint applications use.
- Require TLS with `sslmode=verify-full` and the cluster CA.
- Per-application users with minimal grants; the `doadmin` credential stays in agenix for migrations only.
- In Terraform: `digitalocean_database_firewall` next to every `digitalocean_database_cluster` ([digitalocean_database_firewall](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/database_firewall)).

## Spaces access keys

- Keys are created in the control panel (not via API or CLI) and are account-wide resources ([manage access](https://docs.digitalocean.com/products/spaces/how-to/manage-access/)).
- Use **limited** keys with per-bucket **Read** or **Read/Write/Delete**; a full-access key can create and reconfigure any bucket and belongs only in agenix for the state bootstrap.
- One key per application or pipeline; rotating one does not affect the others. The 200-key limit is generous enough ([limits](https://docs.digitalocean.com/products/spaces/details/limits/)).
- Per-bucket keys are incompatible with S3 bucket policies; if a bucket needs a policy, control access with the policy and a full key instead, and document why.
- The Terraform state key pair lives in agenix as `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (the names the S3 backend reads) ([Spaces backend](https://docs.digitalocean.com/products/spaces/reference/terraform-backend/)); the provider's own Spaces operations read `SPACES_ACCESS_KEY_ID` / `SPACES_SECRET_ACCESS_KEY` ([provider docs](https://github.com/digitalocean/terraform-provider-digitalocean/blob/main/docs/index.md)).

## Audit: security history

**Settings → Security** shows the team's security history: each action, the user, the source IP and the time, including token and resource creation and deletion ([view security history](https://docs.digitalocean.com/platform/teams/how-to/view-security-history/)). Personal logins are on the account's Activity tab. Older history requires a support request, so export what you need after an incident.

Check it when: a token is suspected leaked (look for actions from unknown IPs, then revoke on the Tokens page), after off-boarding, and as part of any change review that touched IAM-like resources (tokens, SSH keys, team members).

## Leak response

1. Revoke the token on **Account → API → Tokens** (or `doctl auth remove --context` on the client), and the Spaces key on the Spaces keys page.
2. Read the security history for the token's lifetime; list Droplets, firewalls, SSH keys and tokens created in that window.
3. Rotate secrets the token could read (database credentials if `database:view_credentials`, kubeconfigs if `kubernetes:access_cluster`).
4. Re-issue a narrower token and record the incident. Prefer the platform `secret-rekey` flow in the [secrets skill](../../secrets/SKILL.md) for the agenix side.
