# Project structure

Baseline: [HashiCorp style guide](https://developer.hashicorp.com/terraform/language/style). Provider-specific backend/auth/tag blocks: see the provider skill's `references/terraform.md`.

## Root modules vs child modules

- A **root module** is a directory you run `terraform init/plan/apply` in. It owns a backend, a state file, provider configuration and credentials. One per environment (and per deployable unit if the environment is large).
- A **child module** is called from a root with a `module` block. It has no `backend` and no `provider` configuration blocks (only `required_providers`), so it can be reused anywhere ([module development](https://developer.hashicorp.com/terraform/language/modules/develop)).
- Keep the tree flat: root -> one level of modules. Deep nesting hides dependencies and makes refactoring painful ([composition](https://developer.hashicorp.com/terraform/language/modules/develop/composition)).

## Layout

```
infra/
├── bootstrap/               # state bucket/container + CI identity; applied once
├── modules/                 # local reusable modules, ./modules/<name>
│   └── network/
│       ├── main.tf
│       ├── variables.tf
│       ├── outputs.tf
│       ├── README.md        # terraform-docs injected
│       └── tests/           # *.tftest.hcl
└── envs/
    ├── dev/                 # root module: own backend key, own credentials
    │   ├── backend.tf
    │   ├── terraform.tf     # required_version + required_providers
    │   ├── providers.tf
    │   ├── main.tf
    │   ├── variables.tf
    │   ├── outputs.tf
    │   ├── locals.tf
    │   ├── terraform.tfvars # non-secret values only
    │   └── .terraform.lock.hcl
    ├── staging/
    └── prod/
```

File names follow the style guide ([file names](https://developer.hashicorp.com/terraform/language/style#file-names)): `backend.tf`, `main.tf`, `outputs.tf`, `providers.tf`, `terraform.tf`, `variables.tf`, `locals.tf`. Split `main.tf` by concern (`network.tf`, `compute.tf`) only when it passes a few hundred lines. Variables and outputs alphabetical.

Why a `bootstrap/` root: the backend must exist before any backend-using root can `init`. Bootstrap is applied once, with local state committed or moved to the bucket afterwards; keep it tiny.

## Per-environment directories vs workspaces

**Default: per-environment directories** (`envs/<env>/`). Each has its own backend, state, variable values, credentials and can pin a different module version. Terraform's own guidance: workspaces are "not appropriate for system decomposition or deployments requiring separate credentials and access controls"; for prod vs dev use separate configurations with their own backends ([workspaces](https://developer.hashicorp.com/terraform/language/state/workspaces), [workspace use cases](https://developer.hashicorp.com/terraform/cli/workspaces#use-cases)).

The cost is duplication of root-level wiring. Keep roots thin: backend + provider + a handful of `module` blocks + tfvars. If the roots diverge in structure, that is a signal the environments are actually different systems, not that you need workspaces.

**Workspaces fit** short-lived copies of the *same* configuration under the *same* credentials: a feature-branch preview stack you destroy after merge, or parallel test instances. Never `terraform workspace select prod` from a laptop; if a root uses workspaces, assert the expected one in a `precondition` or `check` block.

## Naming

From the [style guide](https://developer.hashicorp.com/terraform/language/style#resource-naming):

- `snake_case` for every identifier; descriptive nouns; do not repeat the resource type in the name (`resource "aws_instance" "web"`, not `"web_instance"`).
- Singular for one instance, plural when `count`/`for_each` produce a set.
- The `Name`/tag/display name of the cloud object is built from `var.project`, `var.environment` and a role, e.g. `"${var.project}-${var.environment}-web"`. Never hard-code the environment in a name; it must come from the root.
- Modules published to a registry: repository `terraform-<PROVIDER>-<NAME>` ([publishing](https://developer.hashicorp.com/terraform/registry/modules/publish)).

## `terraform.tfvars` handling

Precedence, lowest to highest: variable `default` -> `TF_VAR_*` env -> `terraform.tfvars` -> `terraform.tfvars.json` -> `*.auto.tfvars` -> `-var`/`-var-file` ([variables](https://developer.hashicorp.com/terraform/language/values/variables#variable-definition-precedence)).

- `terraform.tfvars` in each root is **committed** and holds only non-secret, environment-specific values (sizes, regions, feature flags, CIDRs). Because it is committed, it is reviewable, which is the point.
- Secrets never go into any `.tfvars`. Inject them with `secret-run --only NAME -- terraform plan ...` as `TF_VAR_<name>` or provider env vars (see SKILL.md, Secrets).
- Do not use `*.auto.tfvars` for overrides; it silently wins over `terraform.tfvars` and people forget it exists. If a developer needs a local override, use `-var-file=local.tfvars` with `local.tfvars` git-ignored.
- Add `.gitignore` entries: `.terraform/`, `*.tfstate*`, `*.tfplan`, `local.tfvars`, `crash.log`. Never ignore `.terraform.lock.hcl`.

## `required_version` and `required_providers`

```hcl
# terraform.tf (root module)
terraform {
  required_version = "~> 1.11"          # minimum for write-only args; bump deliberately

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"                 # roots: ~> upper and lower bound
    }
  }
}
```

- Root modules use `~>` on providers to bound both sides; reusable modules use only `>=` minimums so consumers control the upper bound ([provider requirements](https://developer.hashicorp.com/terraform/language/providers/requirements#best-practices-for-provider-versions), [version constraints](https://developer.hashicorp.com/terraform/language/expressions/version-constraints)).
- Pin the Terraform binary with `required_version` so a developer on an older release cannot write a state that CI cannot read ([style guide, version pinning](https://developer.hashicorp.com/terraform/language/style#version-pinning)). The devenv shell pins the same major.minor.
- Upgrade providers on purpose: `terraform init -upgrade`, then re-lock (below), then plan and read the diff. Never let `init` pick the newest at random on a fresh clone; the lock file prevents that.

## `.terraform.lock.hcl`

Commit it. It records the exact provider version and checksums selected so every `init` reproduces the same providers, and the diff is reviewable like code ([dependency lock file](https://developer.hashicorp.com/terraform/language/files/dependency-lock)).

Problem: a plain `terraform init` records checksums only for the platform it ran on (when installing from a mirror) and a teammate or CI on another OS/arch then fails checksum verification. Fix: pre-populate every platform you use ([providers lock](https://developer.hashicorp.com/terraform/cli/commands/providers/lock)):

```bash
terraform providers lock \
  -platform=linux_amd64 \
  -platform=linux_arm64 \
  -platform=darwin_arm64 \
  -platform=darwin_amd64
```

Run it after any provider version change, in every root, and commit the result. Review the signing-key output before committing. In CI use `terraform init -lockfile=readonly` so a pipeline can never silently change the lock ([init](https://developer.hashicorp.com/terraform/cli/commands/init)).

Checklist when adding a root:

- [ ] `backend.tf` with the provider skill's backend, unique `key`/prefix for this environment.
- [ ] `terraform.tf` with `required_version` and `required_providers`.
- [ ] `terraform.tfvars` with non-secret values; secrets via `secret-run`.
- [ ] `.terraform.lock.hcl` generated with all platforms and committed.
- [ ] README with `terraform-docs` markers.
