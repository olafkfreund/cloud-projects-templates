## Google Cloud

- **Skill:** `.claude/skills/gcp`, covering Well-Architected, landing zones, IAM and Terraform.
- **Login:** `gcloud auth login` and `gcloud auth application-default login`. No service account keys; use impersonation or Workload Identity Federation.
- **MCP:** `gcloud` has **no read-only mode**. It is limited by the command allowlist in `.mcp/gcloud-allow.json`. Run agent sessions as a Viewer-only service account: `gcloud config set auth/impersonate_service_account <sa>`.
