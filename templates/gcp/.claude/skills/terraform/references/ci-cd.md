# CI/CD

Principle: a plan is produced once, reviewed by a human, and applied *as reviewed*. Nothing re-plans between approval and apply; nothing applies without approval; no long-lived cloud keys anywhere.

## Pipeline shape

```
PR opened/updated              main merged (or manual dispatch)
┌──────────────────────┐        ┌────────────────────────────────┐
│ fmt / validate / lint│        │ plan (apply identity)          │
│ terraform test (mock)│        │   -> plan.tfplan artifact       │
│ trivy config (HCL)   │        │ environment gate: approval      │
│ plan (read-only id)  │        │ apply plan.tfplan (same runner  │
│   -> trivy on plan   │        │   version, same lock file)      │
│   -> infracost diff  │        │ post-apply: drift check, notify │
│   -> PR comment      │        └────────────────────────────────┘
└──────────────────────┘
```

## Plan on PR

```yaml
# .github/workflows/terraform-plan.yml (excerpt)
permissions:
  id-token: write        # OIDC token
  contents: read
  pull-requests: write   # plan/cost comment
jobs:
  plan:
    strategy:
      matrix: { env: [dev, staging, prod] }
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v4
        with:
          terraform_version: "1.14.6"     # same as devenv.nix
          terraform_wrapper: false
      # cloud login via OIDC: see provider skill (aws-actions/configure-aws-credentials,
      # azure/login, google-github-actions/auth, oracle-actions/...)
      - run: terraform -chdir=infra/envs/${{ matrix.env }} init -lockfile=readonly -input=false
      - run: terraform -chdir=infra/envs/${{ matrix.env }} plan -input=false -lock-timeout=5m -out=plan.tfplan -detailed-exitcode
      - run: terraform -chdir=infra/envs/${{ matrix.env }} show -no-color plan.tfplan > plan.txt
      # post plan.txt as a PR comment; scan plan JSON with trivy; infracost diff
```

