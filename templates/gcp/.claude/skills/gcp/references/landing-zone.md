# Landing zone design on Google Cloud

Verified 2026-09-15. Primary sources:
[Landing zone design](https://docs.cloud.google.com/architecture/landing-zones),
[Enterprise foundations blueprint](https://docs.cloud.google.com/architecture/security-foundations),
[Best practices for enterprise organizations](https://docs.cloud.google.com/docs/enterprise/best-practices-for-enterprise-organizations).

A landing zone is the org-level scaffolding (identity, hierarchy, network,
logging, guardrails) that every project inherits. Build it once, in code,
before the first workload. Retrofitting org policy onto live projects is
the expensive path.

## Resource hierarchy

[Resource hierarchy](https://docs.cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy),
[Folders](https://docs.cloud.google.com/resource-manager/docs/creating-managing-folders)

```
Organization (example.com)
├── fldr-bootstrap        # seed project: state buckets, CI service accounts
├── fldr-common           # logging, billing export, monitoring, DNS hub, interconnect
├── fldr-network          # Shared VPC host projects (prod, nonprod)
├── fldr-production
│   └── prj-p-<team>-<app>
├── fldr-nonproduction
│   └── prj-n-<team>-<app>
└── fldr-development
    └── prj-d-<team>-<app>
```

Rules:

- IAM and org policy inherit downward; grant at the highest level that is
  still least privilege, and never grant at org level for a single project's
  need.
- Folders model environments and business units, not teams' org charts;
  charts change more often than environments.
- One project per environment per workload. Projects are the blast-radius,
  quota and billing unit.
- Naming: `prj-<env>-<bu>-<app>`, `fldr-<purpose>`, `vpc-<env>-shared`,
  consistent and lowercase, matching the blueprint conventions.

## Enterprise foundations blueprint

[Blueprint guide](https://docs.cloud.google.com/architecture/security-foundations),
[terraform-example-foundation](https://github.com/terraform-google-modules/terraform-example-foundation)

The blueprint is Google's opinionated, Terraform-implemented landing zone.
Its stages, which map to state files and CI pipelines:

| Stage | Creates |
|-------|---------|
| 0-bootstrap | seed project, state buckets, CI SAs, org-level IAM |
| 1-org | folders, org policies, logging, SCC, billing export |
| 2-environments | per-environment folders and monitoring projects |
| 3-networks | Shared VPC hubs, firewall policies, Private Google Access, DNS |
| 4-projects | project factory for workload projects |
| 5-app-infra | workload infrastructure |

Adopt it as-is where possible. Deviate deliberately and document why.

## Alternative: Cloud Foundation Fabric / FAST

[cloud-foundation-fabric](https://github.com/GoogleCloudPlatform/cloud-foundation-fabric),
[FAST](https://github.com/GoogleCloudPlatform/cloud-foundation-fabric/tree/master/fast)

FAST is the Fabric team's staged landing zone (bootstrap, resman, networking,
security, project factory). Prefer it when you want thinner, composable
modules and faster iteration; prefer the enterprise foundations blueprint
when you want a compliance-mapped reference. Do not mix both in one org.

Cloud Foundation Toolkit modules for individual pieces
([Blueprints index](https://docs.cloud.google.com/docs/terraform/blueprints/terraform-blueprints)):

- [terraform-google-project-factory](https://github.com/terraform-google-modules/terraform-google-project-factory)
- [terraform-google-network](https://github.com/terraform-google-modules/terraform-google-network)

## Shared VPC

[Shared VPC](https://docs.cloud.google.com/vpc/docs/shared-vpc),
[VPC design best practices](https://docs.cloud.google.com/architecture/best-practices-vpc-design)

- One host project per environment (`prj-p-shared-vpc`, `prj-n-shared-vpc`)
  under `fldr-network`; workload projects attach as service projects.
- Central network team owns subnets, routes, firewall, NAT and DNS. Workload
  teams get `roles/compute.networkUser` on specific subnets only.
- Hierarchical firewall policies at folder level for org-wide rules
  (deny all ingress, allow IAP/health-check ranges); project rules for the
  rest ([Firewall policies](https://docs.cloud.google.com/vpc/docs/using-firewall-policies)).
- Private Google Access on every subnet, Cloud NAT for egress, no external
  IPs (`compute.vmExternalIpAccess` denied)
  ([Private Google Access](https://docs.cloud.google.com/vpc/docs/private-google-access)).
- Plan non-overlapping CIDR ranges across environments and on-prem up front;
  re-IPing later is a migration.

## Centralized logging

[Central log storage](https://docs.cloud.google.com/logging/docs/central-log-storage),
[Aggregated sinks](https://docs.cloud.google.com/logging/docs/export/aggregated_sinks),
[Log buckets](https://docs.cloud.google.com/logging/docs/buckets)

- Org-level aggregated sink with `include_children = true` routing to a log
  bucket in `prj-c-logging`; a second sink to BigQuery for analysis and a
  third to Cloud Storage for long-term retention where required.
- Enable Data Access audit logs org-wide for IAM, Storage, BigQuery and
  Secret Manager at minimum ([Audit logs](https://docs.cloud.google.com/logging/docs/audit)).
- Lock the retention on the central bucket; the logging project must be
  writable only by the sink's writer identity.
- Route Security Command Center findings to the same place
  ([SCC](https://docs.cloud.google.com/security-command-center/docs/security-command-center-overview)).

## Organization policy constraints

[Overview](https://docs.cloud.google.com/resource-manager/docs/organization-policy/overview),
[All constraints](https://docs.cloud.google.com/resource-manager/docs/organization-policy/org-policy-constraints)

Set these at org level in stage 1 and exempt per folder only with a ticket:

| Constraint | Why |
|------------|-----|
| `iam.allowedPolicyMemberDomains` | stop grants to personal Gmail and foreign orgs ([Domain restriction](https://docs.cloud.google.com/resource-manager/docs/organization-policy/restricting-domains)) |
| `iam.disableServiceAccountKeyCreation` | no downloadable long-lived credentials ([Restrict SAs](https://docs.cloud.google.com/resource-manager/docs/organization-policy/restricting-service-accounts)) |
| `iam.disableServiceAccountKeyUpload` | same, for uploaded keys |
| `iam.automaticIamGrantsForDefaultServiceAccounts` | default SAs stop getting Editor |
| `compute.vmExternalIpAccess` | no public VMs |
| `compute.skipDefaultNetworkCreation` | no `default` network with open firewall |
| `compute.requireOsLogin` | SSH via IAM, not metadata keys |
| `compute.restrictVpcPeering` | peering only to approved networks |
| `storage.publicAccessPrevention` | no public buckets |
| `storage.uniformBucketLevelAccess` | no per-object ACLs |
| `gcp.resourceLocations` | data residency ([Locations](https://docs.cloud.google.com/resource-manager/docs/organization-policy/defining-locations)) |
| `sql.restrictPublicIp` | Cloud SQL private only |

Audit what is in force before designing:

```sh
gcloud resource-manager org-policies list --organization=ORG_ID
gcloud resource-manager org-policies list --project=PROJECT_ID
```

## Identity

[Federating identities](https://docs.cloud.google.com/architecture/identity/best-practices-for-federating),
[Workforce Identity Federation](https://docs.cloud.google.com/iam/docs/workforce-identity-federation)

- Federate Cloud Identity with the corporate IdP; no local passwords.
- Grant IAM to Google Groups, never to individual users
  ([Groups](https://docs.cloud.google.com/iam/docs/groups-in-cloud-console)).
- Break-glass accounts with hardware keys, monitored by an alert on their
  login.

## Landing-zone review checklist

- [ ] Hierarchy in code, no manually created folders or projects.
- [ ] Org policies above applied and listed in the repo.
- [ ] Shared VPC host projects exist; no workload project owns a VPC.
- [ ] Org-level log sink writes to a locked central bucket.
- [ ] Billing export to BigQuery enabled ([Billing export](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery)).
- [ ] Security Command Center enabled at org level.
- [ ] Cloud Asset Inventory feed for change tracking ([Asset Inventory](https://docs.cloud.google.com/asset-inventory/docs/overview)).
- [ ] Project factory is the only path that creates projects.
