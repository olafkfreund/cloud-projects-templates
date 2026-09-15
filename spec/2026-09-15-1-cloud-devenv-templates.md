---
status: approved
issue: 1
intent: intent/2026-09-15-1-cloud-devenv-templates.md
---

# Spec: Multi-provider cloud devenv templates

> **Revision 2026-09-15 (approver decision during implementation):**
> - **Terraform is the only IaC CLI.** OpenTofu is dropped. Terraform is installed in every project, and the project's `devenv.yaml` permits only the unfree `terraform` package (`nixpkgs.permitted_unfree_packages: [terraform]`).
> - **New `terraform` skill**, installed in every project alongside the `secrets` skill.
> - This replaces every "OpenTofu first", "Terraform opt-in" and "no unfree packages by default" statement below. `packer` stays opt-in.

## Design

### 1. Repository layout

```
flake.nix                    # outputs: apps.default (init), templates.*, checks, formatter
modules/
  common/devenv.nix          # IaC + lint + security + secrets tooling, git-hooks, secret-* scripts
  aws/devenv.nix   aws/mcp.json
  azure/devenv.nix azure/mcp.json
  gcp/devenv.nix   gcp/mcp.json   gcp/gcloud-allow.json
  oci/devenv.nix   oci/mcp.json
  kubernetes/devenv.nix kubernetes/mcp.json
skills/<p>/SKILL.md          # p ∈ aws azure gcp oci kubernetes
skills/<p>/references/{well-architected,landing-zone,iam,cli-cheatsheet,terraform,mcp}.md
skills/secrets/SKILL.md      # agenix workflow, always installed
templates/base/              # devenv.yaml devenv.nix .envrc .gitignore AGENTS.md CLAUDE.md secrets.nix secrets/.gitkeep
templates/<p>/               # generated: `nix run . -- <p> --into templates/<p>`; CI fails on drift
AGENTS.md  CLAUDE.md (@AGENTS.md)  README.md  LICENSE (MIT)
.github/workflows/ci.yml
intent/ spec/ plan/
```

### 2. Entry points

- **Several providers:** `nix run github:olafkfreund/cloud-projects-templates -- aws azure [--into DIR]`
- **One provider:** `nix flake init -t github:olafkfreund/cloud-projects-templates#aws`
- **Try without copying files:** `devenv --from "github:olafkfreund/cloud-projects-templates?dir=templates/aws" shell`. This path is documented but gets no extra code.

The `init` app is a `writeShellApplication` whose `runtimeInputs` are coreutils, jq and gnused. It reads its sources from `${self}`, so `nix run` gets the exact revision it was fetched at. It runs these steps:

1. Validate each provider name against `modules/*`, then refuse unknown names and an empty list.
2. If `devenv.yaml` doesn't exist, copy `templates/base` in with `cp -rn`, which never overwrites. Then run `chmod -R u+w`.
3. For each provider:
   - **Module import.** Add `- cloud/modules/<p>` under `imports:` in `devenv.yaml`, skipping it if a `grep -qx` finds it already there.
   - **Skill.** Copy `skills/<p>` to `.claude/skills/<p>`, and create the relative symlink `.agents/skills/<p> -> ../../.claude/skills/<p>`.
   - **MCP config.** Merge `modules/<p>/mcp.json` into `.mcp.json` with `jq -s '.[0] * .[1]'`. Existing user entries win on key conflict.
   - **Extra files.** Copy extra per-provider files, such as `gcloud-allow.json` into `.mcp/`.
   - **AGENTS.md.** Append a `## <Provider>` section (skill pointer, login command, MCP notes) between markers, so re-running doesn't duplicate it.
4. Print the next steps: `direnv allow` or `devenv shell`, the login commands, and `secret-add`.

**Why a script:** `nix flake init` refuses to overwrite files, so templates can't be combined. A script is the only way to compose them. The same code path generates `templates/<p>`, so the file set exists in only one place.

### 3. Generated project

**`devenv.yaml`:**
```yaml
inputs:
  nixpkgs:
    url: github:cachix/devenv-nixpkgs/rolling
  cloud:
    url: github:olafkfreund/cloud-projects-templates
    flake: false
imports:
  - cloud/modules/common
  - cloud/modules/aws          # appended per provider
nixpkgs:
  allow_unfree: false          # set true + add `terraform` to packages to opt in
```

