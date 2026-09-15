## AWS

- **Skill:** `.claude/skills/aws`, covering Well-Architected, landing zone, IAM and Terraform.
- **Login:** use IAM Identity Center (`aws configure sso`), then `aws-vault exec <profile> -- claude`, or `export AWS_PROFILE=<profile>`. No long-lived access keys.
- **MCP:** `aws` runs with `READ_OPERATIONS_ONLY=true`, and `aws-docs` needs no credentials. Use a read-only role for agent sessions.
