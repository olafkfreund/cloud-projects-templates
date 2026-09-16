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
| Tools | terraform, tflint, trivy, terraform-docs, infracost, jq, yq, age (agenix-format secrets) | awscli2, aws-vault, ssm plugin, cfn-lint, eksctl, Python, cloud-onboard-aws | az (+aks-preview, resource-graph), bicep, kubelogin | gcloud (+gke auth plugin) | oci-cli | kubectl, helm, k9s, kustomize, kubectx, stern |
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
AGENTS.md CLAUDE.md .mcp.json .mcp/
.claude/skills/<skill>/     # read by Claude Code, Cursor, opencode, Copilot
.agents/skills/<skill>  →   # symlink, read by Codex, Gemini CLI
secrets.nix secrets/*.age
```

Pre-commit hooks run `terraform fmt`, `tflint`, `detect-private-keys`, `shellcheck`, and a check that `secrets/` holds only `*.age` files.

## Cloud onboarding and reports

Every project includes shared onboarding and troubleshooting skills. AWS has an
automated, read-only baseline command; Azure, GCP, OCI, Kubernetes, Cloudflare,
Hetzner and DigitalOcean have manual discovery/reporting procedures.

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
manual review. Baseline comparison and additional automated providers are deferred.

Use `cloud-troubleshoot` for a specific symptom. It relates current evidence to a
suitable baseline and reports likely causes and missing evidence, without
restarting resources, creating debug workloads, or changing permissions.

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
