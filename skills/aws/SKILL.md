---
name: aws
description: AWS best practices and architecture for writing, reviewing and deploying infrastructure with Terraform, the AWS CLI and read-only MCP servers. Use when a task touches AWS accounts, IAM, VPC, EKS, S3, Lambda, RDS, Organizations, Control Tower, landing zones, Well-Architected reviews, cost optimisation, security hardening, remote state, tagging, aws-vault or IAM Identity Center login, or the aws/aws-docs MCP servers. Covers the six Well-Architected pillars, multi-account landing zones (OUs, SCPs, centralised logging and security), least-privilege IAM, CLI cheatsheet, Terraform on AWS conventions (S3 backend with use_lockfile, mandatory tags, tflint/trivy/infracost) and MCP configuration.
---

# AWS

Rules for every AWS task in this project. Read the linked reference before touching the matching area.

## Non-negotiables

1. **Terraform through aws-vault.** Run `aws-vault exec <profile> -- terraform …`, or enable the devenv wrapper once in the project's `devenv.nix`: `aws-vault = { enable = true; profile = "<profile>"; awscliWrapper.enable = true; terraformWrapper.enable = true; };`. It is off by default because the profile is per user. Never pass credentials to the provider. AWS-specific conventions: [references/terraform.md](references/terraform.md); generic practice: [terraform skill](../terraform/SKILL.md).
2. **No long-lived access keys.** Log in with IAM Identity Center and run commands through `aws-vault exec <profile> -- <cmd>`. Never create IAM user access keys for humans or CI. Why: keys leak and never expire; roles expire in hours ([IAM best practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)). See [references/iam.md](references/iam.md).
3. **Least privilege, always.** Scope every policy to actions, resources and conditions. Reject `"Action": "*"` and `"Resource": "*"` in review unless an AWS doc requires it.
4. **Remote state in S3** with `encrypt = true` and `use_lockfile = true`. No local state, no DynamoDB lock table for new projects; DynamoDB locking is deprecated ([Terraform S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3)).
5. **Mandatory tags** on every taggable resource via `default_tags`: `Project`, `Environment`, `Owner`, `CostCenter`, `ManagedBy=terraform`. Why: cost allocation and ownership are impossible after the fact ([Tagging best practices](https://docs.aws.amazon.com/whitepapers/latest/tagging-best-practices/tagging-best-practices.html)).
6. **Secrets stay in agenix.** Store with `secret-add NAME`, use with `secret-run --only NAME -- <cmd>`. Never print, echo, log or write a secret to disk. In AWS, put runtime secrets in Secrets Manager or SSM Parameter Store (SecureString), never in code, tfvars or user data.
7. **MCP servers are read-only by default.** Write access is a deliberate per-project opt-in. See [references/mcp.md](references/mcp.md).
8. **Encrypt everything at rest and in transit.** S3 default encryption, EBS encryption by default, KMS customer managed keys for regulated data, TLS 1.2+ only ([Security pillar](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/welcome.html)).

## Workflow

```bash
aws sso login --profile <profile>                     # once per session (IAM Identity Center)
aws-vault exec <profile> -- aws sts get-caller-identity   # verify who you are before anything else
aws-vault exec <profile> -- terraform init               # or plain `terraform init` with terraformWrapper enabled
terraform plan -out=plan.tfplan
tflint --recursive && trivy config . && infracost breakdown --path .
terraform apply plan.tfplan
```

Before `apply`: read the plan, confirm the account ID and region in `get-caller-identity` match the target, and check that nothing is destroyed unintentionally. Never apply from a dirty working tree.

## Review checklist

Run this on every PR that touches AWS infrastructure.

- [ ] `terraform fmt -check`, `terraform validate`, `tflint`, `trivy config .` pass with no HIGH/CRITICAL.
- [ ] Backend is S3 with `encrypt = true`, `use_lockfile = true`, bucket has versioning and Block Public Access ([S3 Block Public Access](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html)).
- [ ] Provider has `default_tags` with the mandatory set; pinned provider and module versions.
- [ ] No IAM user, no access key, no inline `*` policy, no `iam:PassRole` on `*`.
- [ ] Security groups: no `0.0.0.0/0` ingress except ports 80/443 on public load balancers ([VPC security best practices](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-best-practices.html)).
- [ ] EC2 uses IMDSv2 required (`http_tokens = "required"`) ([IMDS](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html)).
- [ ] Data stores (S3, EBS, RDS, DynamoDB) are encrypted; S3 buckets are private.
- [ ] Logging on: CloudTrail, VPC Flow Logs, ALB/CloudFront access logs where relevant.
- [ ] `infracost` diff reviewed; no unexplained cost jump.
- [ ] Multi-AZ for anything production; no single-AZ RDS or single-instance stateful service.
- [ ] Well-Architected pillar checks applied for the changed area ([references/well-architected.md](references/well-architected.md)).

## Architecture defaults

Use these unless the spec says otherwise, and say why when you deviate.

| Area | Default | Why |
|---|---|---|
| Accounts | One account per workload per environment inside AWS Organizations; Control Tower landing zone | Blast radius and billing isolation ([Organizing your environment](https://docs.aws.amazon.com/whitepapers/latest/organizing-your-aws-environment/organizing-your-aws-environment.html)) |
| Network | VPC with 3 AZs, private subnets for compute, public only for load balancers/NAT; Transit Gateway hub for multi-VPC | Multi-AZ resilience, no public compute ([Multi-VPC whitepaper](https://docs.aws.amazon.com/whitepapers/latest/building-scalable-secure-multi-vpc-network-infrastructure/welcome.html)) |
| Compute | Serverless (Lambda/Fargate) before EC2; Graviton where supported | Less to patch, cheaper ([Graviton](https://aws.amazon.com/ec2/graviton/)) |
| Kubernetes | EKS with private endpoint, access entries, Pod Identity, managed add-ons | Least privilege for pods, no aws-auth ConfigMap ([EKS best practices](https://docs.aws.amazon.com/eks/latest/best-practices/introduction.html)) |
| Identity | IAM Identity Center permission sets; roles with OIDC for CI | No static credentials ([Identity Center](https://docs.aws.amazon.com/singlesignon/latest/userguide/what-is.html)) |
| Data | S3 with versioning + lifecycle, RDS Multi-AZ, AWS Backup plans | Durability and recoverability ([AWS Backup](https://docs.aws.amazon.com/aws-backup/latest/devguide/whatisbackup.html)) |
| Observability | CloudWatch alarms on SLOs, Security Hub + GuardDuty org-wide | Detect before customers do ([CloudWatch](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/WhatIsCloudWatch.html)) |
| Cost | Budgets with alerts, Cost Anomaly Detection, Savings Plans after 30 days of steady state | Nobody watches the bill otherwise ([Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)) |

Landing-zone design (OUs, SCPs, log archive, security tooling account): [references/landing-zone.md](references/landing-zone.md).

## Tools in this shell

| Tool | Use it for |
|---|---|
| `aws` (awscli2) | Every API call; see [references/cli-cheatsheet.md](references/cli-cheatsheet.md) |
| `aws-vault` | Wraps commands with short-lived credentials; `aws-vault exec <profile> -- <cmd>` |
| `session-manager-plugin` | `aws ssm start-session` instead of SSH and bastions ([Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html)) |
| `terraform` (run via `aws-vault exec`, or the opt-in `terraformWrapper`), `tflint`, `trivy`, `terraform-docs`, `infracost` | IaC, lint, security scan, docs, cost |
| `cfn-lint` | Lint any CloudFormation/SAM template before deploying |
| `eksctl` | Bootstrap and inspect EKS clusters; prefer Terraform for the long-lived definition |

### Opt-in tools

Not installed by default because of size. Add to `packages` in the project's `devenv.nix`:

```nix
{ pkgs, ... }: {
  packages = [
    pkgs.aws-sam-cli    # local Lambda/API Gateway testing
    pkgs.aws-cdk-cli    # ~1.9 GB closure; only if the project is CDK-based
  ];
}
```

## References

- [references/well-architected.md](references/well-architected.md) — six pillars, concrete checks per pillar
- [references/landing-zone.md](references/landing-zone.md) — Organizations, Control Tower, OUs, SCPs, central logging and network
- [references/iam.md](references/iam.md) — identity model, policy patterns, CI/EKS federation, review rules
- [references/cli-cheatsheet.md](references/cli-cheatsheet.md) — login, profiles, common read/inspect commands, SSM sessions
- [references/terraform.md](references/terraform.md) — AWS-specific Terraform: backend, provider, default_tags, modules, gotchas
- [references/mcp.md](references/mcp.md) — `aws` and `aws-docs` MCP servers, auth, read-only gate, write opt-in
