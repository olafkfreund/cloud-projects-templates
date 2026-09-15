---
status: approved
issue: 1
spec: spec/2026-09-15-1-cloud-devenv-templates.md
---

# Plan: Multi-provider cloud devenv templates

This plan can be implemented without opening the intent or spec. Every approved decision is copied below.

## Approved decisions

**D1. Entry points.**
- `nix run github:olafkfreund/cloud-projects-templates -- <p>… [--into DIR]` combines providers.
- `nix flake init -t github:olafkfreund/cloud-projects-templates#<p>` sets up one provider.
- `devenv --from "github:…?dir=templates/<p>" shell` is documented only.

**D2. Providers in v1:** `aws azure gcp oci kubernetes`. The `common` module and the `secrets` and `terraform` skills are always included. Kubernetes is opt-in, never implied.

**D3. Generated projects use standalone devenv, not flakes.**
- `devenv.yaml` has the input `cloud: {url: github:olafkfreund/cloud-projects-templates, flake: false}`.
- Modules are imported as `cloud/modules/<p>`, never copied.
- `nixpkgs.permitted_unfree_packages: [terraform]` lives in the project's `devenv.yaml`, because remote imports don't carry it. `allow_unfree` stays false.
- The project's `devenv.nix` is an empty module for local additions.

**D4. The init app** is a `writeShellApplication` with `runtimeInputs` coreutils, jq and gnused. It reads sources from `${self}` and does the following:
- Validates provider names against `modules/*` and refuses an empty list.
- Copies `templates/base` with `cp -rn` only if there's no `devenv.yaml`, then runs `chmod -R u+w`.
- Appends the import only if it isn't already there.
- Copies `skills/<p>` to `.claude/skills/<p>` and creates the relative symlink `.agents/skills/<p> -> ../../.claude/skills/<p>`.
- Merges `modules/<p>/mcp.json` into `.mcp.json`, with existing entries winning.
- Copies extra files into `.mcp/`.
- Appends an `AGENTS.md` provider section between markers, so re-running doesn't duplicate it.
  - *Step 5:* the section text lives in `modules/<p>/agents.md`, so provider data stays out of the script. The script also always copies the `terraform` and `secrets` skills and merges `modules/common/mcp.json`.
- Prints the next steps.

The same script generates the committed `templates/<p>`, and a check fails if they're stale.

*Correction:* the spec's example `jq -s '.[0] * .[1]'` contradicts its own rule that existing entries win. The plan implements the rule, with arguments ordered `new, existing`.

**D5. Module packages** (nixos-unstable attribute names):

| Module | Packages |
|---|---|
| common | `terraform tflint trivy terraform-docs infracost jq yq-go age uv nodejs terraform-mcp-server` |
| aws | `awscli2 ssm-session-manager-plugin aws-vault python3Packages.cfn-lint eksctl`, with the devenv `aws-vault` integration documented as a per-project opt-in (`enable`, `profile`, `awscliWrapper`/`terraformWrapper`). *Step 6:* the integration needs a fixed profile name at build time, and wrapping `aws`/`terraform` would break other login methods, so the shared module only installs `aws-vault` |
| azure | `azure-cli.withExtensions [aks-preview containerapp]`, `bicep kubelogin azure-mcp` |
| gcp | `google-cloud-sdk.withExtraComponents [gke-gcloud-auth-plugin]` |
| oci | `oci-cli` |
| kubernetes | `kubectl kubernetes-helm k9s kustomize kubectx stern` |

Excluded, documented as opt-in: `packer`, `aws-cdk-cli`, `aws-sam-cli`, `checkov`. Out of scope: `azd` and `sops`.

