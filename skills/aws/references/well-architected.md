# Well-Architected checks

The [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html) has [six pillars](https://docs.aws.amazon.com/wellarchitected/latest/framework/the-pillars-of-the-framework.html). Apply the checks below to the area you are changing. Each check is a yes/no question; a "no" needs either a fix or a written reason in the PR.

Run a formal review with the [AWS Well-Architected Tool](https://docs.aws.amazon.com/wellarchitected/latest/userguide/intro.html) for anything production-facing.

## 1. Operational excellence

Source: [pillar overview](https://docs.aws.amazon.com/wellarchitected/latest/framework/operational-excellence.html), [whitepaper](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/welcome.html).

- [ ] Everything is infrastructure as code (Terraform); no console-created resources. Why: unreproducible changes cannot be reviewed or rolled back.
- [ ] Every change goes through `plan` review and CI gates (fmt, validate, tflint, trivy, infracost).
- [ ] CloudWatch alarms exist for each SLO-relevant metric and route to a channel someone reads ([alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AlarmThatSendsEmail.html)).
- [ ] Logs are structured (JSON) and shipped to CloudWatch Logs with a retention period set; no infinite retention by default.
- [ ] Distributed tracing is on for request paths crossing services ([X-Ray](https://docs.aws.amazon.com/xray/latest/devguide/aws-xray.html)).
- [ ] Runbooks for routine operations are automated with [Systems Manager Automation](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation.html), not wiki pages.
- [ ] [AWS Health](https://docs.aws.amazon.com/health/latest/ug/what-is-aws-health.html) events are routed to the on-call channel.
- [ ] Deployments are small, frequent and reversible; a rollback path is documented before the change ships.
- [ ] Post-incident reviews produce concrete IaC or alarm changes, not just documents.

## 2. Security

Source: [pillar overview](https://docs.aws.amazon.com/wellarchitected/latest/framework/security.html), [whitepaper](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/welcome.html).

- [ ] Humans authenticate through IAM Identity Center with MFA; no IAM users with passwords or access keys ([IAM best practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)).
- [ ] Workloads use roles: instance profiles, task roles, Lambda execution roles, EKS Pod Identity. No credentials in environment variables or images.
- [ ] Policies are least privilege and validated with [IAM Access Analyzer policy validation](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html); unused permissions removed based on [last-accessed data](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_last-accessed.html).
- [ ] CloudTrail organization trail is on, logs go to a locked-down log archive bucket with Object Lock ([org trail](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/creating-trail-organization.html), [Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)).
- [ ] GuardDuty, Security Hub and Inspector are enabled org-wide with a delegated administrator ([GuardDuty](https://docs.aws.amazon.com/guardduty/latest/ug/what-is-guardduty.html), [Security Hub](https://docs.aws.amazon.com/securityhub/latest/userguide/what-is-securityhub.html), [Inspector](https://docs.aws.amazon.com/inspector/latest/user/what-is-inspector.html)).
- [ ] Data at rest is encrypted: S3 default encryption, EBS encryption by default, RDS/DynamoDB encryption, KMS customer managed keys where key policy control is required ([S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/default-bucket-encryption.html), [EBS](https://docs.aws.amazon.com/ebs/latest/userguide/EBSEncryption.html), [KMS](https://docs.aws.amazon.com/kms/latest/developerguide/overview.html)).
- [ ] S3 Block Public Access is on at account level; bucket policies deny non-TLS requests ([Block Public Access](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html)).
- [ ] Compute sits in private subnets; ingress only through ALB/CloudFront with WAF ([WAF](https://docs.aws.amazon.com/waf/latest/developerguide/what-is-aws-waf.html)); VPC Flow Logs on ([flow logs](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html)).
- [ ] EC2 requires IMDSv2 ([IMDS](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html)); no SSH ports open, use Session Manager.
- [ ] Secrets live in Secrets Manager or SSM SecureString with rotation where supported ([Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html), [Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html)).
- [ ] Container images are scanned in ECR before deploy ([ECR scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning.html)).

## 3. Reliability

Source: [pillar overview](https://docs.aws.amazon.com/wellarchitected/latest/framework/reliability.html), [whitepaper](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/welcome.html).

- [ ] Production workloads span at least two AZs (three for EKS and databases); RDS is Multi-AZ.
- [ ] Load balancers front all compute; health checks fail fast on real dependencies ([ELB](https://docs.aws.amazon.com/elasticloadbalancing/latest/userguide/what-is-load-balancing.html)).
- [ ] Auto Scaling groups or Kubernetes autoscaling replace failed instances without human action ([EC2 Auto Scaling](https://docs.aws.amazon.com/autoscaling/ec2/userguide/what-is-amazon-ec2-auto-scaling.html)).
- [ ] Service quotas are monitored and raised ahead of need ([Service Quotas](https://docs.aws.amazon.com/servicequotas/latest/userguide/intro.html)). Why: quota exhaustion is a common outage cause that looks like a bug.
- [ ] Backups are automated by AWS Backup with a tested restore, and RPO/RTO are written down ([AWS Backup](https://docs.aws.amazon.com/aws-backup/latest/devguide/whatisbackup.html)).
- [ ] Clients retry with exponential backoff and jitter; timeouts are set on every outbound call.
- [ ] DNS failover or multi-Region is used only when the RTO demands it ([Route 53 failover](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/dns-failover.html)); do not add multi-Region without a stated requirement.
- [ ] Resilience is tested, not assumed: run [AWS Fault Injection Service](https://docs.aws.amazon.com/fis/latest/userguide/what-is.html) experiments and assess with [Resilience Hub](https://docs.aws.amazon.com/resilience-hub/latest/userguide/what-is.html).
- [ ] Stateful data is not on ephemeral instance storage; EBS volumes have snapshots.

## 4. Performance efficiency

Source: [pillar overview](https://docs.aws.amazon.com/wellarchitected/latest/framework/performance-efficiency.html), [whitepaper](https://docs.aws.amazon.com/wellarchitected/latest/performance-efficiency-pillar/welcome.html).

- [ ] Instance families match the workload (compute, memory, storage optimised); use [Compute Optimizer](https://docs.aws.amazon.com/compute-optimizer/latest/ug/what-is-compute-optimizer.html) recommendations instead of guessing ([instance types](https://docs.aws.amazon.com/ec2/latest/instancetypes/instance-types.html)).
- [ ] Graviton (arm64) is the default where the runtime supports it ([Graviton](https://aws.amazon.com/ec2/graviton/)).
- [ ] Managed services (Lambda, Fargate, Aurora, DynamoDB) are chosen before self-managed equivalents.
- [ ] Static and cacheable content goes through CloudFront ([CloudFront](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Introduction.html)).
- [ ] Database access patterns are designed before the schema; DynamoDB tables follow [DynamoDB best practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html), RDS follows [RDS best practices](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_BestPractices.html).
- [ ] Lambda functions are right-sized on memory and keep init work outside the handler ([Lambda best practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)).
- [ ] Load tests run before launch and after major changes; metrics are compared against the previous baseline.
- [ ] Traffic between services in the same Region stays inside the VPC via VPC endpoints ([PrivateLink](https://docs.aws.amazon.com/vpc/latest/privatelink/what-is-privatelink.html)).

## 5. Cost optimisation

Source: [pillar overview](https://docs.aws.amazon.com/wellarchitected/latest/framework/cost-optimization.html), [whitepaper](https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/welcome.html).

- [ ] Every resource carries the mandatory tags and they are activated as cost allocation tags ([cost allocation tags](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/cost-alloc-tags.html)).
- [ ] A budget with alert thresholds exists per account/environment ([Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)) and Cost Anomaly Detection is on ([anomaly detection](https://docs.aws.amazon.com/cost-management/latest/userguide/manage-ad.html)).
- [ ] `infracost` runs on every PR; unexplained increases block merge.
- [ ] Steady-state compute is covered by Savings Plans or Reserved Instances after usage stabilises ([Savings Plans](https://docs.aws.amazon.com/savingsplans/latest/userguide/what-is-savings-plans.html), [RIs](https://docs.aws.amazon.com/cost-management/latest/userguide/reserved-instances.html)).
- [ ] Fault-tolerant batch and CI work runs on Spot ([Spot](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-spot-instances.html)).
- [ ] Non-production environments scale to zero or shut down outside working hours.
- [ ] S3 lifecycle rules move cold data to cheaper classes and expire logs ([lifecycle](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-transition-general-considerations.html)).
- [ ] NAT Gateway data processing is minimised with S3/DynamoDB gateway endpoints and interface endpoints for chatty services. Why: NAT egress is a frequent hidden cost.
- [ ] Trusted Advisor cost checks are reviewed monthly ([Trusted Advisor](https://docs.aws.amazon.com/awssupport/latest/user/trusted-advisor.html)); orphaned EBS volumes, snapshots, EIPs and idle load balancers are deleted.
- [ ] Cost Explorer is used to attribute spend to tags before optimising ([Cost Explorer](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html)).

## 6. Sustainability

Source: [pillar overview](https://docs.aws.amazon.com/wellarchitected/latest/framework/sustainability.html), [whitepaper](https://docs.aws.amazon.com/wellarchitected/latest/sustainability-pillar/sustainability-pillar.html).

- [ ] Utilisation targets exist; over-provisioned instances are downsized using Compute Optimizer data.
- [ ] Graviton and serverless are preferred; they do more work per watt ([Graviton](https://aws.amazon.com/ec2/graviton/)).
- [ ] Idle resources are removed; dev/test scales to zero when unused.
- [ ] Data has retention and lifecycle policies; nothing is kept "just in case" without a rule.
- [ ] Regions are chosen with the [Customer Carbon Footprint Tool](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/what-is-ccft.html) in mind when latency and compliance allow.
- [ ] Build artefacts and container images are minimal (multi-stage builds, no unused layers).
- [ ] Batch work is scheduled and consolidated instead of running always-on pollers.

## Applying the pillars in a PR

1. Identify the pillars the change touches (a new database touches security, reliability, cost).
2. Copy the relevant checks into the PR description and tick them honestly.
3. For each unticked item, write one line: the risk accepted and who accepted it.
4. Link the Well-Architected Tool workload if one exists.
