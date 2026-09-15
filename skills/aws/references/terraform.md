# Terraform on AWS

AWS-specific Terraform conventions: backend, provider, tags, modules and AWS gotchas. Generic Terraform practice (layout, testing, module design, CI) lives in the always-installed [terraform skill](../terraform/SKILL.md); do not duplicate it here. AWS's own guidance: [Best practices for using the Terraform AWS Provider](https://docs.aws.amazon.com/prescriptive-guidance/latest/terraform-aws-provider-best-practices/introduction.html).

Run Terraform through aws-vault so credentials are short-lived and scoped to the child process. Use `aws-vault exec <profile> -- terraform ...`, or turn on the devenv wrapper in the project's `devenv.nix` (`aws-vault = { enable = true; profile = "<profile>"; terraformWrapper.enable = true; };`) so plain `terraform plan` runs through aws-vault. The wrapper is off by default because the profile is per user.

## Backend: S3 with native locking

```hcl
terraform {
  required_version = ">= 1.10"
  backend "s3" {
    bucket       = "<org>-tfstate-<account-id>-eu-west-1"
    key          = "myproject/prod/terraform.tfstate"
    region       = "eu-west-1"
    encrypt      = true
    kms_key_id   = "alias/tfstate"     # optional; SSE-S3 is acceptable, CMK when state holds regulated data
    use_lockfile = true                # S3 lock file (<key>.tflock); no DynamoDB table
  }
}
```

`use_lockfile = true` enables S3-native state locking; DynamoDB-based locking is deprecated and will be removed ([Terraform S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3)). Do not create a DynamoDB lock table for new projects. The lock file needs `s3:GetObject`, `s3:PutObject` and `s3:DeleteObject` on `<key>.tflock` in addition to the state-key permissions.

State contains secrets in plain text, so the bucket must have:

