# DigitalOcean automated onboarding

From the Git project root inside the generated project shell:

```sh
secret-run --only DIGITALOCEAN_READ_TOKEN -- cloud-onboard-digitalocean --account-uuid ACCOUNT_UUID --project-id PROJECT_UUID --environment production
```

Replace example scope values. Use existing read-only credentials. Run
`cloud-onboard-digitalocean --help` for the exact argument contract.
The same arguments work with `just onboard digitalocean ...` inside the shell
or `nix run github:olafkfreund/cloud-projects-templates#onboard-digitalocean -- ...`
from a Git root. The flake app does not decrypt agenix secrets automatically.

## Coverage and permissions

Use stdlib HTTPS GET at `https://api.digitalocean.com/v2` for
`/account`, `/projects/{id}`, `/projects/{id}/resources`; fetch selected project
Droplets, volumes and load balancers by their typed URNs using their GET routes.
Reject unknown URN types as unsupported, do not treat arbitrary URNs as paths.
GET `/droplets/{id}/firewalls` for selected Droplets; do not enumerate unrelated
team resources to repair missing project scope. Fields: resource ID/region,
project membership, Droplet backup feature and attachment IDs, firewall inbound
sources/protocol/ports, load-balancer forwarding TLS/redirect booleans. Fail
world-open TCP 22/3389 firewall rules; absent backups, missing cloud firewall or
HTTP-only forwarding requires manual review. No database users, app specs,
kubeconfigs or Spaces credentials. Permissions: `account:read`, `project:read`,
`droplet:read`, `block_storage:read`, `load_balancer:read`, `firewall:read` as
applicable. Follow validated `links.pages.next`; record that token scopes can
silently hide project resources. Unsupported URNs remain explicit inventory
stubs without configuration conclusions. Spaces and managed databases are
unsupported for configuration assessment in this release.


## Reports

Reports use [schema version 2](../../cloud-onboarding/references/report-format.md)
and preserve earlier runs. Exit 0 means supported collection completed, even
when findings fail; 2 means a partial report; 1 means invocation, identity or
output failure. Denied reads, missing fields and truncated lists are never
passes. The environment labels the report, not a resource filter.

The collector is a bounded baseline, not complete inventory or compliance
certification. Keep reports private and ignored. Workload recovery, IAM, cost,
resilience and governance always retain manual review. No cloud mutation or
service activation is performed.

Official reference: [provider documentation](https://docs.digitalocean.com/products/networking/firewalls/how-to/configure-rules/).
