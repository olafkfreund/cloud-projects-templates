# Hetzner automated onboarding

From the Git project root inside the generated project shell:

```sh
secret-run --only HCLOUD_TOKEN -- cloud-onboard-hetzner --project-label production --acknowledge-project-token --environment production
```

Replace example scope values. Use existing read-only credentials. Run
`cloud-onboard-hetzner --help` for the exact argument contract.
The same arguments work with `just onboard hetzner ...` inside the shell
or `nix run github:olafkfreund/cloud-projects-templates#onboard-hetzner -- ...`
from a Git root. The flake app does not decrypt agenix secrets automatically.

## Coverage and permissions

Use stdlib HTTPS GET at `https://api.hetzner.cloud/v1` for
`/servers`, `/volumes`, `/networks`, `/firewalls`, `/load_balancers`, and optional
`/servers/{sentinel}`. Require the existing project Read token in `HCLOUD_TOKEN`.
Follow `meta.pagination.next_page`; keep only IDs, status, location, attachment
relationships, backup-window presence, protection flags, selected ingress
rules and load-balancer target-health booleans. World-open inbound TCP 22/3389
fails the rule baseline. Missing backups or delete protection requires manual
review because stateless/reprovisionable servers are legitimate. Unhealthy LB
targets require review of a point-in-time observation. Do not infer host firewall
absence from missing cloud firewall associations. Label-selector associations are reported unknown for manual review; explicit
server firewall IDs are retained. Object Storage, Robot, Storage Boxes and account
audit/token policy are explicitly unsupported.


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

Official reference: [provider documentation](https://docs.hetzner.cloud/reference/cloud).
