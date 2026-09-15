# OCI best practices (well-architected) framework

Source: [Well-Architected Framework for Oracle Cloud Infrastructure](https://docs.oracle.com/en/solutions/oci-best-practices/) (verified 2026-09-15). Oracle names five pillars: **Security and Compliance**, **Reliability and Resilience**, **Performance and Cost Optimization**, **Operational Efficiency**, and **Distributed Cloud**. Use the checks below as review gates; each links the Oracle page that justifies it.

## 1. Security and compliance

- [ ] **Root compartment empty; one compartment per function.** Isolation, quotas and Security Zones are compartment-scoped. [Tenancy setup](https://docs.oracle.com/en-us/iaas/Content/GSG/Concepts/settinguptenancy.htm)
- [ ] **Administrators group has a minimal, MFA-enforced membership.** Add `where request.user.mfaTotpVerified='true'` to privileged policies. [MFA](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/usingmfa.htm)
- [ ] **Policies use the lowest verb that works** and name a compartment. [Policy verbs](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/policyreference.htm)
- [ ] **No API keys where a principal works.** Instance principals, resource principals, OKE workload identity for workloads; security tokens for humans. Users are capped at three API keys, so rotate rather than accumulate. [Managing credentials](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingcredentials.htm)
- [ ] **Cloud Guard enabled at tenancy level** with Oracle-managed detector and responder recipes; alerts wired to Notifications. [Cloud Guard](https://docs.oracle.com/en-us/iaas/cloud-guard/using/index.htm)
- [ ] **Security Zones (Maximum Security Recipe) on regulated compartments**: forbids public buckets, public IPs, Oracle-managed keys, moving resources out. [Security Zones](https://docs.oracle.com/en-us/iaas/security-zone/using/security-zones.htm)
- [ ] **Customer-managed keys in Vault** for buckets, volumes and databases that hold regulated data; HSM-protected keys where required; rotation scheduled. [Vault](https://docs.oracle.com/en-us/iaas/Content/KeyManagement/Concepts/keyoverview.htm)
- [ ] **NSGs between tiers, security lists only for the subnet baseline**; no `0.0.0.0/0` on SSH/RDP. [NSGs](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/networksecuritygroups.htm)
- [ ] **Audit logs exported** beyond the fixed 365-day retention via Connector Hub to a locked bucket. [Audit retention](https://docs.oracle.com/en-us/iaas/Content/Audit/Tasks/settingretentionperiod.htm), [Logging](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/loggingoverview.htm)
- [ ] **Per-service hardening applied** from the Security Best Practices index (Compute, Object Storage, OKE, Database, ...). [Index](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/configuration_security.htm), [Security checklist](https://docs.oracle.com/en/solutions/oci-security-checklist)

## 2. Reliability and resilience

- [ ] **Spread across fault domains** (and availability domains in multi-AD regions); Cloud Advisor flags single-node deployments. [Cloud Advisor](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Concepts/cloudadvisoroverview.htm)
- [ ] **Compartment quotas** prevent one team from exhausting shared service limits. [Compartment quotas](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/resourcequotas.htm)
- [ ] **DRG as the single hub** for VCN, on-premises (FastConnect/IPSec) and cross-region (RPC) attachments; explicit DRG route tables. [DRG](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/managingDRGs.htm)
- [ ] **Automatic backups** on block volumes, Object Storage versioning, and Autonomous Database automatic backups turned on (Security Zones can enforce this). [Security Zones](https://docs.oracle.com/en-us/iaas/security-zone/using/security-zones.htm)
- [ ] **OKE clusters stay on supported Kubernetes versions**; scale large clusters in ~10 % batches. [Large cluster best practices](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengbestpractices_topic-Large-Scale-Clusters-best-practices.htm)
- [ ] **State and configuration are recoverable**: remote state with versioning, Resource Manager rollback jobs or tagged plan artifacts. [Resource Manager](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/resourcemanager.htm)
- [ ] **DR designed per workload** using the resilience guidance in the framework; cross-region replication for Object Storage and databases where RPO demands it. [Framework](https://docs.oracle.com/en/solutions/oci-best-practices/)

## 3. Performance and cost optimization

- [ ] **Budgets on every top-level compartment or cost-tracking tag** with forecast alerts. [Budgets](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm)
- [ ] **Defined tags for cost attribution** (`Ops.CostCenter`, `Ops.Owner`, `Ops.Env`) applied via tag defaults so Cost Analysis can slice by them. [Tagging](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/taggingoverview.htm)
- [ ] **Cloud Advisor cost recommendations reviewed**: underutilized instances, unattached volumes, buckets without lifecycle rules. [Cloud Advisor](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Concepts/cloudadvisoroverview.htm)
- [ ] **Flexible shapes sized from metrics**, not guesses; block volume autotune on. [Cloud Advisor performance](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Concepts/cloudadvisoroverview.htm)
- [ ] **`infracost breakdown` in every PR** so cost deltas are visible before apply (project convention).
- [ ] **Object Storage lifecycle policies** move cold data to Infrequent Access/Archive. [Cloud Advisor](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Concepts/cloudadvisoroverview.htm)
- [ ] **Service gateway** for Oracle service traffic instead of NAT egress. [Vault networking note](https://docs.oracle.com/en-us/iaas/Content/KeyManagement/Concepts/keyoverview.htm)

## 4. Operational efficiency

- [ ] **Everything as code**, applied through Terraform or Resource Manager stacks; no console-created production resources. [Resource Manager](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/resourcemanager.htm)
- [ ] **Drift detection** runs on a schedule (Resource Manager) or `terraform plan -detailed-exitcode` in CI with a read-only principal.
- [ ] **Log groups per compartment**; service logs (VCN flow, LB, Object Storage) enabled; custom logs via the Unified Monitoring Agent. [Logging](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/loggingoverview.htm)
- [ ] **Events + Notifications** on security-relevant changes (policy, IAM, Vault key events). [Cloud Guard integration](https://docs.oracle.com/en-us/iaas/cloud-guard/using/index.htm)
- [ ] **CIS compliance report** (`cis_reports.py`) run at least monthly against the tenancy. [CIS quickstart](https://github.com/oci-landing-zones/oci-cis-landingzone-quickstart)
- [ ] **Naming and tag conventions documented** in the repo and enforced by tag defaults plus `tflint`.
- [ ] **Runbooks reference OCIDs by tag query**, not by hand-copied IDs (see [cli-cheatsheet.md](cli-cheatsheet.md)).

## 5. Distributed cloud

Oracle's fifth pillar covers public regions, Dedicated Region, Cloud@Customer, edge and multicloud, under three strategies: design, integrate, optimize. [Distributed cloud strategies](https://docs.oracle.com/en/solutions/oci-best-practices/effective-strategies-distributed-cloud-implementation1.html)

- [ ] **Placement decided by data residency and latency**, documented per workload.
- [ ] **One landing zone pattern across regions/realms**; the Core Landing Zone is region-agnostic. [Landing zones](https://docs.oracle.com/en/solutions/oci-best-practices/simplify-provisioning-oci-landing-zones1.html)
- [ ] **IAM is home-region authoritative**; do not assume immediate propagation of policy changes to other regions. [IAM overview](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/overview.htm)
- [ ] **Cross-region connectivity via DRG remote peering**, with explicit route distributions. [DRG](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/managingDRGs.htm)
- [ ] **Unified observability**: logs and metrics from all regions land in one monitoring compartment.
