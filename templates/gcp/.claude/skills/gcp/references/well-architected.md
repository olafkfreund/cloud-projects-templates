# Google Cloud Well-Architected Framework: review checklist

Source: [Well-Architected Framework](https://docs.cloud.google.com/architecture/framework)
(the old `cloud.google.com/architecture/framework` URL redirects here).
Verified 2026-09-15. Use this as a PR review checklist: tick each item or
write down why it does not apply.

## 1. Operational excellence

[Pillar](https://docs.cloud.google.com/architecture/framework/operational-excellence)

- [ ] SLOs are defined per user-facing service and backed by Cloud Monitoring
      SLO objects, so alerts fire on burn rate, not on raw CPU
      ([CloudOps readiness](https://docs.cloud.google.com/architecture/framework/operational-excellence/operational-readiness-and-performance-using-cloudops),
      [SLO concepts](https://docs.cloud.google.com/monitoring/service-monitoring/slo-concepts)).
- [ ] Every change goes through IaC and CI; no console edits. Drift is caught
      by a scheduled `terraform plan`
      ([Automate and manage change](https://docs.cloud.google.com/architecture/framework/operational-excellence/automate-and-manage-change)).
- [ ] Alerting policies have a notification channel and a runbook link;
      an alert without an owner is noise
      ([Alerting](https://docs.cloud.google.com/monitoring/alerts),
      [Manage incidents](https://docs.cloud.google.com/architecture/framework/operational-excellence/manage-incidents-and-problems)).
- [ ] Uptime checks exist for public endpoints
      ([Uptime checks](https://docs.cloud.google.com/monitoring/uptime-checks/introduction)).
- [ ] Rollout uses a progressive strategy (Cloud Deploy canary, Cloud Run
      traffic splitting) with an automated rollback
      ([Cloud Deploy](https://docs.cloud.google.com/deploy/docs/overview)).
- [ ] Right-sizing and idle-resource recommendations are reviewed monthly
      ([Manage and optimize resources](https://docs.cloud.google.com/architecture/framework/operational-excellence/manage-and-optimize-cloud-resources),
      [Recommender](https://docs.cloud.google.com/recommender/docs/overview)).
- [ ] Postmortems are blameless and produce tracked action items
      ([Continuously improve](https://docs.cloud.google.com/architecture/framework/operational-excellence/continuously-improve-and-innovate)).

## 2. Security, privacy and compliance

[Pillar](https://docs.cloud.google.com/architecture/framework/security)

- [ ] No service account keys; ADC, impersonation or Workload Identity
      Federation everywhere. `iam.disableServiceAccountKeyCreation` is
      enforced ([SA best practices](https://docs.cloud.google.com/iam/docs/best-practices-service-accounts),
      [Restrict SAs](https://docs.cloud.google.com/resource-manager/docs/organization-policy/restricting-service-accounts)).
- [ ] IAM grants go to groups, use predefined or custom roles, and no basic
      roles ([Use IAM securely](https://docs.cloud.google.com/iam/docs/using-iam-securely),
      [Role recommendations](https://docs.cloud.google.com/policy-intelligence/docs/role-recommendations-overview)).
- [ ] Zero trust for workloads: GKE Workload Identity, Cloud Run with a
      dedicated runtime SA, no default compute SA
      ([Zero trust](https://docs.cloud.google.com/architecture/framework/security/implement-zero-trust),
      [GKE Workload Identity](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-identity),
      [Cloud Run identity](https://docs.cloud.google.com/run/docs/securing/service-identity)).
- [ ] Security scans run in CI (trivy, tflint) before apply
      ([Shift-left](https://docs.cloud.google.com/architecture/framework/security/implement-shift-left-security)).
- [ ] Data at rest with CMEK where regulation or contract requires it;
      otherwise Google-managed keys are fine
      ([CMEK](https://docs.cloud.google.com/kms/docs/cmek)).
- [ ] Data access audit logs enabled for sensitive services and routed to a
      central, locked bucket
      ([Audit logs](https://docs.cloud.google.com/logging/docs/audit)).
- [ ] VPC Service Controls perimeter around projects with regulated data
      ([VPC-SC](https://docs.cloud.google.com/vpc-service-controls/docs/overview)).
- [ ] Security Command Center is enabled at org level and findings have
      owners ([SCC](https://docs.cloud.google.com/security-command-center/docs/security-command-center-overview)).
- [ ] Container images are signed and Binary Authorization enforces it on
      GKE / Cloud Run
      ([Binary Authorization](https://docs.cloud.google.com/binary-authorization/docs/overview)).
- [ ] Regulated workloads use Assured Workloads and location constraints
      ([Compliance](https://docs.cloud.google.com/architecture/framework/security/meet-regulatory-compliance-and-privacy-needs),
      [Assured Workloads](https://docs.cloud.google.com/assured-workloads/docs/overview)).

## 3. Reliability

[Pillar](https://docs.cloud.google.com/architecture/framework/reliability)

- [ ] Reliability targets derive from user journeys, with an error budget
      ([User-experience goals](https://docs.cloud.google.com/architecture/framework/reliability/define-reliability-based-on-user-experience-goals),
      [Set targets](https://docs.cloud.google.com/architecture/framework/reliability/set-targets)).
- [ ] Regional resources over zonal: regional MIGs, regional GKE, HA Cloud
      SQL, dual-region buckets for critical data
      ([Build HA systems](https://docs.cloud.google.com/architecture/framework/reliability/build-highly-available-systems),
      [Global/regional/zonal](https://docs.cloud.google.com/compute/docs/regions-zones/global-regional-zonal-resources),
      [Cloud SQL HA](https://docs.cloud.google.com/sql/docs/mysql/high-availability)).
- [ ] Scale horizontally with autoscaling; no single large VM as a design
      ([Horizontal scalability](https://docs.cloud.google.com/architecture/framework/reliability/horizontal-scalability),
      [MIG autoscaler](https://docs.cloud.google.com/compute/docs/autoscaler)).
- [ ] Observability covers metrics, logs and traces, with log-based metrics
      for business signals
      ([Observability](https://docs.cloud.google.com/architecture/framework/reliability/observability),
      [Log-based metrics](https://docs.cloud.google.com/logging/docs/logs-based-metrics)).
- [ ] Dependencies fail gracefully: timeouts, retries with backoff, circuit
      breakers, load shedding
      ([Graceful degradation](https://docs.cloud.google.com/architecture/framework/reliability/graceful-degradation)).
- [ ] Recovery from failure is tested (zone outage drill, region failover)
      ([Test recovery](https://docs.cloud.google.com/architecture/framework/reliability/perform-testing-for-recovery-from-failures),
      [DR planning](https://docs.cloud.google.com/architecture/disaster-recovery)).
- [ ] Backups exist and a restore has actually been run
      ([Recovery from data loss](https://docs.cloud.google.com/architecture/framework/reliability/perform-testing-for-recovery-from-data-loss)).
- [ ] Incidents get a postmortem
      ([Postmortems](https://docs.cloud.google.com/architecture/framework/reliability/conduct-postmortems)).

## 4. Cost optimization

[Pillar](https://docs.cloud.google.com/architecture/framework/cost-optimization)

- [ ] Billing export to BigQuery is on and labels make spend attributable
      ([Billing export](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery),
      [Labels](https://docs.cloud.google.com/resource-manager/docs/labels-overview)).
- [ ] Budgets with alert thresholds exist per project or folder
      ([Budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets),
      [Cost awareness](https://docs.cloud.google.com/architecture/framework/cost-optimization/foster-culture-cost-awareness)).
- [ ] `infracost` runs on every PR so the reviewer sees the delta
      ([Align spend with value](https://docs.cloud.google.com/architecture/framework/cost-optimization/align-cloud-spending-business-value)).
- [ ] Spot VMs / Spot node pools for fault-tolerant batch work
      ([Spot VMs](https://docs.cloud.google.com/compute/docs/instances/spot),
      [GKE Spot](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/spot-vms)).
- [ ] Committed use discounts for steady-state compute and databases
      ([CUDs](https://docs.cloud.google.com/docs/cuds)).
- [ ] Storage classes and lifecycle rules match access patterns
      ([Storage classes](https://docs.cloud.google.com/storage/docs/storage-classes),
      [Lifecycle](https://docs.cloud.google.com/storage/docs/lifecycle)).
- [ ] Serverless (Cloud Run, GKE Autopilot) for spiky or low-utilisation
      services; scale to zero is free
      ([Optimize resource usage](https://docs.cloud.google.com/architecture/framework/cost-optimization/optimize-resource-usage),
      [Autopilot](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/autopilot-overview)).
- [ ] Recommender idle-resource and right-sizing hints are acted on
      ([Optimize continuously](https://docs.cloud.google.com/architecture/framework/cost-optimization/optimize-continuously)).

## 5. Performance optimization

[Pillar](https://docs.cloud.google.com/architecture/framework/performance-optimization)

- [ ] Machine families match the workload (compute-, memory-, storage-
      optimised) rather than defaulting to `e2-standard`
      ([Plan resource allocation](https://docs.cloud.google.com/architecture/framework/performance-optimization/plan-resource-allocation),
      [Machine families](https://docs.cloud.google.com/compute/docs/machine-resource)).
- [ ] Autoscaling on real signals (requests, queue depth) not only CPU
      ([Elasticity](https://docs.cloud.google.com/architecture/framework/performance-optimization/elasticity),
      [GKE HPA](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/horizontalpodautoscaler)).
- [ ] Cloud CDN in front of cacheable content; Memorystore for hot data
      ([Cloud CDN](https://docs.cloud.google.com/cdn/docs/overview),
      [Memorystore](https://docs.cloud.google.com/memorystore/docs/redis)).
- [ ] Services are modular so hot paths scale independently
      ([Modular design](https://docs.cloud.google.com/architecture/framework/performance-optimization/promote-modular-design)).
- [ ] Data and compute are colocated in the same region; cross-region
      egress is both slow and billed
      ([Regions and zones](https://docs.cloud.google.com/compute/docs/regions-zones)).
- [ ] Load balancer type matches the traffic (global external HTTP(S) for
      web, internal passthrough for east-west)
      ([Load balancing overview](https://docs.cloud.google.com/load-balancing/docs/load-balancing-overview)).
- [ ] Performance is measured continuously with dashboards and load tests
      ([Monitor and improve](https://docs.cloud.google.com/architecture/framework/performance-optimization/continuously-monitor-and-improve-performance)).

## 6. Sustainability

[Pillar](https://docs.cloud.google.com/architecture/framework/sustainability)

- [ ] Choose low-carbon regions when latency and residency allow
      ([Low-carbon regions](https://docs.cloud.google.com/architecture/framework/sustainability/low-carbon-regions),
      [Region carbon data](https://docs.cloud.google.com/sustainability/region-carbon)).
- [ ] Idle resources are deleted; dev environments scale to zero overnight
      ([Optimize resource usage](https://docs.cloud.google.com/architecture/framework/sustainability/optimize-resource-usage)).
- [ ] Batch jobs use Spot capacity and run in low-carbon windows
      ([Energy-efficient software](https://docs.cloud.google.com/architecture/framework/sustainability/energy-efficient-software)).
- [ ] Cold data moves to Nearline/Coldline/Archive via lifecycle rules
      ([Optimize storage](https://docs.cloud.google.com/architecture/framework/sustainability/optimize-storage)).
- [ ] Carbon Footprint export is enabled and reviewed with cost
      ([Measure and improve](https://docs.cloud.google.com/architecture/framework/sustainability/continuously-measure-improve),
      [Carbon Footprint](https://docs.cloud.google.com/carbon-footprint/docs)).
