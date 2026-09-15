# Landing zone: Organizations, Control Tower, accounts, network

A landing zone is the multi-account foundation everything else deploys into. Get it right first: retrofitting account structure is a migration project. Primary sources: [Organizing Your AWS Environment Using Multiple Accounts](https://docs.aws.amazon.com/whitepapers/latest/organizing-your-aws-environment/organizing-your-aws-environment.html), [AWS Security Reference Architecture (SRA)](https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture/welcome.html), [AWS Control Tower](https://docs.aws.amazon.com/controltower/latest/userguide/what-is-control-tower.html).

## Why multiple accounts

An account is the strongest isolation boundary AWS offers: separate IAM, quotas, billing and blast radius ([Organizations concepts](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_getting-started_concepts.html)). Use accounts, not VPCs or tags, to separate environments, teams and security domains.

Rules:

- One account per workload per environment (`payments-prod`, `payments-dev`). Shared "dev" accounts for many teams end up with unbounded permissions.
- Never run workloads in the management account. Keep it for Organizations, billing and Control Tower only ([management account best practices](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_best-practices_mgmt-acct.html)).
- Enable "all features" in Organizations so SCPs and service integrations work ([all features](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_org_support-all-features.html)).

## AWS Organizations

[Organizations](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_introduction.html) is the root: it owns accounts, OUs, policies and consolidated billing.

Checklist:

- [ ] Management account has no workloads, no IAM users, hardware MFA on root, root email is a distribution list.
- [ ] Delegated administrator accounts are set for security services so the management account is not used day to day ([delegated admin](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_accounts_delegated_admin.html), [integrated services](https://docs.aws.amazon.com/organizations/latest/userguide/services-that-can-integrate.html)).
- [ ] Tag policies enforce the mandatory tag keys and allowed values ([tag policies](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_tag-policies.html)).
- [ ] Shared resources (Transit Gateway, IPAM pools, subnets) are shared with AWS RAM, not duplicated ([RAM](https://docs.aws.amazon.com/ram/latest/userguide/what-is.html)).

## Recommended OU structure

From [Recommended OUs](https://docs.aws.amazon.com/whitepapers/latest/organizing-your-aws-environment/recommended-ous.html). Start with the first four; add the rest when needed.

```
Root
├── Security          # Log Archive, Security Tooling (Audit)  — Control Tower creates these
├── Infrastructure    # Network (TGW, IPAM, DNS), Shared Services (CI, artefacts, Identity Center)
├── Workloads
│   ├── Prod
│   └── NonProd       # dev, test, staging accounts
├── Sandbox           # individual experimentation, hard budget, no network to prod
├── Deployments       # CI/CD accounts that assume roles into Workloads (optional)
├── PolicyStaging     # test SCPs before applying to Workloads
└── Suspended         # decommissioned accounts, deny-all SCP
```

Why OUs: SCPs and Control Tower controls attach to OUs, so structure reflects policy, not org charts. Group by function and environment, never by team name (teams change).

## Control Tower

[Control Tower](https://docs.aws.amazon.com/controltower/latest/userguide/how-control-tower-works.html) sets up Organizations, the Log Archive and Audit accounts, IAM Identity Center, org-wide CloudTrail and Config, and a library of controls. Use it for any new organisation unless there is a documented reason not to.

- Accounts: Log Archive holds immutable logs ([Log Archive](https://docs.aws.amazon.com/controltower/latest/userguide/log-archive-account.html)); Audit (Security Tooling) holds Security Hub, GuardDuty, Config aggregator and read-only cross-account roles ([Audit](https://docs.aws.amazon.com/controltower/latest/userguide/audit-account.html)).
- Controls: preventive (SCP), detective (Config rules) and proactive (CloudFormation hooks). Enable the "Strongly recommended" set at minimum ([controls](https://docs.aws.amazon.com/controltower/latest/userguide/controls.html)).
- Regions: deny Regions you do not use; region deny is a Control Tower control ([Region deny](https://docs.aws.amazon.com/controltower/latest/userguide/region-how.html)).
- Vending: create accounts with Account Factory, never by hand ([Account Factory](https://docs.aws.amazon.com/controltower/latest/userguide/account-factory.html)). For IaC-driven vending use Account Factory for Terraform (AFT) ([AFT overview](https://docs.aws.amazon.com/controltower/latest/userguide/aft-overview.html), [terraform-aws-control_tower_account_factory](https://github.com/aws-ia/terraform-aws-control_tower_account_factory)).
- Follow [Control Tower best practices](https://docs.aws.amazon.com/controltower/latest/userguide/best-practices.html): do not modify Control Tower-managed resources outside Control Tower, and re-register OUs after drift.

## Service control policies (SCPs) and resource control policies (RCPs)

[SCPs](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html) cap what identities in an account can do; they grant nothing. [RCPs](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_rcps.html) cap what can be done to resources (for example, restrict S3 access to principals in your org). Together they form a [data perimeter](https://aws.amazon.com/identity/data-perimeters-on-aws/).

Use a deny-list strategy: keep `FullAWSAccess` attached and add targeted denies ([SCP strategies](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps_strategies.html)). Why: allow-lists break every time AWS adds an API a service needs.

Baseline SCPs for the Workloads OU (from [SCP examples](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps_examples.html)):

- Deny leaving the organization (`organizations:LeaveOrganization`).
- Deny disabling or deleting CloudTrail, Config, GuardDuty, Security Hub.
- Deny root user actions (`aws:PrincipalArn` = `arn:aws:iam::*:root`).
- Deny use of Regions outside the approved list (with exceptions for global services).
- Deny creation of IAM users and access keys (`iam:CreateUser`, `iam:CreateAccessKey`). Why: forces roles and Identity Center.
- Deny disabling EBS encryption by default and S3 account-level Block Public Access.
- Deny modification of the landing-zone roles (`AWSControlTowerExecution`, your CI/audit roles) by anyone except them.

Test every SCP in the PolicyStaging OU first. An SCP typo in the Workloads OU is an outage.

## Centralised logging and security

Per the [SRA](https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture/welcome.html):

- [ ] One organization CloudTrail trail delivering to the Log Archive bucket, with Object Lock and a KMS key owned by Log Archive ([org trail](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/creating-trail-organization.html), [CloudTrail security best practices](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/best-practices-security.html)). Consider [CloudTrail Lake](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-lake.html) for querying.
- [ ] Config recorders in every account and Region, aggregated in Security Tooling ([Config aggregator](https://docs.aws.amazon.com/config/latest/developerguide/aggregate-data.html)).
- [ ] Security Hub delegated administrator is Security Tooling, with the AWS Foundational Security Best Practices standard enabled ([designate admin](https://docs.aws.amazon.com/securityhub/latest/userguide/designate-orgs-admin-account.html)).
- [ ] GuardDuty and Inspector enabled org-wide via the same delegated admin.
- [ ] VPC Flow Logs, ALB logs and CloudFront logs from workload accounts land in Log Archive with lifecycle rules.
- [ ] IAM Access Analyzer with the organization as zone of trust runs in Security Tooling ([Access Analyzer](https://docs.aws.amazon.com/IAM/latest/UserGuide/what-is-access-analyzer.html)).
- [ ] Nobody has write access to Log Archive except the log-delivery service principals.

## Network: hub and spoke

Source: [Building a Scalable and Secure Multi-VPC Network Infrastructure](https://docs.aws.amazon.com/whitepapers/latest/building-scalable-secure-multi-vpc-network-infrastructure/welcome.html).

- **Network account** in the Infrastructure OU owns the [Transit Gateway](https://docs.aws.amazon.com/vpc/latest/tgw/what-is-transit-gateway.html), shared to workload accounts with RAM. Workload VPCs attach as spokes; there is no VPC peering mesh.
- **IPAM** allocates non-overlapping CIDRs per account and Region ([IPAM](https://docs.aws.amazon.com/vpc/latest/ipam/what-it-is-ipam.html)). Why: overlapping CIDRs block TGW routing and are impossible to fix later.
- **Route tables on the TGW** separate prod from non-prod: prod spokes cannot reach non-prod spokes.
- **Centralised egress** through a NAT/inspection VPC with [Network Firewall](https://docs.aws.amazon.com/network-firewall/latest/developerguide/what-is-aws-network-firewall.html) when compliance requires egress control; otherwise NAT per VPC is simpler and often cheaper for low traffic.
- **VPC endpoints** for S3, DynamoDB, STS, ECR, CloudWatch Logs, SSM in every workload VPC so traffic to AWS services never crosses NAT ([interface endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/create-interface-endpoint.html)). Share endpoints from the network VPC via Route 53 private hosted zones when endpoint cost dominates.
- **Standard workload VPC**: 3 AZs; per AZ one public subnet (load balancers, NAT) and one or more private subnets (compute, data). No public IPs on instances ([VPC how it works](https://docs.aws.amazon.com/vpc/latest/userguide/how-it-works.html), [VPC security best practices](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-best-practices.html)).
- **DNS**: Route 53 Resolver rules shared from the network account for hybrid and cross-account resolution.

## Identity across accounts

- IAM Identity Center in the management account (or a delegated admin), connected to the corporate IdP. Permission sets map to roles in every account ([Identity Center](https://docs.aws.amazon.com/singlesignon/latest/userguide/what-is.html), [permission sets](https://docs.aws.amazon.com/singlesignon/latest/userguide/permissionsetsconcept.html)).
- CI/CD assumes roles in target accounts via OIDC federation from a Deployments account; no keys stored in the pipeline ([OIDC providers](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html)).
- Cross-account roles carry `aws:PrincipalOrgID` conditions so only principals in your organization can assume them ([condition keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_aws-condition-keys.html)).

See [iam.md](iam.md) for policy patterns.

## Minimum viable landing zone (small org)

If Control Tower is overkill today, still do these; they are the parts that hurt to retrofit:

1. Organizations with all features, management account empty.
2. Four accounts: Log Archive, Security Tooling, Shared Services (CI + Identity Center), one workload account per environment.
3. Region deny SCP, root deny SCP, CloudTrail/Config protection SCP.
4. Organization CloudTrail and Config aggregator to Log Archive/Security Tooling.
5. IAM Identity Center with MFA; delete all IAM users.
6. IPAM plan written down even if VPCs are created by hand.
7. Budgets and Cost Anomaly Detection in every account.