**D6. Git hooks** (in common). *Step 6:* the base `.envrc` needs a `# shellcheck shell=bash` directive, or the shellcheck hook fails. *Step 4:* devenv 2.x requires a `git-hooks` input (`github:cachix/git-hooks.nix`, following nixpkgs) in the base `devenv.yaml`. `terraform-format` (default terraform package), `tflint`, `detect-private-keys`, `shellcheck`, and a local `secrets-age-only` hook that rejects anything in `secrets/` other than `*.age` and `.gitkeep`.

**D7. MCP servers.** All are pinned, read-only by default, and use the CLI login with no embedded credentials:

| Server | Configuration |
|---|---|
| `aws` | `uvx awslabs.aws-api-mcp-server==1.5.5`, env `READ_OPERATIONS_ONLY=true REQUIRE_MUTATION_CONSENT=true AWS_API_MCP_PROFILE_NAME=${AWS_PROFILE:-default} AWS_REGION=${AWS_REGION:-eu-west-1} AWS_API_MCP_SUPPRESS_DEPRECATION_WARNING=true` |
| `aws-docs` | `uvx awslabs.aws-documentation-mcp-server==1.2.1` |
| `azure` | `azure-mcp server start --read-only --mode namespace` (nixpkgs binary) |
| `gcloud` | `npx -y @google-cloud/gcloud-mcp@0.5.3 --config ${DEVENV_ROOT}/.mcp/gcloud-allow.json`, allowlist of list/describe/read groups only |
| `oci` | `uvx oracle.oci-cloud-mcp-server==2.2.3`, env `OCI_CONFIG_PROFILE=${OCI_CLI_PROFILE:-DEFAULT} OCI_MCP_AUTH_TYPE=auto` |
| `kubernetes` | `npx -y kubernetes-mcp-server@0.0.66 --read-only --disable-multi-cluster` |
| `terraform` | in `modules/common/mcp.json`: `terraform-mcp-server stdio --toolsets registry,registry-private`, env `TFE_TOKEN=${TFE_TOKEN:-}` |

GCP and OCI have no server-side read-only mode. The skills and `init` output tell the user to use a Viewer-only service account (GCP) or a read-only OCI profile. Write access is opt-in, documented per provider in `references/mcp.md`.

**D8. Secrets use agenix.**
- `secrets.nix` holds `recipients` and an entry per secret. `secrets/<NAME>.age` files are committed.
- Scripts in common: `secret-add NAME` (reads stdin), `secret-edit`, `secret-rekey`, `secret-list` (names only) and `secret-run [--only A,B] -- CMD`.
  - *Step 0 result:* `ragenix` ignores piped stdin. It opens `$EDITOR`, writes an empty secret or panics. So the scripts use plain `age` instead, reading recipients with `nix-instantiate --eval --strict --json -E '(import ./secrets.nix)."secrets/NAME.age".publicKeys'` and then `age -r … -o secrets/NAME.age`. The output is standard agenix format: verified that upstream `agenix -d` decrypts it, so users can still run `agenix -e` and NixOS `age.secrets` on these files.
  - `secret-edit NAME` asks for a new value (stdin or a hidden prompt) and replaces the file, so no temp plaintext file is created.
  - `secret-rekey` re-encrypts each file for the current recipients with `age -d | age -r`, in memory.
  - `ragenix` is dropped from D5.
  - `secret-run` decrypts with `age -d -i ${AGENIX_IDENTITY:-$HOME/.ssh/id_ed25519}` into its own environment, then `exec`s the command.
- Nothing is decrypted in `enterShell`, and no plaintext is written to disk.
- `.gitignore` excludes `.env .env.* *.dec .mcp.local.json`. *Step 5:* the earlier `.env*` pattern also ignored `.envrc`.