Why each flag: `-lockfile=readonly` refuses a pipeline that would change providers silently ([init](https://developer.hashicorp.com/terraform/cli/commands/init)); `-input=false` fails instead of hanging on a prompt; `-lock-timeout` waits for a concurrent run; `-detailed-exitcode` returns 2 when there are changes so the job can label the PR ([plan](https://developer.hashicorp.com/terraform/cli/commands/plan)). `setup-terraform` pins the binary ([setup-terraform](https://github.com/hashicorp/setup-terraform)).

Plan identity is **read-only** on the cloud plus read on the state backend. A PR from any branch can trigger it, so it must not be able to change anything.

## Saved plan files

`terraform plan -out=plan.tfplan` writes a binary plan containing the full configuration, all planned values and the state snapshot, in cleartext, including anything marked `sensitive` ([plan -out](https://developer.hashicorp.com/terraform/cli/commands/plan)). Therefore:

- Upload it as a CI artifact only with a short retention (hours) and access limited to the pipeline; never attach it to the PR, never commit it.
- Apply it with the **same Terraform version and same lock file** that produced it; the binary format is version-specific.
- A plan is only valid against the state serial it was made from. If anyone applies in between, `apply plan.tfplan` errors with a stale-plan message; re-plan, do not force.
- Set retention so a plan cannot be applied days later against changed reality; re-plan after 1 hour or on any new commit.

## Apply only from the saved plan, only after approval

```yaml
  apply:
    needs: plan
    environment: prod            # GitHub environment with required reviewers
    steps:
      - download plan.tfplan artifact
      - terraform init -lockfile=readonly -input=false
      - terraform apply -input=false -lock-timeout=5m plan.tfplan
```

`terraform apply plan.tfplan` performs exactly the saved operations with no prompt and accepts no further planning options ([apply](https://developer.hashicorp.com/terraform/cli/commands/apply)). The approval gate (GitHub environment protection, GitLab protected environment, or HCP Terraform run confirmation) sits between plan and apply, and the approver must not be the PR author. Never run `terraform apply -auto-approve` without a plan file in a pipeline: it re-plans, so what runs may differ from what was reviewed.

For merges to `main`, either re-plan on `main` with the apply identity and gate that plan, or (simpler) apply the PR plan if its commit equals the merge commit's tree and state serial is unchanged. Pick one and write it down in the workflow file.

## OIDC to clouds, no static keys

Pipelines authenticate with a short-lived OIDC token exchanged for cloud credentials; no access keys or service principal secrets are stored in CI ([GitHub OIDC](https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect)). Requirements:

- `permissions: id-token: write` on the job.
- Trust policy / federated credential / workload identity pool scoped to the repo **and** branch or environment (`repo:org/repo:environment:prod`), so a PR from a fork cannot assume the prod role.
- Provider-specific setup is in the provider skill: AWS IAM role with OIDC provider, Azure federated credentials on a managed identity/app, GCP Workload Identity Federation, OCI/Kubernetes equivalents.
- Locally, humans use the same idea: SSO/device login via the provider CLI, tokens injected per command with `secret-run --only NAME -- terraform ...`.

## Least-privilege plan vs apply identities

| Identity | Cloud permissions | State backend | Triggered by |
|---|---|---|---|
| `tf-plan-<env>` | Read-only (`ReadOnlyAccess` / `Reader` / `roles/viewer` plus any `Describe*` the provider needs) | read state, take lock | any PR |
| `tf-apply-<env>` | Scoped write to the resources this root manages; deny IAM/identity changes unless the root owns them | read/write state, lock, KMS decrypt | protected environment only |

Why two: a plan needs no write permission, and a compromised PR pipeline with apply rights is a full environment compromise. Two identities cost one extra role per environment and remove that class of incident. Keep `prod` roles in a separate account/subscription/project from `dev` where the provider skill's landing-zone guidance says so.

## HCP Terraform option

If the team prefers a managed workflow, HCP Terraform provides remote runs, state with encryption and locking, run approval, a private module registry, and policy enforcement (Sentinel/OPA) in one place ([HCP Terraform](https://developer.hashicorp.com/terraform/cloud-docs), [policy enforcement](https://developer.hashicorp.com/terraform/cloud-docs/policy-enforcement)). Free tier exists for small teams.

- Configure a `cloud` block instead of a `backend`; `terraform plan/apply` then run remotely and the CLI streams output ([CLI-driven runs](https://developer.hashicorp.com/terraform/cloud-docs/run/cli)). Saved plans work the same way: `plan -out`, then `apply <file>`.
- Use **dynamic provider credentials** (OIDC from HCP Terraform to AWS/Azure/GCP/Kubernetes/Vault) so no cloud keys are stored as workspace variables ([dynamic provider credentials](https://developer.hashicorp.com/terraform/cloud-docs/workspaces/dynamic-provider-credentials)).
- One workspace per root module/environment; approval happens in the run UI or via the API; VCS-driven runs plan on PR and apply on merge ([GitHub Actions tutorial](https://developer.hashicorp.com/terraform/tutorials/automation/github-actions)).
- The `TF_API_TOKEN`/`TFE_TOKEN` is a secret: `secret-add TFE_TOKEN`, then `secret-run --only TFE_TOKEN -- terraform ...`. In CI it is a protected secret, scoped to the apply job.

Choose HCP Terraform when you want run history, RBAC and policy without building it; choose plain CI when state and runs must stay inside your cloud boundary. Both use the same HCL and the same checks in [testing.md](testing.md).

## Pipeline checklist

- [ ] Terraform version pinned in CI equals `required_version` and devenv.
- [ ] `init -lockfile=readonly`; lock file changes only through PRs.
- [ ] Plan job: read-only identity, `-out`, plan text in PR comment, plan JSON scanned then deleted, cost diff commented.
- [ ] Apply job: separate identity, protected environment with reviewers, consumes the saved plan, no `-auto-approve` re-plan.
- [ ] OIDC trust scoped to repo + environment; no static keys in CI secrets.
- [ ] Concurrency group per environment so two applies never race for the lock.
- [ ] Scheduled `plan -refresh-only -detailed-exitcode` for drift; alert on exit 2.
- [ ] Artifacts with plans/state expire within hours and are not publicly downloadable.
