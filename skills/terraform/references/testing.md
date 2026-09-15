# Testing and static checks

Order, cheapest first. Git hooks already run `terraform fmt` and `tflint` on commit; CI runs everything.

```bash
terraform fmt -recursive -check          # formatting
terraform init -backend=false            # providers/modules only, no state access
terraform validate                       # syntax, types, references
tflint --recursive                       # provider-aware lint
trivy config --severity HIGH,CRITICAL .  # misconfiguration + secrets
terraform test                           # module logic, mocked or real
terraform-docs .                         # README up to date (CI: --output-check)
infracost diff ...                       # cost delta on the PR
```

## `terraform fmt` and `terraform validate`

- `fmt -check` exits non-zero on unformatted files; `-recursive` covers modules ([fmt](https://developer.hashicorp.com/terraform/cli/commands/fmt)). Formatting is not negotiable; it removes style from review.
- `validate` needs an initialised directory; use `terraform init -backend=false` so it works without credentials or state ([validate](https://developer.hashicorp.com/terraform/cli/commands/validate)). `-json` for machine output.
- `validate` catches references and types, not provider-side rules (invalid instance types, bad CIDRs). Those need `validation` blocks, `tflint` rulesets, or a plan.

## `terraform test` [1.6]

Native test framework: `*.tftest.hcl` files in `tests/` (or next to the config), each with `run` blocks that `plan` or `apply` the configuration and `assert` on results ([tests](https://developer.hashicorp.com/terraform/language/tests), [test command](https://developer.hashicorp.com/terraform/cli/commands/test)).

```hcl
# modules/hardened-bucket/tests/basic.tftest.hcl
mock_provider "aws" {}                 # Terraform >= 1.7: no credentials, no real resources

variables {
  name        = "test-logs"
  environment = "dev"
}

run "rejects_bad_environment" {
  command = plan
  variables { environment = "qa" }
  expect_failures = [var.environment]
}

run "bucket_is_private" {
  command = plan
  assert {
    condition     = aws_s3_bucket_public_access_block.this.block_public_acls == true
    error_message = "Public ACLs must be blocked."
  }
}

run "naming_is_stable" {
  command = plan
  assert {
    condition     = aws_s3_bucket.this.bucket == "test-logs-dev"
    error_message = "Bucket name must be <name>-<environment>."
  }
}
```

Guidance ([mocking](https://developer.hashicorp.com/terraform/language/tests/mocking)):

- **Unit tests**: `command = plan` + `mock_provider` [1.7]. Fast, credential-free, run on every PR. Use `mock_resource`/`mock_data` `defaults` to supply computed values the logic depends on (ARNs, IDs); `override_resource`/`override_data`/`override_module` to stub a specific object. `override_during = plan` [1.11] applies overrides at plan time.
- **Integration tests**: `command = apply` against a real sandbox account, in a nightly job, with `secret-run` supplying credentials. Terraform destroys what it created at the end of the file; keep runs small and name resources with a random suffix.
- Test the module's *logic*: naming, conditionals, validation, counts, tags. Do not assert that the provider works.
- `terraform test -filter=tests/basic.tftest.hcl` for one file; `-junit-xml=report.xml` [1.11 GA] for CI reporters; `-verbose` to print plans when debugging.
- Put `validation`, `precondition`, `postcondition` and `check` blocks in the config first; tests then only need `expect_failures` to prove they fire.

## tflint

Provider-aware linting: deprecated arguments, invalid instance types/regions/SKUs, unused declarations, missing `required_providers`, naming ([tflint](https://github.com/terraform-linters/tflint), [configuration](https://github.com/terraform-linters/tflint/blob/master/docs/user-guide/config.md)).

```hcl
# .tflint.hcl at repo root
config {
  call_module_type = "local"        # lint local modules; skip registry modules
}

plugin "terraform" {                # bundled ruleset
  enabled = true
  preset  = "recommended"
}

plugin "aws" {                      # one per provider in use: aws | azurerm | google
  enabled = true
  version = "0.48.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}
```

```bash
tflint --init                       # installs the plugins in .tflint.hcl (cache in CI)
tflint --recursive                  # every root and module
```

Rulesets: [terraform](https://github.com/terraform-linters/tflint-ruleset-terraform) (bundled), [aws](https://github.com/terraform-linters/tflint-ruleset-aws), [azurerm](https://github.com/terraform-linters/tflint-ruleset-azurerm), [google](https://github.com/terraform-linters/tflint-ruleset-google). Pin the plugin `version`; bump in its own PR. Disable a rule with a `rule "<name>" { enabled = false }` block and a comment explaining why, never with a blanket `force = true`.

## trivy config

Scans HCL (and plan JSON) for misconfigurations - public buckets, open security groups, missing encryption, weak TLS - and for hard-coded secrets ([misconfiguration scanning](https://trivy.dev/latest/docs/scanner/misconfiguration/), [Terraform coverage](https://trivy.dev/latest/docs/coverage/iac/terraform/)).

```bash
trivy config --severity HIGH,CRITICAL --exit-code 1 .          # fail CI on high/critical
trivy config --tf-vars envs/prod/terraform.tfvars envs/prod     # resolve variables
terraform show -json plan.tfplan > tfplan.json
trivy config tfplan.json                                        # scan the real plan (values resolved)
```

Scanning the plan JSON is more accurate than scanning HCL because values are resolved; do it on the PR plan. Plan JSON contains secrets: scan it in the job and delete it, never upload it as an artifact. Suppress a finding inline with `#trivy:ignore:<ID>` plus a reason, and keep a `.trivyignore` only for accepted risks with an owner and expiry.

## terraform-docs

Generates the inputs/outputs/providers tables into the README so documentation cannot drift from code ([terraform-docs](https://terraform-docs.io/user-guide/introduction/), [configuration](https://terraform-docs.io/user-guide/configuration/)).

```yaml
# .terraform-docs.yml
formatter: markdown table
recursive:
  enabled: true
  path: modules
output:
  file: README.md
  mode: inject
  template: |-
    <!-- BEGIN_TF_DOCS -->
    {{ .Content }}
    <!-- END_TF_DOCS -->
```

```bash
terraform-docs .                    # local: inject
terraform-docs --output-check .     # CI: fail if README is stale
```

Every module and root has the markers. Write the prose above the markers by hand; let the tool own the tables.

## infracost

Shows the monthly cost of a plan and the delta a PR introduces, so cost is reviewed like any other change ([infracost](https://www.infracost.io/docs/), [CI/CD integrations](https://www.infracost.io/docs/integrations/cicd/), [v0.10 CLI guide](https://www.infracost.io/docs/guides/v0.10_migration/)).

```bash
# baseline from the target branch (CI does this on a checkout of main)
infracost breakdown --path envs/prod --format json --out-file infracost-base.json
# on the PR branch
infracost diff --path envs/prod --compare-to infracost-base.json --format json --out-file infracost.json
infracost comment github --path infracost.json --repo "$REPO" --pull-request "$PR" --github-token "$TOKEN"
```

`--terraform-var-file` points at the environment's `terraform.tfvars`. `infracost breakdown --path plan.json` works on a plan JSON when HCL parsing misses dynamic values. The API key is a secret: `secret-add INFRACOST_API_KEY`, then `secret-run --only INFRACOST_API_KEY -- infracost ...`. Usage-based resources (data transfer, requests) need a `infracost-usage.yml`; without it treat those lines as lower bounds.

## CI matrix

| Check | Where | Blocks merge |
|---|---|---|
| `fmt -check`, `validate`, `tflint` | pre-commit + PR | yes |
| `trivy config` (HCL) | PR | HIGH/CRITICAL |
| `terraform test` (mocked, plan) | PR | yes |
| `terraform plan -out` + `trivy config` on plan JSON | PR, per environment | yes |
| `infracost diff` | PR comment | advisory, reviewer decides |
| `terraform-docs --output-check` | PR | yes |
| `terraform test` (apply, sandbox) | nightly | alerts |
| `plan -refresh-only -detailed-exitcode` | scheduled | alerts on drift |