**D9. Agent context.**
- Base `AGENTS.md` covers Terraform as the only IaC CLI, tags and naming, least privilege, login per provider, read-only MCP, secret rules and pointers to the skills. `CLAUDE.md` is the single line `@AGENTS.md`.
- Skill frontmatter has only `name` (equal to the directory name) and `description`. `SKILL.md` stays at or under 500 lines, and each file in `references/` at or under 300.
- References: `well-architected`, `landing-zone`, `iam`, `cli-cheatsheet`, `terraform`, `mcp`. Each claim links to the official source:
  - AWS: Well-Architected Framework and Control Tower
  - Azure: Well-Architected Framework, CAF and the Azure landing zone
  - GCP: Well-Architected Framework and the enterprise foundations blueprint
  - OCI: best-practices framework and the CIS Landing Zone
- The repo root has its own `AGENTS.md`, covering how to add a provider and the artifact workflow, plus a `CLAUDE.md`.

**D10. CI.**
- `nix flake check`, which includes the stale-template and skills checks.
- A template matrix: `aws azure gcp oci kubernetes aws+azure` × `ubuntu-latest macos-latest`, with `fail-fast: false`. The macOS jobs are not required.
  - Each job runs `devenv --override-input cloud path:$GITHUB_WORKSPACE test`.
- A secrets smoke test.
- `uvx` and `npx` MCP servers are not launched in CI.

**D12. Terraform only** (approver revision, 2026-09-15). OpenTofu is dropped, and `terraform` is in the common module for every project.
- `skills/terraform/` is always installed. It holds `SKILL.md` plus `references/{project-structure,state,modules,testing,ci-cd,mcp}.md`, following the D9 limits and linking to official HashiCorp sources.
- Each provider skill's `references/terraform.md` stays provider-specific and links to `../terraform/SKILL.md`.
- *Step 4 measurement:* the first `devenv test`, including the Terraform build, took 123 s, under 5 minutes, so no `nixpkgs-terraform` input is needed.
- **Risk:** unfree packages are not in cache.nixos.org, so `terraform` builds from source on first use. Step 4 measures the time. If it takes longer than 5 minutes, add input `nixpkgs-terraform: github:stackbuilders/nixpkgs-terraform` and its cachix cache to the base `devenv.yaml`, and update this plan in the same commit.

**D11.** MIT licence. The repo contains no secrets or account IDs.

## Steps

Each step is one commit, `feat(<area>): … (#1)`, on `feat/1-cloud-devenv-templates`. An `ACT` cites the step number.

0. **Check that ragenix works like agenix (spec risk 4).**
   - Run `nix shell nixpkgs#ragenix nixpkgs#age`, use a throwaway age key and a temp `secrets.nix`, then:
     - `printf v | agenix -e secrets/T.age`
     - `age -d -i key secrets/T.age` should print `v`
     - `agenix -r` should exit 0
   - → verify: all three succeed.
   - If any fails, revise D5 and D8 to add `github:ryantm/agenix` as a devenv input, and update this plan in the same commit.
1. **Repo basics.** Add `LICENSE` (MIT), `.gitignore` (`result*`, `.devenv*`, `.direnv`), root `AGENTS.md` and `CLAUDE.md`, and a real `README.md` (quick start, providers, secrets, opt-in tools, `devenv update`).
   → verify: files exist; `CLAUDE.md` contains exactly `@AGENTS.md`.
2. **`flake.nix` skeleton.**
   - Input `nixpkgs` (nixos-unstable).
   - Systems: `x86_64-linux aarch64-linux x86_64-darwin aarch64-darwin`, via `nixpkgs.lib.genAttrs`, with no flake-utils.
   - `formatter = nixfmt-rfc-style`.
   - `apps.default` points to `pkgs/init.sh` through `writeShellApplication`.
   → verify: `nix flake show` lists the apps, and `nix run . -- ` with no arguments exits 1 with usage.
