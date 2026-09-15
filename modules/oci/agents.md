## Oracle Cloud (OCI)

- **Skill:** `.claude/skills/oci`, covering the best-practices framework, the CIS Landing Zone, IAM policies and Terraform.
- **Login:** `oci session authenticate --profile-name <profile>`. Prefer security tokens over API keys.
- **MCP:** `oci` has **no read-only mode**. Set `OCI_CLI_PROFILE` to a profile whose group has only `inspect`/`read` policies. See `.claude/skills/oci/references/iam.md`.
