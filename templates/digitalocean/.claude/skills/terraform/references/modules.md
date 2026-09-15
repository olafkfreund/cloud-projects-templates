# Modules

Source: [module development](https://developer.hashicorp.com/terraform/language/modules/develop), [composition](https://developer.hashicorp.com/terraform/language/modules/develop/composition), [standard structure](https://developer.hashicorp.com/terraform/language/modules/develop/structure), [style guide](https://developer.hashicorp.com/terraform/language/style).

## When NOT to write a module

HashiCorp: a module should "raise the level of abstraction by describing a new concept in your architecture"; if you cannot name it differently from its main resource, it is a thin wrapper and adds indirection without value ([module development](https://developer.hashicorp.com/terraform/language/modules/develop)). Do not write a module when:

- It wraps a single resource type (`module "s3_bucket"` around `aws_s3_bucket`). Write the resource.
- It is used once and there is no second consumer planned this quarter.
- It exists only to "hide" provider arguments. Consumers still need to understand them.
- A verified public registry module already does it (below). Read its source first; reuse if it fits, fork if it almost fits, otherwise write your own and say why in the README.

Write a module when several roots need the same multi-resource concept (a hardened bucket with logging + policy + lifecycle; a private subnet set with routes and NAT; a service with its role, log group and alarms).

## Design rules

- **Flat**: root -> modules -> resources. No module calling modules calling modules ([composition](https://developer.hashicorp.com/terraform/language/modules/develop/composition)).
- **Dependency inversion**: take IDs of existing things as inputs (`vpc_id`, `subnet_ids`) instead of looking them up or creating them inside. The module then does not care where they came from.
- **No provider blocks** inside reusable modules; only `required_providers` with `>=` minimums ([provider requirements](https://developer.hashicorp.com/terraform/language/providers/requirements#best-practices-for-provider-versions)). Provider config and aliases are passed by the root via `providers = { ... }`.
- **No `backend`, no hard-coded environment**, no `terraform_remote_state`. Data-only modules (that only read) are allowed and useful for encapsulating "how do we find X".
- **Conditional creation** is done by the caller passing either an existing ID or `null`, not by `count = var.create ? 1 : 0` on every resource.
- **Everything the caller might need** is an output; nothing else. Outputs are the module's API.

## Standard structure

```
modules/<name>/
├── main.tf          # resources
├── variables.tf     # alphabetical, every one typed + described
├── outputs.tf       # alphabetical, every one described
├── versions.tf      # required_version + required_providers (>= only)
├── README.md        # terraform-docs BEGIN/END markers
├── examples/
│   └── basic/       # runnable root using the module by relative path
└── tests/
    └── basic.tftest.hcl
```

Nested `modules/` inside a module are internal unless they have a README ([standard structure](https://developer.hashicorp.com/terraform/language/modules/develop/structure)).

## Inputs

```hcl
variable "environment" {
  type        = string
  description = "Deployment environment, used in names and tags."

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of dev, staging, prod."
  }
}

variable "db_password" {
  type        = string
  description = "Initial admin password. Not stored in state when the provider supports write-only arguments."
  sensitive   = true
  ephemeral   = true   # Terraform >= 1.10
}

variable "settings" {
  type = object({
    retention_days = optional(number, 30)
    multi_az       = optional(bool, false)
  })
  default     = {}
  description = "Tunables with safe defaults; override per environment."
}
```

Rules ([variable block](https://developer.hashicorp.com/terraform/language/block/variable), [style guide](https://developer.hashicorp.com/terraform/language/style#variables)):

- `type` and `description` on every variable; a `default` only when the value is genuinely optional. No `type = any`.
- `validation` blocks for anything with a closed set, a format (CIDR, ARN, region) or a range. Fail at plan time, not in the cloud API.
- `sensitive = true` for secrets; add `ephemeral = true` [1.10] when the value is only needed during the run (then it must flow only into ephemeral/write-only positions).
- Prefer one `object` with `optional(...)` attributes for groups of related tunables over ten scalar variables.
- `nullable = false` when `null` makes no sense; otherwise handle `null` explicitly.

## Outputs

```hcl
output "subnet_ids" {
  description = "Private subnet IDs, one per availability zone."
  value       = aws_subnet.private[*].id
}
```

- `description` always. `sensitive = true` if the value is secret (it is still in state). `ephemeral = true` [1.10] for run-only values ([manage sensitive data](https://developer.hashicorp.com/terraform/language/manage-sensitive-data)).
- Output IDs and ARNs, not whole resource objects; whole objects make every attribute a compatibility promise.
- Use `precondition`/`postcondition` on resources and outputs to assert invariants the provider does not enforce; use `check` blocks [1.5] for non-blocking assertions ([check block](https://developer.hashicorp.com/terraform/language/block/check)).

## Sources and versioning

```hcl
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"   # public registry
  version = "~> 5.8"                           # always constrain
}

module "network" {
  source = "git::https://github.com/org/terraform-aws-network.git?ref=v1.4.2"  # tag or SHA, never a branch
}

module "hardened_bucket" {
  source = "../../modules/hardened-bucket"      # local: versioned with the repo
}
```

- Registry modules: `version` is required by policy; use `~>` in roots ([module sources](https://developer.hashicorp.com/terraform/language/modules/sources), [using registry modules](https://developer.hashicorp.com/terraform/registry/modules/use)).
- Git sources: pin `ref=` to a tag or commit. A branch ref makes `init -upgrade` a surprise deploy.
- Local modules change with the root; that is fine inside one repo. Once a module is shared across repos, move it to its own `terraform-<PROVIDER>-<NAME>` repo with semantic-version tags (`v1.2.3`) and publish to the private registry or HCP Terraform ([publishing](https://developer.hashicorp.com/terraform/registry/modules/publish)).
- Breaking change = major bump; document `moved` blocks for renamed resources so consumers upgrade without recreation ([refactoring](https://developer.hashicorp.com/terraform/language/modules/develop/refactoring)).

## Public registry: verified and partner modules

On [registry.terraform.io](https://registry.terraform.io/) filter for *partner* (verified) modules; those are reviewed by HashiCorp for stability and compatibility ([using registry modules](https://developer.hashicorp.com/terraform/registry/modules/use)). Community modules (for example the `terraform-aws-modules` organisation) are widely used but not reviewed; before adopting any public module:

- [ ] Read `main.tf` and `variables.tf`; understand what it creates by default.
- [ ] Check open issues, last release date and the provider version constraint.
- [ ] Pin a version; note the upgrade path in the README.
- [ ] Run `trivy config` and `tflint` against an example root using it.
- [ ] Look it up via the MCP server (`references/mcp.md`) rather than guessing inputs.

## Module checklist

- [ ] Name describes an architectural concept, not a resource type.
- [ ] No `provider`/`backend` blocks; `>=` constraints only.
- [ ] Every variable typed, described, validated where a closed set exists; secrets `sensitive`/`ephemeral`.
- [ ] Every output described; secrets `sensitive`.
- [ ] `examples/basic` applies cleanly; `tests/*.tftest.hcl` cover the logic with mocks ([testing.md](testing.md)).
- [ ] README generated by `terraform-docs`; CHANGELOG entry for behaviour changes.