3. **`templates/base`.**
   - `devenv.yaml` puts `imports:` last, with `- cloud/modules/common`, so providers are appended with `>>`.
   - Also add `devenv.nix` (`{ pkgs, ... }: { }`), `.envrc` (`eval "$(devenv direnvrc)"` + `use devenv`), `.gitignore` (D8 patterns plus `.devenv*` and `.direnv`), `AGENTS.md`, `CLAUDE.md` and `secrets/.gitkeep`.
   - `secrets.nix`:
     ```nix
     let
       recipients = [
         # "ssh-ed25519 AAAA… you@host"   (cat ~/.ssh/id_ed25519.pub)
       ];
     in
     {
       # secret-add inserts entries above this line
     }
     ```
   → verify: `nix-instantiate --parse secrets.nix` succeeds.
4. **`modules/common/devenv.nix` and `mcp.json`.** Add the D5 packages, the D6 hooks, the D8 scripts and the D7 terraform MCP server.
   - Measure the first-shell build time for `terraform` (D12 risk).
   - `enterTest` runs `terraform version`, `tflint --version`, `trivy --version`, `age --version`, `terraform-mcp-server --version`.
   - `secret-add`:
     - The name must match `^[A-Z][A-Z0-9_]*$`.
     - It fails if `recipients` is empty.
     - It inserts `"secrets/NAME.age".publicKeys = recipients;` with sed before the marker, only if the entry isn't there.
     - It runs `agenix -e`. When stdin isn't a TTY, agenix reads from stdin.
   → verify: run `cp -r templates/base/. $tmp && chmod -R u+w $tmp`. Then `devenv --override-input cloud path:$PWD test` passes in `$tmp`, and a stdin `secret-add` works with a throwaway key. This doesn't need the init script, which comes in step 5.
5. **Finish `pkgs/init.sh` (D4).**
   - Arguments: providers, plus `--into DIR` (default `.`).
   - Always merge `modules/common/mcp.json` and copy `skills/secrets`.
   - The MCP merge is `jq -s '.[0] * .[1]' new.json existing.json`, starting from `{}` if the file is missing.
   - AGENTS.md markers are `<!-- provider:<p>:start -->` and `<!-- provider:<p>:end -->`. The section is skipped if the start marker exists.
   → verify: `shellcheck` passes (writeShellApplication runs it). Running `nix run . -- aws --into $tmp` twice leaves the second run with no diff.
6. **AWS.** Add `modules/aws/{devenv.nix,mcp.json}` and `skills/aws/{SKILL.md,references/*.md}`.
   - Check the devenv `aws-vault` option names against https://devenv.sh/reference/options/ before using them. If they differ, update this plan.
   - `enterTest` runs `aws --version`, `aws-vault --version`, `cfn-lint --version`, `eksctl version`.
   → verify: in `$tmp`, `devenv test` passes, and `jq -e '.mcpServers.aws.env.READ_OPERATIONS_ONLY=="true"' .mcp.json` passes.
7. **Azure.** Add the module, `mcp.json` and skill.
   - `enterTest` runs `az version`, `bicep --version`, `kubelogin --version`, `azure-mcp --version`.
   → verify: `devenv test` passes, and `jq -e '.mcpServers.azure.args|index("--read-only")'` passes.
8. **GCP.** Add the module, `mcp.json`, `gcloud-allow.json` (allow-only list: `config list`, `auth list`, `projects list`, `projects describe`, `compute instances list`, `compute instances describe`, `container clusters list`, `run services list`, `storage buckets list`, `iam service-accounts list`, `logging read`) and skill.
   - `enterTest` runs `gcloud version` and `gke-gcloud-auth-plugin --version`.
   → verify: `devenv test` passes, and `.mcp/gcloud-allow.json` has only an `allow` key.
9. **OCI.** Add the module, `mcp.json` and skill. `skills/oci/references/iam.md` includes the read-only policy (`Allow group <ro-agents> to read all-resources in tenancy`).
   - `enterTest` runs `oci --version`.
   → verify: `devenv test` passes.
10. **Kubernetes.** Add the module, `mcp.json` and skill.
    - `enterTest` runs `kubectl version --client`, `helm version`, `k9s version --short`.
    → verify: `devenv test` passes, and `jq` finds `--read-only` in the kubernetes server args.