**Why the modules are imported, not copied:** a project gets module improvements with `devenv update`, and the version is pinned in `devenv.lock`. The project's own `devenv.nix` is an empty module for local additions.

**Unfree setting:** `allow_unfree` lives here, in the project, because devenv doesn't pick it up from remote imports.

### 4. Modules (packages from nixos-unstable, names verified)

| Module | Packages | Notes |
|---|---|---|
| common | `opentofu tflint trivy terraform-docs infracost jq yq-go ragenix age uv nodejs terraform-mcp-server` | git-hooks: `terraform-format` (package = opentofu), `tflint`, `detect-private-keys`, `shellcheck`, plus a local hook that rejects anything in `secrets/` that isn't `*.age`. `enterTest` checks each binary's version. |
| aws | `awscli2 ssm-session-manager-plugin aws-vault python3Packages.cfn-lint eksctl` | devenv `aws-vault` integration: `aws-vault.enable`, `profile`, `opentofuWrapper.enable` |
| azure | `(azure-cli.withExtensions [ azure-cli.extensions.aks-preview azure-cli.extensions.containerapp ]) bicep kubelogin azure-mcp` | |
| gcp | `(google-cloud-sdk.withExtraComponents [ google-cloud-sdk.components.gke-gcloud-auth-plugin ])` | |
| oci | `oci-cli` | |
| kubernetes | `kubectl kubernetes-helm k9s kustomize kubectx stern` | Not imported automatically. Opt in with `nix run … -- aws kubernetes`. |

**Opt-in and excluded tools:**
- `terraform` and `packer` are unfree, uncached and built locally.
- `aws-cdk-cli` is about 1.9 GB.
- `aws-sam-cli` is uncached on aarch64-darwin.
- `checkov` is uncached.
- `azd` is not in nixpkgs.

Opt-in tools are documented in each skill's `references/terraform.md` and in the README. Nothing is installed by default. `sops` is dropped, so agenix is the only secrets mechanism.

### 5. MCP servers: read-only by default, credentials from the CLI login

Every server is pinned to an exact version. Stdio servers inherit the environment of the agent process, and credentials come from the provider CLI's own login.

| Server | Command | Read-only mechanism | Auth |
|---|---|---|---|
| `aws` | `uvx awslabs.aws-api-mcp-server==1.5.5` | `READ_OPERATIONS_ONLY=true`, `REQUIRE_MUTATION_CONSENT=true` | boto3 chain: `AWS_PROFILE`, or `aws-vault exec <profile> -- claude` |
| `aws-docs` | `uvx awslabs.aws-documentation-mcp-server==1.2.1` | Always read-only | None |
| `azure` | `azure-mcp server start --read-only` | `--read-only` flag | `az login` (AzureCliCredential) |
| `gcloud` | `npx -y @google-cloud/gcloud-mcp@0.5.3 --config ${DEVENV_ROOT}/.mcp/gcloud-allow.json` | **No read-only mode.** An allowlist of list/describe/read command groups, plus a recommended Viewer-only impersonated service account. | `gcloud auth login` |
| `oci` | `uvx oracle.oci-cloud-mcp-server==2.2.3` | **No read-only mode.** Use a dedicated read-only OCI profile (`OCI_CLI_PROFILE`, IAM `inspect`/`read` verbs only). The IAM policy snippet is in `skills/oci/references/iam.md`. | `~/.oci/config` / `oci session authenticate`, `OCI_MCP_AUTH_TYPE=auto` |
| `kubernetes` | `npx -y kubernetes-mcp-server@0.0.66 --read-only --disable-multi-cluster` | `--read-only` flag | kubeconfig |
| `terraform` | `terraform-mcp-server stdio --toolsets registry,registry-private` | Registry toolsets only. The `terraform` toolset is left out because some of its write tools aren't gated. | `TFE_TOKEN` (optional, from agenix) |

**Write opt-in:** documented per provider in the skill's `references/mcp.md`. It means removing the flag or env var, or widening the allowlist, in the project's own `.mcp.json`. It is never the default.

### 6. Secrets with agenix

