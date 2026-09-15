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

Running `nix run … -- <provider>` again in an existing project adds that provider. It never overwrites your files.

## What you get

| | Every project | aws | azure | gcp | oci | kubernetes |
|---|---|---|---|---|---|---|
| Tools | terraform, tflint, trivy, terraform-docs, infracost, jq, yq, age (agenix-format secrets) | awscli2, aws-vault, ssm plugin, cfn-lint, eksctl | az (+aks-preview), bicep, kubelogin | gcloud (+gke auth plugin) | oci-cli | kubectl, helm, k9s, kustomize, kubectx, stern |
| MCP servers (read-only) | terraform (registry) | aws-api, aws-docs | azure | gcloud (allowlist) | oci | kubernetes |
| Skills | `terraform`, `secrets` | `aws` | `azure` | `gcp` | `oci` | `kubernetes` |

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

## Contributing

See [AGENTS.md](AGENTS.md). Changes follow `intent/` → `spec/` → `plan/`.

## License

MIT
