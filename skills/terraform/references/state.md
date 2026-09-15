# State

State is Terraform's map from configuration to real objects. It contains every attribute of every resource, including secrets, in cleartext ([sensitive data in state](https://developer.hashicorp.com/terraform/language/state/sensitive-data)). Treat it as production credentials.

## Remote backends

Every shared root uses a remote backend; local state is only acceptable in `bootstrap/` for the minutes before its bucket exists ([remote state](https://developer.hashicorp.com/terraform/language/state/remote)). Pick the backend from the provider skill:

| Provider | Backend | Locking | Encryption |
|---|---|---|---|
| AWS | `s3` | `use_lockfile = true` (S3-native, GA in 1.11; DynamoDB locking deprecated) | `encrypt = true`, `kms_key_id` |
| Azure | `azurerm` | blob lease (built in) | storage encryption + CMK |
| GCP | `gcs` | built in | default or `kms_encryption_key` |
| OCI | `s3`-compatible or `oci` | see OCI skill | see OCI skill |
| Any | HCP Terraform `cloud` block | built in | built in |

S3 details: [S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3). The `backend` block cannot reference variables; use partial configuration (`terraform init -backend-config=...`) for values that differ per pipeline ([backend configuration](https://developer.hashicorp.com/terraform/language/backend#partial-configuration)).

Backend storage checklist (whatever the cloud):

- [ ] Versioning/soft-delete on, so a corrupted or deleted state can be restored.
- [ ] Encryption at rest with a customer-managed key for regulated data.
- [ ] Public access blocked; TLS enforced.
- [ ] Read/write restricted to the CI apply identity and platform admins; plan identities get read-only.
- [ ] Access logging/audit on the bucket or container.

## Locking

Terraform locks state automatically on every operation that could write it, when the backend supports it ([state locking](https://developer.hashicorp.com/terraform/language/state/locking)). Rules:

- Never `-lock=false`.
- Use `-lock-timeout=5m` in CI so concurrent pipelines wait instead of failing ([plan options](https://developer.hashicorp.com/terraform/cli/commands/plan)).
- `terraform force-unlock <ID>` only for a lock you own that a crashed run left behind; unlocking someone else's lock produces two writers and a corrupted state.

## Isolation and blast radius

One state per environment, and within a large environment one state per independently-deployed layer (network, platform, application). Why: a bad apply, a leaked credential or a corrupted file only affects that unit; plans stay fast; permissions can be scoped per layer ([workspace use cases](https://developer.hashicorp.com/terraform/cli/workspaces#use-cases)).

Rule of thumb: if two things are always changed together, one state; if they have different owners, change cadence or credentials, separate states.

## Sharing data between states

Prefer, in order:

1. **Provider data sources** on the real object (`data "aws_vpc"`, `data "azurerm_subnet"`, ...) selected by name/tag. Needs only read permission on that object.
2. **Explicitly published values**: SSM Parameter Store, Key Vault, Secret Manager, a tagged resource. The producer writes, the consumer reads with narrow permissions.
3. **`terraform_remote_state`** last. It requires read access to the *whole* state snapshot, which contains everything, not just outputs. HashiCorp: publish data for external consumption to a separate location instead of reading remote state ([remote state data source](https://developer.hashicorp.com/terraform/language/state/remote-state-data)). If you must use it, mark the consumer read-only and keep the producer's outputs minimal.

## Adopting existing objects: `import` blocks [1.5]

Do not run `terraform import` interactively in a shared root; it writes state outside code review. Use an `import` block, generate config, review, apply ([import](https://developer.hashicorp.com/terraform/language/import)):

```hcl
import {
  to = aws_s3_bucket.logs
  id = "my-logs-bucket"
}
```

```bash
terraform plan -generate-config-out=generated.tf   # experimental since 1.5, review and trim
terraform plan -out=plan.tfplan                      # shows "to import"
terraform apply plan.tfplan
```

Move the generated block into the right file, delete computed-only attributes, then delete the `import` block in a follow-up once applied. `for_each` on `import` blocks [1.7] imports many instances from a map ([import block](https://developer.hashicorp.com/terraform/language/block/import)); generated config caveats: [generating configuration](https://developer.hashicorp.com/terraform/language/import/generating-configuration).

## Refactoring: `moved` [1.1] and `removed` [1.7]

Rename or relocate without destroy/recreate ([moved](https://developer.hashicorp.com/terraform/language/moved), [refactoring](https://developer.hashicorp.com/terraform/language/modules/develop/refactoring)):

```hcl
moved {
  from = aws_instance.web
  to   = module.web.aws_instance.this
}
```

Stop managing an object without destroying it ([removed](https://developer.hashicorp.com/terraform/language/block/removed)):

```hcl
removed {
  from = aws_s3_bucket.legacy
  lifecycle {
    destroy = false
  }
}
```

Why blocks instead of `terraform state mv/rm`: the intent is in the PR, the plan shows it, CI applies it identically in every environment, and the same change works for modules published to other roots. A module may only declare `moved` for its own objects and its children. Keep `moved`/`removed` blocks until every environment has applied them, then delete.

`terraform state` subcommands (`list`, `show`, `mv`, `rm`, `pull`, `push`) remain for inspection and emergency repair; they always write a backup ([state commands](https://developer.hashicorp.com/terraform/cli/commands/state)). `mv`/`rm`/`push` require a second person on the call.

## Drift detection

Drift is the real object differing from state. Detect it without proposing config changes:

```bash
terraform plan -refresh-only -detailed-exitcode   # exit 2 = drift found
```

`-refresh-only` shows what changed outside Terraform; applying a refresh-only plan updates state to match reality without touching infrastructure ([plan modes](https://developer.hashicorp.com/terraform/cli/commands/plan#planning-modes)). Run it on a schedule in CI and alert on exit code 2. Decide per finding: revert the manual change (normal `apply`), adopt it (change config, then apply), or accept it (refresh-only apply). Never silence drift with `lifecycle { ignore_changes = all }`.

## Never edit state by hand

The state file is JSON, but HashiCorp is explicit: "Do not directly edit this file" ([state](https://developer.hashicorp.com/terraform/language/state)). Hand edits skip the serial/lineage checks, the lock, and the backup, and the next `apply` may destroy production objects. Use `moved`/`removed`/`import`, or `terraform state` commands, and if state is truly corrupted restore a previous version from the backend's versioning.

## Incident checklist

- [ ] Lock stuck: confirm no run is active in CI/HCP Terraform, then `force-unlock` with the reported ID.
- [ ] State lost or corrupted: restore the previous object version from the backend; do not `state push` a laptop copy.
- [ ] Resource destroyed by mistake: recreate via `apply`; if it still exists in the cloud, `import` block.
- [ ] Secret leaked into state: rotate the secret first, then move to ephemeral/write-only so it never returns.
