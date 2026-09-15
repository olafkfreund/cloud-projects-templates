---
name: terraform
description: Generic Terraform (HCL, IaC) practice for every project in this repo - the only IaC CLI here is terraform. Use when writing, reviewing, refactoring or running Terraform - root modules vs child modules, project structure, per-environment directories, terraform.tfvars, required_version and required_providers pinning, .terraform.lock.hcl with multi-platform hashes, remote backend and state locking, state encryption and blast radius, import blocks, moved and removed blocks, drift detection with plan -refresh-only, terraform_remote_state, module design and versioning, terraform validate, fmt, terraform test with mock providers, tflint, trivy config scanning, terraform-docs, infracost, CI/CD with saved plan files and OIDC, HCP Terraform, ephemeral values and write-only arguments, secrets via agenix secret-run, and the terraform-mcp-server MCP configuration. Provider-specific rules live in the aws, azure, gcp, oci and kubernetes skills.
---

# Terraform

Generic Terraform rules for this project. `terraform` is the only IaC CLI here (no OpenTofu). Provider-specific conventions (backend choice, tags, auth, provider pinning) live in the provider skills: [../aws/references/terraform.md](../aws/references/terraform.md), [../azure](../azure/SKILL.md), [../gcp](../gcp/SKILL.md), [../oci/references/terraform.md](../oci/references/terraform.md), [../kubernetes](../kubernetes/SKILL.md). Read the matching one before touching provider resources.

