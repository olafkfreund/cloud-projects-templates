# cloud-projects-templates

This repo sets up a cloud project folder in one command. You get:

- a reproducible [devenv](https://devenv.sh) environment with the provider CLIs, Terraform, and lint and security tools
- `AGENTS.md` and best-practice **agent skills**
- **read-only MCP servers** that AI agents use to inspect your cloud accounts
- **agenix**-encrypted secrets

Providers: **AWS**, **Azure**, **GCP**, **Oracle Cloud (OCI)**, **Kubernetes**, **Cloudflare**, **Hetzner Cloud** and **DigitalOcean**.

## Quick start

Prerequisites: [Nix](https://nixos.org/download) with flakes enabled, [devenv](https://devenv.sh/getting-started/), and optionally [direnv](https://direnv.net).

```bash
mkdir my-infra && cd my-infra && git init

# one or more providers
nix run github:olafkfreund/cloud-projects-templates -- aws azure

# or a single provider as a plain flake template
nix flake init -t github:olafkfreund/cloud-projects-templates#gcp

direnv allow        # or: devenv shell
```

`nix run` and `nix flake init` write the project files: `AGENTS.md`, skills, `.mcp.json`, `secrets.nix` and `devenv.yaml`. `devenv --from …` only opens a temporary shell with the tools and writes none of these, so don't use it to start a project.

Running `nix run … -- <provider>` again in a generated project adds that provider while preserving existing skills and MCP overrides. It updates the YAML `imports` list even when other settings follow it. An actual addition may normalize YAML formatting; repeated additions leave the YAML unchanged. Malformed YAML or an `imports` value other than a list of strings is rejected before project changes.

## What you get

| | Every project | aws | azure | gcp | oci | kubernetes |
|---|---|---|---|---|---|---|
| Tools | just, terraform, tflint, trivy, terraform-docs, infracost, jq, yq, age (agenix-format secrets) | awscli2, aws-vault, ssm plugin, cfn-lint, eksctl, Python, cloud-onboard-aws | az (+aks-preview, resource-graph), bicep, kubelogin | gcloud (+gke auth plugin) | oci-cli | kubectl, helm, k9s, kustomize, kubectx, stern |
| MCP servers (read-only) | terraform (registry) | aws-api, aws-docs | azure | gcloud (allowlist) | oci | kubernetes |
| Skills | `terraform`, `secrets`, `cloud-onboarding`, `cloud-troubleshoot` | `aws` | `azure` | `gcp` | `oci` | `kubernetes` |

| | cloudflare | hetzner | digitalocean |
|---|---|---|---|
| Tools | wrangler, cloudflared, flarectl | hcloud | doctl |
| MCP servers | cloudflare-docs, cloudflare-api (read token) | none, as there is no official server | digitalocean-docs, digitalocean (read token) |
| Skills | `cloudflare` | `hetzner` | `digitalocean` |

Files in a generated project:

```
devenv.yaml devenv.nix devenv.lock .envrc .gitignore
justfile cloud-onboarding.just
AGENTS.md CLAUDE.md .mcp.json .mcp/
.claude/skills/<skill>/     # read by Claude Code, Cursor, opencode, Copilot
.agents/skills/<skill>  →   # symlink, read by Codex, Gemini CLI
secrets.nix secrets/*.age
```

Pre-commit hooks run `terraform fmt`, `tflint`, `detect-private-keys`, `shellcheck`, and a check that `secrets/` holds only `*.age` files.

## Cloud onboarding and reports

Every project includes shared onboarding and troubleshooting skills. AWS has an
automated, read-only baseline command, as do Azure, GCP, OCI, Kubernetes,
Cloudflare, Hetzner and DigitalOcean. Each has explicitly bounded coverage.
See the [command guide](skills/cloud-onboarding/references/commands.md) for
provider examples, required identity arguments and existing-project adoption.

Use `cloud-onboard-<provider>` inside `devenv shell` or direnv,
`just onboard <provider> ...` in the same environment, or
`nix run github:olafkfreund/cloud-projects-templates#onboard-<provider> -- ...`
from a Git project root. Shell activation never scans. `just --list` discovers
the recipe; all commands support credential-free `--help`.

Inside an AWS project's shell, from its Git root:

```sh
cloud-onboard-aws --account-id 123456789012 --regions eu-west-1 eu-west-2 \
  --environment production --profile audit
```

Use an existing read-only profile. Identity must match the account before any
inventory is read. The environment is a report label, not a tag filter. The
commercial-AWS baseline covers root MFA/keys, EC2 instances/volumes/security
groups, RDS instances, general-purpose S3 buckets and CloudTrail logging. It is
not complete account inventory or compliance certification. Permissions are
listed in the [AWS procedure](skills/aws/references/cli-cheatsheet.md#onboarding-discovery).

Each run creates private `report.md`, `inventory.json`, `findings.json` and
`coverage.json` in `reports/<environment>/<timestamp-and-id>/`. Reports distinguish
pass, fail, unknown, not applicable and manual review, with evidence and priority
actions. Denied reads and incomplete lists never prove absence or compliance.
Reports contain sensitive infrastructure metadata: keep them local and ignored;
do not publish automatically. The command also protects old projects through
local Git exclusion, rejects tracked/symlinked report paths, and preserves old runs.

Exit **0**: supported collection complete (findings may fail); **2**: a partial
report was written; **1**: invalid input, identity failure, or report failure.
Defaults are 1,000 items per paginated list, 60 seconds per command, 900 seconds
total. `--max-items`, `--command-timeout`, and `--timeout` adjust these bounds.
Backups need restore evidence; architecture, IAM, resilience and cost require
manual review. Automated baseline comparison is deferred. AWS reports retain schema v1; the
other seven use v2 with provider-specific scope and explicit identity strength.

Use `cloud-troubleshoot` for a specific symptom. It relates current evidence to a
suitable baseline and reports likely causes and missing evidence, without
restarting resources, creating debug workloads, or changing permissions.

### What you can do

| Task | Available now |
|---|---|
| Establish an AWS baseline | Run `cloud-onboard-aws` for one account and explicit regions; get inventory, checks, evidence and coverage reports. |
| Discover another provider | Run `cloud-onboard-<provider>` with its explicit scope. Each produces inventory, bounded checks and coverage; an agent can interpret the report. |
| Assess configuration gaps | AWS checks include root MFA/keys, open SSH/RDP security-group rules, encryption, RDS backup retention/public access, S3 protection/versioning, CloudTrail logging and required tags. Workload-dependent decisions remain manual. |
| Investigate a problem | Ask an agent to use `cloud-troubleshoot` with a symptom, scope, time window and an existing baseline if available. It gathers evidence and distinguishes likely causes from unverified hypotheses. |
| Prepare fixes | Use the provider and Terraform skills to turn reviewed findings into proposed IaC changes. Onboarding itself does not apply fixes. |
| Reassess after changes | Run onboarding again to preserve a new dated report. Comparing runs is currently a manual or agent-assisted review; there is no automated diff command. |

The skills are instructions for your coding agent, not additional shell commands.
There is no scheduled scanning, hosted dashboard, automatic publication, or full
CIS/compliance certification. The report's coverage determines what was assessed.

### Your first assessment

1. Create an AWS project using the quick start, or follow [Updates](#updates) to
   adopt the command and skills in an existing project. Enter its `devenv shell`.
2. Authenticate with your existing read-only AWS profile. For an SSO profile,
   use `aws sso login --profile audit`; substitute your actual profile name.
   Confirm the intended account ID and regions before running the example above.
3. Run `cloud-onboard-aws` from the project's Git root. Replace the example
   account, regions and environment label with your agreed scope.
4. Open `report.md` in the directory printed by the command. Check coverage and
   unknown results before prioritizing failures: denied access is an evidence
   gap, and an empty partial inventory does not establish that resources are absent.
5. Review the recommended actions and manual-review items. Use `inventory.json`
   for resource evidence, `findings.json` for individual assessments, and
   `coverage.json` for collection gaps and unsupported areas. The
   [report format](skills/cloud-onboarding/references/report-format.md) describes
   their contract.
6. Propose and review fixes separately, then rerun the same scope to check the
   observed result. Exit code 0 means collection succeeded, not that every check
   passed; automation must also inspect findings and coverage.

### Example agent requests

Replace the example scope with your own. Start the agent inside the generated
project so it can read the installed skills.

> Use cloud-onboarding for AWS account 123456789012, profile audit, regions
> eu-west-1 and eu-west-2, environment production. Create a read-only baseline,
> summarize coverage gaps, and prioritize findings with their evidence.

> Use cloud-onboarding for Azure tenant <tenant-id> and subscription
> <subscription-id>. Run the Azure collector, create a local
> report, and distinguish missing configuration from unavailable evidence.

> Use cloud-troubleshoot to investigate <symptom> in <account/project/cluster>
> and <region/namespace> during <UTC time window>. Use <report-directory> as the
> baseline. Gather read-only evidence and report likely causes, confidence and
> the next checks needed.

## MCP servers are read-only

The agent gets the permissions of **your CLI login**, restricted further as follows:

| Server | Restriction |
|---|---|
| aws | `READ_OPERATIONS_ONLY=true` |
| azure | `--read-only` flag |
| kubernetes | `--read-only` flag |
| terraform | registry toolsets only |
| gcloud | **No read-only mode.** A command allowlist in `.mcp/gcloud-allow.json`. Use a Viewer-only service account. |
| oci | **No read-only mode.** Use a read-only OCI profile (`OCI_CLI_PROFILE`). |
| cloudflare-api | **No read-only mode.** Token scope: store a "Read all resources" token as `CLOUDFLARE_READ_TOKEN`. If a browser authorisation prompt appears, don't approve it; rotate the token. |
| digitalocean | **No read-only mode.** Token scope: store a Read Only token as `DIGITALOCEAN_READ_TOKEN`. |

Log in first (`aws-vault exec <profile> -- claude`, `az login`, `gcloud auth login`, `oci session authenticate`). Each skill's `references/mcp.md` explains how to allow writes.

## Secrets (agenix)

```bash
cat ~/.ssh/id_ed25519.pub            # add this key to `recipients` in secrets.nix
gh auth token | secret-add GITHUB_TOKEN
secret-list
secret-run --only INFRACOST_API_KEY -- infracost breakdown --path .
secret-run -- claude                 # agent + MCP servers see the decrypted env vars
secret-rekey                         # after adding or removing a recipient
```

`secrets/*.age` is encrypted and safe to commit. Plaintext is never written to disk. Removed a recipient? Rotate the secret at the provider as well. Old ciphertext stays in git history.

## Opt-in tools

Add them to `packages` in your project's `devenv.nix`:

| Tool | Package | Caveat |
|---|---|---|
| AWS CDK | `pkgs.aws-cdk-cli` | about 1.9 GB |
| AWS SAM | `pkgs.aws-sam-cli` | uncached on macOS |
| Checkov | `pkgs.checkov` | uncached |
| Packer | `pkgs.packer` | unfree: add `packer` to `permitted_unfree_packages` in `devenv.yaml` |

## Updates

Projects import the modules from this repo at the revision pinned in `devenv.lock`. Run `devenv update` to pick up new tools and fixes.

Copied skills and just recipes do not update with that lockfile. Existing task
files are preserved; review importing `cloud-onboarding.just` or run
`just --justfile cloud-onboarding.just onboard <provider> ...`.

Copied skills do not update with that lockfile. Re-run the generator to add
missing shared skills, preserving local edits and MCP overrides. For existing
skill updates, generate the same providers into a temporary directory, review
the differences against `.claude/skills/`, then copy only the reviewed changes.
Do not replace customized skills wholesale. Existing `AGENTS.md` and `.gitignore`
also stay unchanged; adopt their guidance through a reviewed diff. Keep manual
reports ignored even when using an older project template.

`cloud-onboard-aws` runs the remote module's script revision; the script copied
inside the onboarding skill can differ. Reports identify the executed collector
and ruleset versions. Update the project module deliberately before using the
new command; no generator run refreshes the module lock automatically.

## Contributing

See [AGENTS.md](AGENTS.md). Changes follow `intent/` → `spec/` → `plan/`.

After changing template sources, stage any new source files so Nix includes them, then run from this repository's root:

```bash
nix run .#regenerate-templates
nix flake check -L
```

The maintainer command generates all providers before **replacing every generated `templates/<provider>` directory**, including obsolete files. It preserves `templates/base` and refuses symlinked destinations and nested Git repositories. Use ordinary `nix run … -- <provider>` for user projects. If replacement fails partway through, inspect `git diff` and restore only affected generated directories from Git before retrying.

Flake checks cover offline AWS onboarding scenarios, template freshness, skill format, generator regressions, and generated MCP configuration (package pins, configured read-only restrictions, token mappings, and the GCP allowlist). Linux CI also tests secrets in a project path containing spaces and performs a credential-free Terraform MCP initialization and tool-list handshake. It does not invoke tools. Cloud-provider MCP startup and live read/write authorization remain [tracked separately in #11](https://github.com/olafkfreund/cloud-projects-templates/issues/11); passing these checks does not establish cloud permissions.

## License

MIT