- Versioning on, to recover a corrupted or deleted state ([Versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html)).
- Default encryption, SSE-KMS preferred ([default encryption](https://docs.aws.amazon.com/AmazonS3/latest/userguide/default-bucket-encryption.html)).
- Block Public Access, all four flags ([Block Public Access](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html)).
- A bucket policy denying `aws:SecureTransport = false` and limiting `s3:GetObject`/`PutObject`/`DeleteObject` on the state prefix to the CI deploy role and platform admins ([bucket policies](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-policies.html)).
- A lifecycle rule expiring noncurrent versions after 90 days.
- `lifecycle { prevent_destroy = true }` on the bucket and its KMS key.

Create the bucket in a `bootstrap/` root applied once before any backend exists. One state key per account and environment (`<project>/<env>/terraform.tfstate`); do not share a key across environments via workspaces, because a wrong `TF_WORKSPACE` then applies dev config to prod with prod credentials.

## Provider and mandatory tags

```hcl
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

provider "aws" {
  region = var.region
  # No access keys here. Credentials come from aws-vault / AWS_PROFILE / CI OIDC.
  assume_role {
    role_arn     = "arn:aws:iam::${var.account_id}:role/Deploy"   # explicit target account
    session_name = "terraform-${var.environment}"
  }
  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      Owner       = var.owner
      CostCenter  = var.cost_center
      ManagedBy   = "terraform"
      Repository  = var.repository
    }
  }
}
```

Why `assume_role` with the account ID in it: the plan fails fast if the credentials in the shell belong to the wrong account. Why `default_tags`: it applies to every taggable resource so tags cannot be forgotten ([resource tagging guide](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/guides/resource-tagging), [tagging best practices](https://docs.aws.amazon.com/whitepapers/latest/tagging-best-practices/tagging-best-practices.html)). Enforce the same keys with a tag policy in Organizations and activate them as cost allocation tags ([cost allocation tags](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/cost-alloc-tags.html)). Resource-level `tags = { Name = "..." }` merge on top.

Gotchas:

- Some resources ignore `default_tags` (for example `aws_autoscaling_group` needs explicit `tag` blocks with `propagate_at_launch`); check the provider docs per resource.
- Multi-Region: one `provider "aws"` block per Region with `alias`, passed to modules with `providers = { aws = aws.us_east_1 }`. CloudFront certificates and WAF for CloudFront must be in `us-east-1`.
- Multi-account: one provider alias per account, each with its own `assume_role`; never switch accounts by changing `AWS_PROFILE` mid-apply.
- Pin the provider with `~>` at the major level and commit `.terraform.lock.hcl`.

## Secrets and sensitive values

- Never put secrets in `.tfvars`, `locals` or `user_data`. Applications read them at runtime from Secrets Manager or SSM SecureString via IAM ([Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html), [Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html)).
- Prefer resources that generate secrets server-side (`manage_master_user_password = true` on RDS/Aurora) so the value never exists locally.
- When a value must pass through Terraform (initial credential for a third-party provider), inject it from agenix and mark it `sensitive = true`:
  `secret-run --only DD_API_KEY -- terraform apply -var "datadog_api_key=$DD_API_KEY"`. It still lands in state, which is why the state bucket is locked down.
- Outputs carrying credentials are `sensitive = true`; never dump `terraform output -json` into CI logs.

## Modules

- Use the [AWS Integration & Automation](https://github.com/aws-ia) modules and the `terraform-aws-modules` family before writing your own; pin exact versions.
- No provider blocks inside modules; the root passes providers. Modules take `tags = {}` and merge with resource-specific tags.
- Validate AWS-shaped inputs with `validation` blocks (CIDR, Region, allowed instance families) so mistakes fail at plan, not apply.
- Generate module docs with `terraform-docs markdown table . > README.md`.

## AWS patterns worth copying

```hcl
# Account baseline (bootstrap/)
resource "aws_ebs_encryption_by_default" "this" { enabled = true }
resource "aws_s3_account_public_access_block" "this" {
  block_public_acls = true; block_public_policy = true
  ignore_public_acls = true; restrict_public_buckets = true
}

# EC2 with IMDSv2 required
resource "aws_launch_template" "app" {
  metadata_options { http_tokens = "required"; http_endpoint = "enabled" }
}

# EKS: private endpoint, access entries, audit logs
resource "aws_eks_cluster" "this" {
  access_config { authentication_mode = "API" }
  vpc_config    { endpoint_private_access = true; endpoint_public_access = false }
  enabled_cluster_log_types = ["api", "audit", "authenticator"]
}

# S3 bucket: private, versioned, encrypted
resource "aws_s3_bucket_versioning" "data" { versioning_configuration { status = "Enabled" } }
resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  rule { apply_server_side_encryption_by_default { sse_algorithm = "aws:kms"; kms_master_key_id = aws_kms_key.data.arn } }
}
resource "aws_s3_bucket_public_access_block" "data" {
  block_public_acls = true; block_public_policy = true
  ignore_public_acls = true; restrict_public_buckets = true
}

# RDS in prod
resource "aws_db_instance" "this" {
  multi_az = true; storage_encrypted = true; deletion_protection = true
  manage_master_user_password = true; publicly_accessible = false
  lifecycle { prevent_destroy = true }
}
```

Sources: [EBS encryption](https://docs.aws.amazon.com/ebs/latest/userguide/EBSEncryption.html), [IMDS](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html), [EKS endpoint access](https://docs.aws.amazon.com/eks/latest/userguide/cluster-endpoint.html), [access entries](https://docs.aws.amazon.com/eks/latest/userguide/access-entries.html), [EKS add-ons](https://docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html), [RDS best practices](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_BestPractices.html). For clusters where you do not want to manage nodes use [EKS Auto Mode](https://docs.aws.amazon.com/eks/latest/userguide/automode.html). Keep the cluster within the [supported Kubernetes versions](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html); extended support costs more.

## AWS gotchas

- **Eventual consistency**: IAM roles and policies take seconds to propagate; a Lambda or EKS resource created immediately after may fail with `InvalidParameterValueException`. Add `depends_on` on the policy attachment, not just the role.
- **Deleting VPCs** fails while ENIs from Lambda, RDS or endpoints remain; destroy those resources first or the run hangs for 20 minutes.
- **S3 bucket names are global** and cannot be renamed; include the account ID and Region in the name.
- **Security group rule ordering**: use `aws_vpc_security_group_ingress_rule`/`egress_rule` resources instead of inline `ingress {}` blocks so rules can be added without replacing the group.
- **`aws_iam_policy_document` data source** is the way to write policies; JSON heredocs hide typos until apply.
- **Service quotas** (VPCs per Region, EIPs, Lambda concurrency) fail at apply time; check before large rollouts ([Service Quotas](https://docs.aws.amazon.com/servicequotas/latest/userguide/intro.html)).
- **`force_destroy`** on buckets and `skip_final_snapshot` on databases belong only in non-prod tfvars.

## Local loop and CI gates

```bash
terraform fmt -recursive -check
terraform init -backend=false && terraform validate
tflint --init && tflint --recursive              # AWS ruleset: invalid instance types, deprecated args, missing tags
trivy config --severity HIGH,CRITICAL --exit-code 1 .
infracost breakdown --path envs/prod --format table
terraform plan -out=plan.tfplan                  # aws-vault wrapper injects credentials
terraform show -json plan.tfplan | jq -r '.resource_changes[] | select(.change.actions | index("delete")) | .address'   # list deletions
```

CI assumes an OIDC deploy role ([OIDC](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html)); `plan` on PR, `apply` only from the default branch with manual approval for prod. Post the `infracost diff` and the plan summary as PR comments. Run a nightly `terraform plan -detailed-exitcode` per environment; exit code 2 means drift.

## Review rules (AWS-specific)

- [ ] Backend has `encrypt = true` and `use_lockfile = true`; no `dynamodb_table`, no `access_key`/`secret_key`.
- [ ] Provider has `assume_role` with the target account and `default_tags` with the mandatory set.
- [ ] No `aws_iam_user`/`aws_iam_access_key`; policies via `aws_iam_policy_document` with scoped resources (see [iam.md](iam.md)).
- [ ] Security groups: no `0.0.0.0/0` ingress beyond 80/443 on load balancers ([VPC security best practices](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-best-practices.html)).
- [ ] All data stores encrypted; S3 buckets private with versioning where data matters; RDS `multi_az`, `deletion_protection`, `manage_master_user_password` in prod.
- [ ] EC2 `http_tokens = "required"`; EKS private endpoint and `authentication_mode = "API"`.
- [ ] `prevent_destroy` on state buckets, KMS keys and production databases.
- [ ] `trivy config` and `tflint` clean; `infracost` diff acknowledged; plan shows no unexpected `destroy`/`replace`.

## CloudFormation / CDK / SAM

If the project is CloudFormation-based, lint with `cfn-lint` before every deploy and follow [CloudFormation best practices](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html). [CDK](https://docs.aws.amazon.com/cdk/v2/guide/home.html) and [SAM](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html) are opt-in packages (see SKILL.md); do not manage the same resource from both CDK and Terraform.
