# Cloudflare automated onboarding

From the Git project root inside the generated project shell:

```sh
secret-run --only CLOUDFLARE_READ_TOKEN -- cloud-onboard-cloudflare --account-id ACCOUNT_ID --zone-ids ZONE_ID --environment production
```

Replace example scope values. Use existing read-only credentials. Run
`cloud-onboard-cloudflare --help` for the exact argument contract.
The same arguments work with `just onboard cloudflare ...` inside the shell
or `nix run github:olafkfreund/cloud-projects-templates#onboard-cloudflare -- ...`
from a Git root. The flake app does not decrypt agenix secrets automatically.

## Coverage and permissions

Use stdlib HTTPS GET to `/client/v4/accounts/{id}`,
`/zones/{id}`, `/zones/{id}/dns_records`, and individual zone settings
`ssl`, `min_tls_version`, `always_use_https`; explicitly selected zones only.
Keep DNS ID/type/proxiable/proxied booleans, no names/content; settings retain
only ID/value. `ssl=strict` passes this baseline; off/flexible/full fail the
strict origin-verification baseline. TLS below 1.2 and Always Use HTTPS off
fail these bounded transport checks. DNS-only records require workload review,
not failure. Optional `/accounts/{id}/security-center/insights` retains issue
ID/type/severity/status/time only as native findings needing review. Follow its
documented page metadata separately from DNS pagination. Permissions: Account
Settings Read, Zone Read, DNS Read, Zone Settings Read, and Security Center read
when explicitly requested. Feature/plan unavailability produces unknown, never
activation. Verify token types through actual scope reads; do not require a
user-token-only verification endpoint for account-owned tokens.


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

Official reference: [provider documentation](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/).
