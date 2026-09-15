# IAM: identity, least privilege, federation

Source of record: [Security best practices in IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html). Everything below follows from it.

## Identity model

| Who | How they authenticate | Never |
|---|---|---|
| Humans | IAM Identity Center + corporate IdP + MFA, permission sets per job ([Identity Center](https://docs.aws.amazon.com/singlesignon/latest/userguide/what-is.html)) | IAM users, console passwords, access keys |
| CI/CD | OIDC federation (GitHub Actions, GitLab) into a deploy role ([OIDC](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html)) | Access keys in CI secrets |
| EC2 / ECS / Lambda | Instance profile, task role, execution role ([temporary credentials](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp.html)) | Credentials in user data or env vars |
| EKS pods | EKS Pod Identity (preferred) or IRSA ([Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html), [IRSA](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html)) | Node role shared by all pods |
| Third parties | Cross-account role with `ExternalId` ([third-party access](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_common-scenarios_third-party.html)) | Sharing keys |
| AI agents (MCP) | `aws-vault exec <ro-profile> -- claude`, role with `ReadOnlyAccess`/`ViewOnlyAccess` ([mcp.md](mcp.md)) | Admin profiles |

Why no access keys: they never expire, get committed, and appear in every breach write-up. Roles issue credentials that expire in 1–12 hours ([access keys guidance](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html), [programmatic access](https://docs.aws.amazon.com/IAM/latest/UserGuide/security-creds-programmatic-access.html)).

Local workflow: `aws sso login --profile <p>` then `aws-vault exec <p> -- <cmd>`. `aws-vault` keeps the session in the OS keyring and injects short-lived credentials only into the child process ([aws-vault](https://github.com/99designs/aws-vault)).

## Root user

- Hardware MFA, no access keys, email is a monitored distribution list.
- Used only for the [tasks that require root](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_mfa.html); an SCP denies root actions in member accounts (see [landing-zone.md](landing-zone.md)).
- Alarm on any root sign-in via CloudTrail.

## Writing least-privilege policies

Policy evaluation is deny-by-default; explicit denies always win ([evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html)).

Rules:

1. **Actions**: list them. Wildcards only as service-scoped read prefixes (`s3:Get*`, `s3:List*`), never `*` or `s3:*` in production.
2. **Resources**: ARNs, not `*`. Actions that genuinely require `*` (for example `ec2:DescribeInstances`) go in a separate statement so the exception is visible.
3. **Conditions**: add at least one where the API supports it: `aws:PrincipalOrgID`, `aws:SourceVpce`, `aws:RequestedRegion`, `aws:ResourceTag/...`, `aws:MultiFactorAuthPresent` ([global condition keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_aws-condition-keys.html), [condition operators](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_condition_operators.html)).
4. **`iam:PassRole`**: always scope to the exact role ARN and add `iam:PassedToService`. Unscoped PassRole is privilege escalation.
5. **Managed policies** for baselines (`ReadOnlyAccess`), customer managed policies for workloads, inline only for one-off trust exceptions ([managing policies](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_manage-attach-detach.html)).
6. **Validate** with [Access Analyzer policy validation](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html) (`aws accessanalyzer validate-policy`) and fix every SECURITY_WARNING.
7. **Generate then trim**: start from CloudTrail activity using [policy generation](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-generation.html), then remove what [last-accessed data](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_last-accessed.html) shows is unused.
8. **Permissions boundaries** on any role that can create roles (CI, platform teams) so delegated admins cannot escalate ([boundaries](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html)).

### Pattern: application role

```hcl
data "aws_iam_policy_document" "app" {
  statement {
    sid       = "ReadConfig"
    actions   = ["ssm:GetParameter", "ssm:GetParametersByPath"]
    resources = ["arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project}/${var.environment}/*"]
  }
  statement {
    sid       = "ReadSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.db.arn]
  }
  statement {
    sid       = "WriteOwnBucketPrefix"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.data.arn}/${var.project}/*"]
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["true"]
    }
  }
}
```

### Pattern: CI deploy role trust (GitHub Actions OIDC)

```hcl
data "aws_iam_policy_document" "ci_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:<org>/<repo>:ref:refs/heads/main", "repo:<org>/<repo>:environment:prod"]
    }
  }
}
```

Why the `sub` condition: without it any repository on GitHub can assume the role ([OIDC providers](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html)).

### Pattern: cross-account role locked to the organization

```hcl
condition {
  test     = "StringEquals"
  variable = "aws:PrincipalOrgID"
  values   = [var.org_id]
}
```

Add `sts:ExternalId` when the caller is outside your organization ([principal element](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_principal.html)).

## Identity Center permission sets

Standard set per account ([permission sets](https://docs.aws.amazon.com/singlesignon/latest/userguide/permissionsetsconcept.html)):

| Permission set | Policy | Session | Who |
|---|---|---|---|
| `ReadOnly` | `ReadOnlyAccess` | 8 h | everyone, AI agents |
| `Developer` | customer managed: deploy to own workload, no IAM writes | 4 h | engineers in NonProd |
| `PowerUser` | `PowerUserAccess` + boundary | 2 h | engineers in Prod on-call |
| `Admin` | `AdministratorAccess` | 1 h | platform team, break-glass, alarmed |

Break-glass admin use raises a CloudTrail alarm and is reviewed afterwards.

## EKS specifics

- Cluster access via [access entries](https://docs.aws.amazon.com/eks/latest/userguide/access-entries.html), not the `aws-auth` ConfigMap.
- Pods get AWS permissions via [Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html); one role per service account, no node-role permissions beyond the EKS-required managed policies.
- Follow the [EKS security best practices](https://docs.aws.amazon.com/eks/latest/best-practices/security.html).

## Review rules (block the PR)

- `"Action": "*"` or `"Resource": "*"` without a comment linking the AWS doc that requires it.
- `iam:*`, `iam:PassRole` on `*`, `sts:AssumeRole` on `*`.
- `aws_iam_user`, `aws_iam_access_key`, `aws_iam_user_login_profile` resources.
- Trust policy with `"Principal": {"AWS": "*"}` or an OIDC trust without a `sub` condition.
- Policies attached directly to users; MFA not required on human-facing roles.
- `NotAction` combined with `Allow` (grants everything else).
- Secrets or key IDs in `tfvars`, `locals`, or `user_data`.

## Audit commands

```bash
aws-vault exec <p> -- aws iam get-account-summary
aws-vault exec <p> -- aws iam list-users                         # should be empty
aws-vault exec <p> -- aws iam generate-credential-report && aws-vault exec <p> -- aws iam get-credential-report --query Content --output text | base64 -d
aws-vault exec <p> -- aws accessanalyzer validate-policy --policy-type IDENTITY_POLICY --policy-document file://policy.json
aws-vault exec <p> -- aws accessanalyzer list-findings --analyzer-arn <arn> --filter '{"status":{"eq":["ACTIVE"]}}'
aws-vault exec <p> -- aws iam get-role --role-name <r> --query 'Role.RoleLastUsed'
```