Style baseline for everything below: the [HashiCorp style guide](https://developer.hashicorp.com/terraform/language/style). Deviate only with a stated reason.

## Non-negotiables

1. **Remote, locked, encrypted state.** Never local state for anything shared; never edit state by hand ([state](https://developer.hashicorp.com/terraform/language/state)). See [references/state.md](references/state.md).
2. **Pin everything.** `required_version`, `required_providers` with `~>` in root modules, module `version` constraints, and a committed `.terraform.lock.hcl` with hashes for every platform the team and CI run on ([dependency lock](https://developer.hashicorp.com/terraform/language/files/dependency-lock)). See [references/project-structure.md](references/project-structure.md).
3. **One root module per environment, own backend, own credentials.** Workspaces do not give separate access control ([workspace use cases](https://developer.hashicorp.com/terraform/cli/workspaces#use-cases)).
4. **Plan is a saved artifact; apply consumes it.** `terraform plan -out=plan.tfplan`, review, then `terraform apply plan.tfplan` ([apply](https://developer.hashicorp.com/terraform/cli/commands/apply)). Plan files are sensitive: never commit or leave them in CI logs/artifacts without access control ([plan -out](https://developer.hashicorp.com/terraform/cli/commands/plan)).
5. **No secrets in HCL, tfvars, or state where avoidable.** See [Secrets](#secrets).
6. **Refactor with `moved`/`removed`/`import` blocks, not `state mv`/`rm` by hand.** Review the change in a PR, not in a terminal ([refactoring](https://developer.hashicorp.com/terraform/language/modules/develop/refactoring)).
7. **Lint and scan before commit.** Git hooks run `terraform fmt` and `tflint`; CI adds `validate`, `terraform test`, `trivy config`, `infracost`. See [references/testing.md](references/testing.md).
8. **MCP is registry-only by default.** Write access to HCP Terraform is a per-project opt-in. See [references/mcp.md](references/mcp.md).

## Daily workflow

```bash
cd infra/envs/dev
terraform init                                   # -lockfile=readonly in CI
terraform fmt -recursive -check && terraform validate
tflint --recursive
trivy config --severity HIGH,CRITICAL .
secret-run --only <NAME> -- terraform plan -out=plan.tfplan   # credentials injected per command
terraform show plan.tfplan                       # read the whole thing
infracost diff --path . --compare-to infracost-base.json      # optional, see testing.md
secret-run --only <NAME> -- terraform apply plan.tfplan
```

Why saved plans: the apply executes exactly what was reviewed, without re-planning or prompting ([apply](https://developer.hashicorp.com/terraform/cli/commands/apply)).

## Before you run apply

- [ ] Correct directory and backend: `terraform workspace show` is `default`; the backend `key`/prefix names this environment.
- [ ] Identity verified against the target account/subscription/project (see the provider skill for the command).
- [ ] The plan was produced from the committed HEAD, not a dirty tree, and is less than an hour old.
- [ ] Every `destroy` and `replace` (`-/+`) in the plan is intended and named in the PR.
- [ ] No unexpected drift: `terraform plan -refresh-only` is clean or its changes are understood ([plan modes](https://developer.hashicorp.com/terraform/cli/commands/plan#planning-modes)).
- [ ] Lock file unchanged (or the provider bump is the point of the PR).
- [ ] `tflint`, `trivy config`, `terraform test` green; cost diff reviewed.
- [ ] Production: plan came from CI, apply was approved by someone other than the author ([references/ci-cd.md](references/ci-cd.md)).

## Secrets

State and plan files contain every value Terraform knows, in cleartext ([sensitive data in state](https://developer.hashicorp.com/terraform/language/state/sensitive-data)). Therefore:

- **Never put a secret in `terraform.tfvars`, `*.auto.tfvars`, or HCL.** Those files are committed or end up in artifacts.
- **Store tokens with agenix**: `secret-add NAME`. Inject per command: `secret-run --only NAME -- terraform plan -out=plan.tfplan`. Expose them as `TF_VAR_<name>` (variable input) or the provider's own env var (`AWS_*`, `ARM_*`, `GOOGLE_*`, `OCI_*`, `TFE_TOKEN`). Never `echo`, log, or write a secret to disk; never pass it as `-var` (it lands in shell history and process lists).
- **Mark inputs `sensitive = true`** so they are redacted in output (still stored in state) ([variable block](https://developer.hashicorp.com/terraform/language/block/variable)).
- **Prefer values that never touch state** (min versions in brackets): `ephemeral = true` on variables/outputs [1.10], `ephemeral` resources [1.10], and provider write-only arguments such as `password_wo` + `password_wo_version` [1.11] ([manage sensitive data](https://developer.hashicorp.com/terraform/language/manage-sensitive-data), [write-only](https://developer.hashicorp.com/terraform/language/manage-sensitive-data/write-only)). Use them whenever the provider supports them; the version companion argument is how you rotate.
- **Encrypt and restrict the backend** (KMS/CMK, versioning, least-privilege read access, audit logging) - state is the crown jewel ([references/state.md](references/state.md)).
- Runtime secrets belong in the cloud secret manager, generated in Terraform via ephemeral/write-only patterns, never as an `output` unless `sensitive = true` and genuinely needed.

## Review checklist

- [ ] `terraform fmt -check`, `validate`, `tflint --recursive`, `trivy config` (no HIGH/CRITICAL) pass.
- [ ] `required_version`, `required_providers` (`~>` in roots, `>=` in reusable modules) and module `version` present ([provider requirements](https://developer.hashicorp.com/terraform/language/providers/requirements)).
- [ ] `.terraform.lock.hcl` committed, covers `linux_amd64` and `darwin_arm64` (plus any other platform in use).
- [ ] Every variable has `type` and `description`; every output has `description`; secrets are `sensitive`/`ephemeral` ([style guide](https://developer.hashicorp.com/terraform/language/style)).
- [ ] No `terraform_remote_state` where a provider data source or published output works ([remote state data](https://developer.hashicorp.com/terraform/language/state/remote-state-data)).
- [ ] Resource renames use `moved`; removals from management use `removed`; adoption uses `import` blocks with the generated config reviewed.
- [ ] New module only if it raises the abstraction level; no single-resource wrappers ([module development](https://developer.hashicorp.com/terraform/language/modules/develop)).
- [ ] `terraform test` covers module logic with mocks; plan-time checks use `validation`/`precondition`/`check`.
- [ ] Cost diff reviewed; no unexplained jump.
- [ ] Provider-skill checklist applied for the touched provider.

## Tooling in the devenv shell

| Tool | Use | Reference |
|---|---|---|
| `terraform` | init/plan/apply/test/fmt/validate | [CLI](https://developer.hashicorp.com/terraform/cli) |
| `tflint` | provider-aware linting, runs on commit | [testing.md](references/testing.md) |
| `trivy config` | IaC misconfiguration and secret scanning | [testing.md](references/testing.md) |
| `terraform-docs` | README inputs/outputs tables | [testing.md](references/testing.md) |
| `infracost` | cost breakdown and PR diff | [testing.md](references/testing.md) |
| `terraform-mcp-server` | registry docs/module lookup for the agent | [mcp.md](references/mcp.md) |

## References

- [references/project-structure.md](references/project-structure.md) - layout, roots vs modules, environments, tfvars, pinning, lock file.
- [references/state.md](references/state.md) - backends, locking, encryption, isolation, import/moved/removed, drift.
- [references/modules.md](references/modules.md) - module design, inputs/outputs/validation, versioning, when not to write one.
- [references/testing.md](references/testing.md) - validate, fmt, terraform test, tflint, trivy, terraform-docs, infracost.
- [references/ci-cd.md](references/ci-cd.md) - plan on PR, saved plans, gated apply, OIDC, HCP Terraform.
- [references/mcp.md](references/mcp.md) - terraform-mcp-server configuration and opt-in write access.
