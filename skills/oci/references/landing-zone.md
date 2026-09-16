# CIS OCI Landing Zone

Verified 2026-09-15. Do not hand-roll a tenancy foundation; deploy the Oracle-maintained landing zone and build workloads inside it.

## Which repo

| Repo | Status | Use |
|------|--------|-----|
| [terraform-oci-core-landingzone](https://github.com/oci-landing-zones/terraform-oci-core-landingzone) | Current | Centralized, CIS OCI Foundations Benchmark v3.0-aligned foundation. Start here. |
| [oci-landing-zone-operating-entities](https://github.com/oci-landing-zones/oci-landing-zone-operating-entities) | Current | Blueprints for multi-entity organizations |
| [terraform-oci-modules-networking](https://github.com/oci-landing-zones/terraform-oci-modules-networking), [-observability](https://github.com/oci-landing-zones/terraform-oci-modules-observability), [-workloads](https://github.com/oci-landing-zones/terraform-oci-modules-workloads), [-orchestrator](https://github.com/oci-landing-zones/terraform-oci-modules-orchestrator) | Current | Building blocks the landing zone is composed of; reuse them for workloads |
| [oci-cis-landingzone-quickstart](https://github.com/oci-landing-zones/oci-cis-landingzone-quickstart) | Retired May 2025 | Keep only for `scripts/cis_reports.py` (CIS-certified compliance checker) |

Org index: [github.com/oci-landing-zones](https://github.com/oci-landing-zones).

## Compartment design

The Core Landing Zone creates a functional hierarchy; mirror it even if you deploy by hand:

```
tenancy (root, empty)
└── <enclosing>            optional, one per environment or business unit
    ├── network            VCNs, DRG, gateways, firewalls
    ├── security           Vault, Cloud Guard target, Bastion, logging buckets
    ├── appdev             compute, OKE, functions, load balancers
    ├── database           DB systems, Autonomous Database
    └── exainfra           optional, Exadata infrastructure
```

Rules (from [Tenancy setup best practices](https://docs.oracle.com/en-us/iaas/Content/GSG/Concepts/settinguptenancy.htm) and the landing zone):
- Max depth is 6 below root; keep to 3.
- One admin group per compartment (`<env>-network-admins`, `<env>-security-admins`, ...) with `manage` scoped to that compartment only.
- Cross-compartment needs are expressed as narrow `use`/`read` grants, e.g. app admins `use virtual-network-family in compartment network`.
- Workload compartments get [compartment quotas](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/resourcequotas.htm) so one team cannot exhaust regional limits.
- Use tag defaults on each compartment so `Ops.Env`, `Ops.Owner`, `Ops.CostCenter` are applied automatically. [Tag defaults](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagdefaults.htm)

## Network: hub and spoke on a DRG

The Core Landing Zone supports up to 10 VCNs: three-tier, OKE and Exadata spokes plus one hub VCN. Design points, from the [landing zone README](https://github.com/oci-landing-zones/terraform-oci-core-landingzone) and [DRG docs](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/managingDRGs.htm):

- **One DRG per region is the hub.** Attach every spoke VCN, on-premises (FastConnect virtual circuit or IPSec tunnel) and remote regions (RPC) to it. A VCN can attach to only one DRG.
- **Explicit DRG route tables and import route distributions.** Default tables allow everything attached to reach everything; create separate tables for spokes vs. on-prem attachments to control transit.
- **Hub VCN hosts inspection**: OCI Network Firewall or a third-party appliance; the landing zone can route spoke-to-spoke and north-south traffic through it.
- **Three-tier spoke layout**: public LB subnet (only public subnet), private app subnet, private DB subnet. Egress via NAT gateway; Oracle services via service gateway.
- **OKE spokes**: private API endpoint subnet, private worker subnet, pod subnet (VCN-native CNI), LB subnet. Size CIDRs for growth up front. [OKE security best practices](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengbestpractices_topic-Security-best-practices.htm)
- **NSGs for tier rules, security lists for the subnet baseline.** NSGs can reference other NSGs, decoupling security from subnet layout. [NSGs](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/networksecuritygroups.htm)
- **Bastion service, not a jump host with a public IP**, for SSH into private subnets. [Landing zone README](https://github.com/oci-landing-zones/terraform-oci-core-landingzone)
- **VCN flow logs on** for every subnet that carries production traffic. [Logging](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/loggingoverview.htm)

## Cloud Guard

[Cloud Guard docs](https://docs.oracle.com/en-us/iaas/cloud-guard/using/index.htm)

- Enable once per tenancy in the home region; the target is the root or enclosing compartment so all children are covered.
- Use Oracle-managed configuration, activity and threat detector recipes; clone to user-managed recipes only to tune noise, never to disable detectors silently.
- Responder recipes: start in "suggest" mode, promote to automatic only for reversible actions (e.g. make bucket private).
- Route problems to Notifications via Events so a human sees critical findings; the landing zone wires this by default.
- Cloud Guard is a prerequisite for Security Zones.

## Security Zones

[Security Zones docs](https://docs.oracle.com/en-us/iaas/security-zone/using/security-zones.htm)

- Attach the **Maximum Security Recipe** to the `database` and `security` compartments (and `appdev` where feasible). It denies, at API level: public buckets, public IPs, Oracle-managed keys, moving resources out of the zone, resources without automatic backups.
- Subcompartments inherit the zone. Create a custom recipe only when a specific policy blocks a documented requirement; record the exception in the repo.
- Test in a sandbox compartment first: existing non-compliant resources are surfaced by Cloud Guard, new ones are rejected.

## Vault and keys

[Vault docs](https://docs.oracle.com/en-us/iaas/Content/KeyManagement/Concepts/keyoverview.htm)

- One vault in the `security` compartment per environment. Virtual private vault only if you need backup, auto-rotation or a dedicated HSM partition; the default vault is cheaper.
- Master encryption keys: HSM-protected for regulated data, software-protected elsewhere. Reference them by OCID in `kms_key_id` on buckets, volumes, databases and the state backend.
- Grant `use keys` to the service dynamic groups (e.g. `Allow service objectstorage-<region> to use keys in compartment security`), `manage keys` only to security admins.
- Runtime secrets (DB passwords, API tokens) go in Vault secrets, not in state or env files. Developer-side secrets stay in agenix.
- Enable Events on key rotation/deletion and alert; schedule rotation (60-365 days) where supported.

## Logging, audit and evidence

- Audit logs: 365-day fixed retention; export with [Connector Hub](https://docs.oracle.com/en-us/iaas/Content/connector-hub/home.htm) to a versioned, retention-locked bucket in `security`. [Audit](https://docs.oracle.com/en-us/iaas/Content/Audit/Concepts/auditoverview.htm), [Retention](https://docs.oracle.com/en-us/iaas/Content/Audit/Tasks/settingretentionperiod.htm)
- One log group per compartment; enable service logs for Object Storage, load balancers, functions, API gateway and VCN flow logs. [Logging](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/loggingoverview.htm)
- Notifications topic per environment for IAM/policy/Vault change events.
- Optional CIS assessment: review and pin the Oracle script and its read permissions first. Keep reports private and local; publishing or scheduling is separate work:

```
# Uses an existing read-only CLI profile; secret-run is not needed.
python3 cis_reports.py --profile ro-agent --report-directory ./reports/oci-cis
```
(Script: [oci-cis-landingzone-quickstart/scripts](https://github.com/oci-landing-zones/oci-cis-landingzone-quickstart); supports config-file, security-token and instance-principal auth.)

## OCI security checklist (condensed)

Derived from [Learn About Security in OCI](https://docs.oracle.com/en/solutions/oci-security-checklist), [Securing your tenancy](https://docs.oracle.com/en-us/iaas/Content/Security/Tasks/securing_your_tenancy.htm) and the [service security index](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/configuration_security.htm):

- [ ] Root compartment empty; Administrators group minimal, MFA enforced
- [ ] Federated identity domain for humans; no shared local users
- [ ] Policies least-privilege, compartment-scoped, reviewed quarterly
- [ ] API keys rotated, never more than needed (max 3 per user); prefer tokens/principals
- [ ] Cloud Guard enabled tenancy-wide, findings routed to Notifications
- [ ] Security Zones on data compartments
- [ ] Customer-managed keys for regulated data; key rotation scheduled
- [ ] No public buckets; Object Storage versioning on state and evidence buckets
- [ ] No public IPs on compute except LB/bastion; NSGs restrict tier traffic
- [ ] Audit and service logs exported and retained per policy
- [ ] Budgets and quotas on every workload compartment
- [ ] CIS report run and gaps tracked as issues
