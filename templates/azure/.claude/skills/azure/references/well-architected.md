# Azure Well-Architected Framework

Verified 2026-09-15. Source: [Well-Architected Framework](https://learn.microsoft.com/en-us/azure/well-architected/),
[pillars](https://learn.microsoft.com/en-us/azure/well-architected/pillars).
Each pillar has a design-review checklist with coded recommendations (RE:01, SE:01, ...).
Use those codes when you cite a finding in a review. Service-specific guidance lives in the
[service guides](https://learn.microsoft.com/en-us/azure/well-architected/service-guides/), e.g.
[AKS](https://learn.microsoft.com/en-us/azure/well-architected/service-guides/azure-kubernetes-service).
Run the [Azure Well-Architected Review](https://learn.microsoft.com/en-us/assessments/azure-architecture-review/)
for a scored assessment and read [Azure Advisor](https://learn.microsoft.com/en-us/azure/advisor/advisor-overview)
for automated findings against the same pillars.

## Reliability

Principles: [Reliability design principles](https://learn.microsoft.com/en-us/azure/well-architected/reliability/principles).
Checklist: [Reliability checklist](https://learn.microsoft.com/en-us/azure/well-architected/reliability/checklist).

- [ ] Define SLO, RTO and RPO per workload flow before choosing SKUs; the numbers
      decide zone vs region redundancy
      ([Reliability metrics](https://learn.microsoft.com/en-us/azure/well-architected/reliability/metrics)).
- [ ] Run a failure mode analysis: list every dependency, its failure mode and the
      mitigation ([FMA](https://learn.microsoft.com/en-us/azure/well-architected/reliability/failure-mode-analysis)).
- [ ] Deploy zone-redundant SKUs (`zones = ["1","2","3"]`, ZRS storage, zone-redundant
      AKS node pools) in regions that support availability zones
      ([Regions and AZs](https://learn.microsoft.com/en-us/azure/well-architected/reliability/regions-availability-zones)).
- [ ] Add redundancy only where the SLO needs it; each extra layer costs money and
      operational complexity ([Redundancy](https://learn.microsoft.com/en-us/azure/well-architected/reliability/redundancy)).
- [ ] Multi-region only for workloads whose RTO cannot be met by a single region;
      decide active-active vs active-passive explicitly
      ([Multi-region](https://learn.microsoft.com/en-us/azure/well-architected/reliability/highly-available-multi-region-design)).
- [ ] Write and test the DR plan: backups restored, failover rehearsed, documented
      ([Disaster recovery](https://learn.microsoft.com/en-us/azure/well-architected/reliability/disaster-recovery)).
- [ ] Build self-preservation in code: retries with backoff, circuit breakers,
      timeouts, bulkheads ([Self-preservation](https://learn.microsoft.com/en-us/azure/well-architected/reliability/self-preservation)).
- [ ] Test resilience: chaos experiments and load tests in a pre-production ring
      ([Testing strategy](https://learn.microsoft.com/en-us/azure/well-architected/reliability/testing-strategy)).
- [ ] Alert on the health model, not on raw metrics; every alert has an owner
      ([Monitoring and alerting](https://learn.microsoft.com/en-us/azure/well-architected/reliability/monitoring-alerting-strategy)).
- [ ] Keep it simple: fewer components, managed services over self-hosted
      ([Simplify](https://learn.microsoft.com/en-us/azure/well-architected/reliability/simplify)).

## Security

Principles: [Security design principles](https://learn.microsoft.com/en-us/azure/well-architected/security/principles).
Checklist: [Security checklist](https://learn.microsoft.com/en-us/azure/well-architected/security/checklist).
Baseline controls: [Microsoft cloud security benchmark](https://learn.microsoft.com/en-us/security/benchmark/azure/overview).

- [ ] Threat model each new flow (STRIDE is fine); record the mitigations in the spec
      ([Threat model](https://learn.microsoft.com/en-us/azure/well-architected/security/threat-model)).
- [ ] Identity is the perimeter: Entra ID for everything, MFA and Conditional Access
      for humans, managed identities for workloads
      ([Identity and access](https://learn.microsoft.com/en-us/azure/well-architected/security/identity-access)).
- [ ] Segment by management group, subscription, resource group and VNet; one blast
      radius per segment ([Segmentation](https://learn.microsoft.com/en-us/azure/well-architected/security/segmentation)).
- [ ] Network: private endpoints for PaaS, NSGs on every subnet, Azure Firewall or
      NVA in the hub, no direct internet ingress to compute
      ([Networking](https://learn.microsoft.com/en-us/azure/well-architected/security/networking)).
- [ ] Encrypt in transit (TLS 1.2+) and at rest; customer-managed keys only when a
      regulation demands it ([Encryption](https://learn.microsoft.com/en-us/azure/well-architected/security/encryption)).
- [ ] Application secrets in Key Vault, fetched by managed identity, rotated on a
      schedule; nothing in code, config or CI logs
      ([Application secrets](https://learn.microsoft.com/en-us/azure/well-architected/security/application-secrets)).
- [ ] Harden resources: disable local auth, public network access and legacy TLS on
      every PaaS service that offers the switch
      ([Harden resources](https://learn.microsoft.com/en-us/azure/well-architected/security/harden-resources)).
- [ ] Shift left: SAST, dependency and IaC scanning (`trivy`) in the pipeline
      ([Secure development lifecycle](https://learn.microsoft.com/en-us/azure/well-architected/security/secure-development-lifecycle)).
- [ ] Enable Defender for Cloud on every subscription and route alerts to an owner
      ([Monitor threats](https://learn.microsoft.com/en-us/azure/well-architected/security/monitor-threats),
      [Defender for Cloud](https://learn.microsoft.com/en-us/azure/defender-for-cloud/defender-for-cloud-introduction)).

## Cost optimization

Principles: [Cost optimization design principles](https://learn.microsoft.com/en-us/azure/well-architected/cost-optimization/principles).
Checklist: [Cost optimization checklist](https://learn.microsoft.com/en-us/azure/well-architected/cost-optimization/checklist).

- [ ] Build a cost model per workload before deploying; `infracost breakdown` gives the
      IaC part ([Cost model](https://learn.microsoft.com/en-us/azure/well-architected/cost-optimization/cost-model)).
- [ ] Tag everything with `cost-center`, `owner`, `environment` so Cost Management can
      allocate spend ([Collect and review cost data](https://learn.microsoft.com/en-us/azure/well-architected/cost-optimization/collect-review-cost-data)).
- [ ] Set budgets with alerts at 50/80/100 % and Policy limits on SKUs and regions
      ([Spending guardrails](https://learn.microsoft.com/en-us/azure/well-architected/cost-optimization/set-spending-guardrails)).
- [ ] Use reservations or savings plans for steady compute, spot for interruptible,
      dev/test pricing where eligible
      ([Best rates](https://learn.microsoft.com/en-us/azure/well-architected/cost-optimization/get-best-rates)).
- [ ] Scale to zero where the service allows it (Container Apps, Functions consumption,
      AKS node autoscaler with a small minimum)
      ([Scaling costs](https://learn.microsoft.com/en-us/azure/well-architected/cost-optimization/optimize-scaling-costs)).
- [ ] Non-production environments: smaller SKUs, auto-shutdown, shorter retention,
      tear down on a schedule
      ([Environment costs](https://learn.microsoft.com/en-us/azure/well-architected/cost-optimization/optimize-environment-costs)).
- [ ] Review Advisor cost recommendations monthly and act on idle resources.
- [ ] Follow the Cost Management practice guide for reporting cadence
      ([Cost management best practices](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/cost-mgt-best-practices)).

## Operational excellence

Principles: [Operational excellence design principles](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/principles).
Checklist: [Operational excellence checklist](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/checklist).

- [ ] Everything is IaC (Terraform or Bicep), reviewed in a PR, applied by a pipeline;
      no portal changes to managed resources
      ([IaC design](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/infrastructure-as-code-design)).
- [ ] CI runs fmt, validate, lint, security scan and a plan on every PR
      ([Continuous integration](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/release-engineering-continuous-integration)).
- [ ] Safe deployment practices: progressive exposure, health gates, automated rollback
      ([Safe deployments](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/safe-deployments)).
- [ ] Diagnostic settings on every resource to a central Log Analytics workspace;
      Application Insights for the app
      ([Observability](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/observability),
      [Instrument the application](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/instrument-application)).
- [ ] Automate repetitive operations (rotation, cleanup, scaling); a runbook is a
      bug report against automation
      ([Automate tasks](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/automate-tasks)).
- [ ] Policy compliance is part of the operational dashboard, not an annual audit.
- [ ] Every alert maps to a documented response and an on-call owner.

## Performance efficiency

Principles: [Performance efficiency design principles](https://learn.microsoft.com/en-us/azure/well-architected/performance-efficiency/principles).
Checklist: [Performance efficiency checklist](https://learn.microsoft.com/en-us/azure/well-architected/performance-efficiency/checklist).

- [ ] Set numeric performance targets (p95 latency, throughput) per flow first
      ([Performance targets](https://learn.microsoft.com/en-us/azure/well-architected/performance-efficiency/performance-targets)).
- [ ] Pick the service tier from the targets, not from habit; check the service
      guide limits ([Select services](https://learn.microsoft.com/en-us/azure/well-architected/performance-efficiency/select-services)).
- [ ] Prefer horizontal scaling and partitioning over bigger SKUs; make scale rules
      metric-driven ([Scale and partition](https://learn.microsoft.com/en-us/azure/well-architected/performance-efficiency/scale-partition)).
- [ ] Collect performance telemetry continuously, not only during incidents
      ([Collect performance data](https://learn.microsoft.com/en-us/azure/well-architected/performance-efficiency/collect-performance-data)).
- [ ] Load test before release against production-like data volumes
      ([Performance testing](https://learn.microsoft.com/en-us/azure/well-architected/performance-efficiency/performance-test)).
- [ ] Optimise data access: indexes, caching, right consistency level, connection pooling
      ([Data performance](https://learn.microsoft.com/en-us/azure/well-architected/performance-efficiency/optimize-data-performance)).
- [ ] Profile code and infrastructure paths together; fix the hot path, not everything
      ([Code and infrastructure](https://learn.microsoft.com/en-us/azure/well-architected/performance-efficiency/optimize-code-infrastructure)).
- [ ] Revisit targets and SKUs on a cadence as usage changes
      ([Continuous optimization](https://learn.microsoft.com/en-us/azure/well-architected/performance-efficiency/continuous-performance-optimize)).