11. **`skills/secrets/SKILL.md` and `skills/terraform/` (D12).** Document the D8 workflow and rules: never print or decrypt to files, use `secret-run --only`, add recipients and rekey, rotate secrets.
    → verify: the frontmatter check from step 12 passes.
12. **Flake outputs and checks.**
    - `templates.<p> = { path = ./templates/<p>; description; welcomeText; }` for each provider, and `templates.default = templates.aws`.
    - Generate them with `for p in aws azure gcp oci kubernetes; do nix run . -- $p --into templates/$p; done`.
    - `checks.<system>.templates-fresh` is a `runCommand` that regenerates each template into `$out` and runs `diff -r` against `${self}/templates/<p>`.
    - `checks.<system>.skills` is a `runCommand` asserting that the frontmatter `name` equals the directory name and that the line limits hold.
    → verify: `nix flake check` passes. Editing a module file without regenerating makes `templates-fresh` fail, and reverting the edit makes it pass.
13. **`.github/workflows/ci.yml`** (D10). Pin the action versions: `actions/checkout@v5`, `cachix/install-nix-action@v31`, `cachix/cachix-action@v16` with name `devenv`.
    - The secrets smoke job runs `age-keygen`, sets the public key in `secrets.nix`, then `printf s3cr3t | secret-add T`, checks that `secret-run --only T -- printenv T` prints `s3cr3t`, and checks that `! grep -r s3cr3t --exclude-dir=.devenv .` finds nothing.
    → verify: `actionlint` passes locally, and the PR run is green on ubuntu.
14. **Final checks and PR.**
    - Run `trivy fs --scanners secret .` and `nix flake check`.
    - Open a PR with `gh pr create` that links the intent, spec and plan.
    - Open follow-up issues: migrate the AWS MCP server once a read-only API mode exists; add Cloudflare, Hetzner and DigitalOcean.
    → verify: CI is green, the PR description links all three files, and the issues exist.

## Tests

```bash
nix flake check                                              # templates-fresh + skills checks pass
tmp=$(mktemp -d)
nix run . -- aws azure --into "$tmp"                         # composition
nix run . -- aws azure --into "$tmp" && git -C "$tmp" diff --exit-code  # idempotent (after git init + commit)
cd "$tmp" && devenv --override-input cloud "path:$OLDPWD" test   # enterTest + hooks pass
jq -e '.mcpServers | has("aws") and has("aws-docs") and has("azure") and has("terraform")' .mcp.json
jq -e '.mcpServers.aws.env.READ_OPERATIONS_ONLY=="true"' .mcp.json
test -L .agents/skills/aws && test -f .claude/skills/aws/SKILL.md
for p in aws azure gcp oci kubernetes; do d=$(mktemp -d); (cd "$d" && nix flake init -t "path:$OLDPWD#$p" && devenv --override-input cloud "path:$OLDPWD" test); done
# secrets smoke (step 13) and: printf 'x' > secrets/plain && git add secrets/plain && ! git commit -m t   # hook rejects
trivy fs --scanners secret .                                 # no findings
```

Manual check, one-off: in a generated AWS project after `aws-vault exec <profile> -- claude`, `claude mcp list` should show the servers connected. A read call should succeed and a write call should be refused.

## Rollback

- **Each step is its own commit.** `git revert <sha>` undoes one step, and deleting the branch drops everything before merge.
- **After merge:** existing generated projects pin `cloud` in their `devenv.lock`, so they're unaffected until they run `devenv update`. To roll back, revert on `main`. Users who already updated can run `devenv update` again, or pin `cloud` to a known-good revision (`url: github:olafkfreund/cloud-projects-templates/<rev>`).
- **Secrets can't be rolled back by revert.** An `.age` file stays decryptable by old recipients from git history. When a recipient is removed, rotate the secret at the provider as well as running `secret-rekey`.