**Files:**
- `secrets.nix` lists recipients (the user's SSH or age public keys, plus teammates) and one entry per secret. The template ships with an empty recipient list and a comment explaining how to add a key.
- `secrets/<NAME>.age` holds encrypted files, which are committed.

**Scripts** (devenv `scripts`, in `modules/common`):

| Script | Behaviour |
|---|---|
| `secret-add NAME` | Adds `"secrets/NAME.age".publicKeys = recipients;` to `secrets.nix` if it's missing, then runs `agenix -e secrets/NAME.age`. It accepts a value from stdin (`gh auth token \| secret-add GITHUB_TOKEN`) so the value never appears in shell history or on disk. |
| `secret-edit NAME` | `agenix -e secrets/NAME.age` |
| `secret-rekey` | `agenix -r`, after a recipient is added or removed |
| `secret-list` | Lists names only, never values |
| `secret-run [--only A,B] -- CMD…` | Decrypts each selected `secrets/*.age` with `age -d -i ${AGENIX_IDENTITY:-~/.ssh/id_ed25519}` into an environment variable named after the file. It does this only inside its own process, then `exec`s CMD. |

**Typical use:**
- `secret-run -- claude` starts the agent with its secrets.
- `secret-run --only INFRACOST_API_KEY -- infracost breakdown` runs one tool with one secret.
- `.mcp.json` refers to secrets as `${TFE_TOKEN}` and the like. Claude Code expands `${VAR}` in `command`, `args` and `env`.

**Guarantees:**
- No plaintext is ever written inside the project.
- `.gitignore` excludes `.env*`, `*.dec` and `.mcp.local.json`.
- Pre-commit runs `detect-private-keys` and the `*.age`-only check on `secrets/`.
- `skills/secrets/SKILL.md` tells agents to use `secret-run` and to never `cat`, `echo` or decrypt secrets into files or chat.

### 7. Agent context

- **`AGENTS.md`** (base) covers:
  - project conventions: OpenTofu first, tag and naming rules, least privilege
  - how to log in per provider
  - that MCP servers are read-only and why
  - the secrets rules
  - pointers to the skills

  Provider sections are appended by `init`.
- **`CLAUDE.md`** is a single line, `@AGENTS.md`.
- **Skills** use only `name` and `description` in frontmatter, with `name` equal to the directory name. Each `SKILL.md` stays under 500 lines, and each file in `references/` stays under 300 lines. Each skill covers these points:
  - When to use it, and a decision checklist per Well-Architected pillar.
  - Landing zone and reference architecture:
    - AWS: Control Tower / Organizations
    - Azure: CAF and the Azure landing zone
    - GCP: the enterprise foundations blueprint
    - OCI: the CIS Landing Zone
  - IAM patterns, a CLI cheatsheet, and OpenTofu provider, backend and module conventions.
  - MCP usage and write opt-in.
  - Every claim links to the official source URL.
- **Repo root:** has its own `AGENTS.md` (how to add a provider, and the artifact workflow) and a `CLAUDE.md` that imports it.

### 8. CI (`.github/workflows/ci.yml`)

- **`flake` job:** `nix flake check`, plus the drift check. It regenerates every `templates/<p>` and runs `git diff --exit-code`.
- **`skills` job:** frontmatter `name` equals the directory name, and the line limits hold. This is plain bash in `checks`, with no new dependency.
- **`template` matrix** over `aws azure gcp oci kubernetes` and `aws+azure`, on ubuntu-latest and macos-latest:
  1. Install Nix with `cachix/install-nix-action`, enable the `devenv` cache with `cachix/cachix-action`, and install devenv with `nix profile add nixpkgs#devenv`.
  2. Initialise into a temp dir.
  3. Run `devenv --override-input cloud path:$GITHUB_WORKSPACE test`, so a PR tests its own modules.
  4. `enterTest` asserts that each CLI and each MCP binary in nixpkgs starts and prints its version. `uvx` and `npx` servers are not launched in CI, because they need network access and credentials.
- **Secrets smoke test:** generate a throwaway age key, run `secret-add` with stdin, check that `secret-run -- printenv NAME` matches, and check that no plaintext file exists.

## Alternatives rejected

- **devenv as a flake (`devenv.lib.mkShell` / flake-parts).** It needs `--no-pure-eval` and is slower to evaluate, and devenv recommends the standalone CLI.
- **Only `nix flake init -t` templates.** Providers can't be combined, because it refuses to overwrite files.
- **One template with devenv `profiles` per provider.** Every project would carry every provider's skills and MCP config, and agents would load context that doesn't apply.
- **`devenv --from` only.** No `AGENTS.md`, skills or `.mcp.json` would land in the repo, and teammates would need the same command.
- **Copying modules into each project.** Projects would stop receiving fixes, and the duplicate module code would drift.
- **`secretspec` or `sops` for secrets.** You chose agenix. One mechanism is simpler, and agenix matches your NixOS workflow.
- **Decrypting secrets in `enterShell`.** Every subprocess and devenv cache would see them for the whole session. `secret-run` scopes them to one command.
- **The new remote AWS MCP Server via `mcp-proxy-for-aws --read-only`.** Read-only mode hides the sandboxed API tool entirely, which would leave agents without read access to discover resources. Its per-operation read-only gate is weaker than `READ_OPERATIONS_ONLY`. Revisit when AWS adds a read-only API mode.
- **`npx @azure/mcp`.** The nixpkgs `azure-mcp` is reproducible and cached, although it is about 10 betas behind.
- **`oci-api-mcp-server`.** It can run arbitrary `oci` commands. The cloud server exposes a smaller set of tools.

## Risks

1. **AWS API MCP server is deprecated.** `aws-api-mcp-server` is superseded upstream. Mitigation: pin the version, suppress the deprecation banner, and track migration in a follow-up issue.
2. **GCP and OCI have no server-side read-only mode.** The allowlist matches whole command groups, so it's coarse. The real boundary is a read-only cloud identity, which the user must set up. Mitigation: `AGENTS.md` and the skills say so plainly, and `init` prints a warning.
3. **Secrets visible to the agent.** Secrets passed with `secret-run -- claude` are visible to the agent and its child processes, and an agent could print one. Mitigation: `--only` scoping, rules in the secrets skill, and short-lived tokens where the provider supports them.
4. **ragenix compatibility.** `ragenix` must be CLI-compatible with `agenix` for `-e`, stdin input and `-r`. This is verified at the start of implementation. The fallback is to add `github:ryantm/agenix` as a devenv input.
5. **Remote imports pin `cloud` in `devenv.lock`.** Users only get fixes after `devenv update`. That is intentional, and the README documents it.
6. **Uncached and heavy packages** would make first shells slow. They are all excluded from the defaults.
7. **`kubelogin` name clash.** The Azure `kubelogin` and `kubelogin-oidc` share a binary name, so only the Azure one is included.
8. **macOS CI.** A macOS runner costs more and may expose darwin-only breakage. The matrix uses `fail-fast: false`, and the jobs are informative, not required, until they're stable.
9. **Credential variables in HTTP headers.** Claude Code reads some credential variables as empty in remote `url`/`headers`. Only stdio servers are used, so this doesn't apply.

## Verification

"Done" means all of the following hold:

1. **Flake:** `nix flake check` passes locally and in CI.
2. **Per template:** for every template, `nix flake init -t path:.#<p>` in a temp dir, followed by `devenv --override-input cloud path:<repo> test`, passes on x86_64-linux. aarch64-darwin passes in CI.
3. **Combined providers:**
   - `nix run . -- aws azure --into $tmp` produces a `devenv.yaml` with both imports, both skills, and a merged `.mcp.json` with `aws`, `aws-docs`, `azure` and `terraform`.
   - `devenv test` passes.
   - Running the same command again changes nothing (`git diff` is empty).
4. **Templates not stale:** regenerated templates are identical to the committed ones.
5. **Skills:** the frontmatter check passes, and each `SKILL.md` has at least one official URL per pillar or landing-zone section.
6. **MCP servers are read-only:**
   - `jq` asserts `READ_OPERATIONS_ONLY=true` for aws, `--read-only` for azure and kubernetes, and no `terraform` toolset.
   - A manual check with `claude mcp list` in a generated AWS project, after login, shows the servers connecting.
   - A read call works, and a write call is refused.
7. **Secrets:** the smoke test passes. `git grep` for the test secret's value in the generated project finds nothing, and the pre-commit hook rejects a plaintext file in `secrets/`.
8. **Clean public repo:** `trivy fs --scanners secret .` on the repo finds nothing.
