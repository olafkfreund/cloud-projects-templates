# OCI automated onboarding

From the Git project root inside the generated project shell:

```sh
cloud-onboard-oci --tenancy-id ocid1.tenancy.oc1..EXAMPLE --compartment-ids ocid1.compartment.oc1..EXAMPLE --regions eu-frankfurt-1 --profile audit --environment production
```

Replace example scope values. Use existing read-only credentials. Run
`cloud-onboard-oci --help` for the exact argument contract.
The same arguments work with `just onboard oci ...` inside the shell
or `nix run github:olafkfreund/cloud-projects-templates#onboard-oci -- ...`
from a Git root. The flake app does not decrypt agenix secrets automatically.

## Coverage and permissions

Use `oci iam tenancy get`, `oci iam compartment get`,
`oci search resource structured-search`, `oci compute instance list`,
`oci bv volume list`, `oci network vcn list`, `oci network security-list list`,
`oci network nsg list`, `oci network nsg rules list`,
`oci os ns get`, `oci os bucket list/get`, all with explicit profile, tenancy
where accepted, region and compartment. Escape/validate OCIDs before inserting
them into structured query text. Search supplies bounded overview; the selected
service lists supply check evidence. Fields: resource IDs/relationships, ingress
source/protocol/port ranges, bucket public-access type and versioning. Fail
world-open TCP 22/3389 ingress and non-private bucket public-access type under
this private-storage baseline. Versioning disabled/suspended requires review;
provider-managed encryption is not absence of encryption. Permissions: read
tenancy/compartment metadata, inspect supported resource families, and the read
permissions needed for security rules and bucket details; document policy
resource families `instances`, `volumes`, `vcns`, `security-lists`,
`network-security-groups`, `objectstorage-namespaces`, `buckets`, scoped to
selected compartments where possible. `NotAuthorizedOrNotFound` is unknown.
Cloud Advisor/Cloud Guard ingestion is deferred and listed as unsupported.


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

Official reference: [provider documentation](https://docs.oracle.com/en-us/iaas/Content/Search/Concepts/queryoverview.htm).
