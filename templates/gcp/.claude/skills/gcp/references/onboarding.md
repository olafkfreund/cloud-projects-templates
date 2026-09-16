# GCP automated onboarding

From the Git project root inside the generated project shell:

```sh
cloud-onboard-gcp --project-id my-project --expected-principal reader@example.com --environment production
```

Replace example scope values. Use existing read-only credentials. Run
`cloud-onboard-gcp --help` for the exact argument contract.
The same arguments work with `just onboard gcp ...` inside the shell
or `nix run github:olafkfreund/cloud-projects-templates#onboard-gcp -- ...`
from a Git root. The flake app does not decrypt agenix secrets automatically.

## Coverage and permissions

Use `gcloud asset search-all-resources` with project scope and selected
read mask for name/type/location; `gcloud compute instances list`,
`gcloud compute disks list`, `gcloud compute firewall-rules list`, and
`gcloud storage buckets list` with selected JSON fields, explicit project and
principal. Fetch bucket details through `gcloud storage buckets describe` only
when required fields are missing from list results. Fields: instance/disk
relationships, external-IP presence (no address persistence), firewall
direction/disabled/action/protocol/ports/source ranges, bucket public-access
prevention, uniform bucket-level access and versioning. Fail active INGRESS
allow rules covering world-open TCP 22/3389 and explicit uniform-access=false;
public-access prevention `enforced` passes, inherited/unspecified requires
manual review of organization policy. Versioning disabled requires manual
review, not universal failure. External IP is exposure evidence, not a failure
on its own. Do not flag provider-managed disk encryption as missing merely
because CMEK is absent. Permissions: `resourcemanager.projects.get`,
`cloudasset.assets.searchAllResources`, `compute.instances.list`,
`compute.disks.list`, `compute.firewalls.list`, `storage.buckets.list/get`.
SCC and Recommender integration are unsupported in this first collector, with
manual review retained; no API activation or IAM-policy dump.


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

Official reference: [provider documentation](https://cloud.google.com/asset-inventory/docs/search-resources).
