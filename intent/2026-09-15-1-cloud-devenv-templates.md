---
status: approved
issue: 1
author: olafkfreund
---

# Intent: Multi-provider cloud devenv templates

> **Revision 2026-09-15 (approver decision during implementation):**
> - **Terraform is the only IaC CLI.** OpenTofu is dropped. Terraform is installed in every project, and the project's `devenv.yaml` permits only the unfree `terraform` package (`nixpkgs.permitted_unfree_packages: [terraform]`).
> - **New `terraform` skill**, installed in every project alongside the `secrets` skill.
> - This replaces every "OpenTofu first", "Terraform opt-in" and "no unfree packages by default" statement below. `packer` stays opt-in.

## Problem

Starting a cloud project means hand-assembling the same toolbox every time. That toolbox has four parts:

- **Provider tools:** the provider CLI and its auth helpers.
- **Infrastructure tools:** IaC, lint and security scanners.
- **Kubernetes tools.**
- **Agent context:** instructions that give an AI coding agent the provider's best practices and architecture guidance.

Versions drift between machines and teammates. Agents start with no context about Well-Architected pillars, landing zones or IAM conventions. Work that spans more than one provider (for example AWS and Azure) makes this worse.

There is no single place to go into an empty folder, run one command, and get a reproducible environment ready for one or more cloud providers.

## Proposed outcome

A public repo, `github.com/olafkfreund/cloud-projects-templates`. In any folder, a user runs one of these commands:

- `nix run github:olafkfreund/cloud-projects-templates -- aws azure` for one or more providers combined
- `nix flake init -t github:olafkfreund/cloud-projects-templates#aws` for a single provider

The folder is then ready to use, with these properties:

- **Environment activation.** A devenv environment (`devenv.yaml`, `devenv.nix`, `.envrc`) activates on `cd`, with direnv or the devenv hook.
- **Tools pinned by `devenv.lock`:**
  - the provider CLIs
  - OpenTofu, with Terraform opt-in
  - lint and security tools (tflint, trivy, terraform-docs, infracost)
  - secrets tools (sops, age)
  - Kubernetes tooling
  - pre-commit hooks
- **`AGENTS.md`** is present, plus a `CLAUDE.md` that imports it.
- **One agent skill per selected provider** is present. Each skill covers best practices, reference architecture, landing zones, IAM, a CLI cheatsheet and IaC conventions.
  - It sits in `.claude/skills/<provider>`, with `.agents/skills/<provider>` pointing to it, so Claude Code, Codex, Cursor, Gemini, opencode and Copilot all find it.
- **MCP servers for every selected provider are configured by default** in `.mcp.json`, for AWS, Azure, GCP and OCI, with Kubernetes and OpenTofu/Terraform added where relevant.
  - Once the user is logged in with the provider CLI, an agent can use them to connect, debug, manage live resources and discover what a project needs.
  - Each server reuses the CLI's local credentials (`aws sso login`, `az login`, `gcloud auth application-default login`, `oci session authenticate`).
  - The devenv shell provides the runtimes the servers need (`uv`, `nodejs`), so no global installs are required.
- **Shared modules keep projects current.** Provider modules live in this repo, and a project picks up improvements with `devenv update`.
- **CI proves it works.** Every template builds and passes its tests.

v1 providers are AWS, Azure, GCP, OCI and Kubernetes. The layout makes a new provider a new folder, not a redesign.

## Affected users and systems

- **Developers** starting cloud or IaC projects on Linux (x86_64) and macOS (aarch64) with Nix and devenv installed.
- **AI coding agents** working in those projects.
- **This new public GitHub repo, its CI** (GitHub Actions) and the devenv binary cache.
- **No NixOS host configuration** is touched.

## Constraints

- **Standalone devenv.** Must use standalone devenv, the mode devenv recommends. Generated projects must not need flakes or `--no-pure-eval`.
- **No unfree packages by default.** Tools must come from nixpkgs where possible. `terraform` and `packer` (BUSL) are opt-in only.
  - Because of how devenv imports work, `allow_unfree` must be set in the project's own `devenv.yaml`.
- **Never overwrite user files.** A second provider must merge in, not clobber.
- **Skills follow the Agent Skills spec:** only `name` and `description` in frontmatter, `name` equal to the directory name, and each `SKILL.md` under 500 lines.
- **Skill content traces to official sources:**
  - AWS Well-Architected and Control Tower
  - Azure Well-Architected, CAF and landing zones
  - Google Cloud Well-Architected Framework and landing zones
  - OCI best-practices framework and the CIS Landing Zone
- **Public repo:** no secrets, credentials or account IDs anywhere. MIT licence.
- **MCP servers must be official vendor servers:**
  - AWS: `awslabs` / Agent Toolkit for AWS
  - Azure: `microsoft/mcp` / `azure-mcp`
  - GCP: `googleapis/gcloud-mcp`
  - OCI: `oracle/mcp`

  Each must be pinned to a version and must use the user's existing CLI login, never embedded credentials.
- **Access defaults to read-only where the server supports it.** Mutating tools (create, delete) need explicit opt-in, so an agent can't change cloud resources by accident.
- **Secrets are stored encrypted with agenix.** API keys, PATs and tokens (for example the Infracost API key, a GitHub PAT, or cloud MCP tokens) are encrypted with agenix (age) to recipients listed in `secrets.nix`.
  - The encrypted `secrets/*.age` files are safe to commit, even in public repos.
  - Plaintext never lands on disk inside the project or in git.
  - Secrets are decrypted only for the process that needs them, such as a CLI or MCP server.
  - Adding, editing and rotating a secret each take one command.
- **AWS auth uses `aws-vault`.** It ships with the devenv `aws-vault` integration.
- **Minimal code:** one init script and one shared module per provider, with no duplicated template sources. Single-provider templates are generated by the same script, and CI checks they are not stale.

## Decisions (approver answers, 2026-09-15)

1. **Licence:** MIT.
2. **MCP:** servers are configured for AWS, Azure, GCP and OCI, read-only by default. Mutating tools are opt-in.
3. **Heavy tools:** CDK and SAM are opt-in, and `azd` is out of scope (accepted by not objecting).
4. **AWS auth helper:** `aws-vault`.
5. **Secrets:** agenix is required for API keys, PATs and other tokens.
6. **More providers:** not decided. They are deferred to follow-up issues after v1.
