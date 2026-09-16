# Azure automated onboarding

From the Git project root inside the generated project shell:

```sh
cloud-onboard-azure --tenant-id TENANT_UUID --subscription-id SUBSCRIPTION_UUID --environment production
```

Replace example scope values. Use existing read-only credentials. Run
`cloud-onboard-azure --help` for the exact argument contract.
The same arguments work with `just onboard azure ...` inside the shell
or `nix run github:olafkfreund/cloud-projects-templates#onboard-azure -- ...`
from a Git root. The flake app does not decrypt agenix secrets automatically.

## Coverage and permissions

Use `az graph query` with explicit subscription, stable ID ordering,
selected projections and skip tokens for resource ID/type/location/group and
tag-presence inventory. For supported records, use scoped read commands:
`az vm show`, `az network nsg show`, and `az storage account show`; retrieve no
VM instance-view extensions or deployment outputs. Fields: VM disk/resource
relationships; NSG direction/access/protocol/port ranges/source prefixes;
storage HTTPS-only, minimum TLS, public-blob setting. Fail the storage baseline
when HTTPS-only is false, minimum TLS is older than 1.2, or public blob access is
allowed. Flag inbound Allow TCP 22/3389 from any IPv4/IPv6 source, including
ranges and wildcard protocols, as an exposed rule, not proven reachability.
VM presence alone does not prove encryption/backup adequacy. Optional
`az advisor recommendation list` retains ID/category/impact only as native
review items. Permissions: resource/subscription reads, Resource Graph access,
`Microsoft.Compute/virtualMachines/read`,
`Microsoft.Network/networkSecurityGroups/read`,
`Microsoft.Storage/storageAccounts/read`; optional
`Microsoft.Advisor/recommendations/read`. Reader is a suggested existing role,
not something the collector grants. Record Graph visibility and indexing limits.


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

Official reference: [provider documentation](https://learn.microsoft.com/en-us/azure/governance/resource-graph/overview).
