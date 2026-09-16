# AGENTS.md — cloud-projects-templates

This repo **produces** cloud project environments. It is not a cloud project itself.
Generated projects get their own `AGENTS.md` from `templates/base/AGENTS.md`.

## Layout

| Path | What |
|---|---|
| `flake.nix` | `apps.default` (init script), `templates.*`, `checks` |
| `pkgs/init.sh` | The only code path that builds a project, including the committed `templates/<p>` |
| `pkgs/regenerate-templates.sh` | Maintainer wrapper: stages fresh projects, then replaces generated provider directories |
| `modules/<p>/devenv.nix` | Tools, hooks and `enterTest` per provider. Imported remotely by projects as `cloud/modules/<p>` |
| `modules/<p>/mcp.json` | Read-only MCP servers merged into the project's `.mcp.json` |
| `skills/<p>/` | Agent Skills copied to `.claude/skills/<p>`. `secrets` and `terraform` are always copied |
| `templates/base/` | Files every project starts with |
| `templates/<p>/` | **Generated. Never hand-edit.** Regenerate all providers from the repo root with `nix run .#regenerate-templates` |

## Rules

- **Terraform is the only IaC CLI.** It is the one permitted unfree package.
- **MCP servers are pinned to exact versions and read-only by default.** They never carry embedded credentials.
- **Secrets use agenix** (`secret-add`, `secret-run`). Never put plaintext in the repo, in logs or in chat.
- **Skill format.** Frontmatter has only `name` (equal to the directory name) and `description`. `SKILL.md` stays at or under 500 lines, and each file in `references/` at or under 300. Link official sources.
- **Before pushing,** run `nix flake check`. It fails on stale `templates/` or skill format errors.

## Adding a provider `<p>`

1. Add `modules/<p>/devenv.nix` (packages and an `enterTest` with `--version` checks) and `modules/<p>/mcp.json` (read-only).
2. Add `skills/<p>/SKILL.md` and `references/`.
3. Add `<p>` to the provider list in `flake.nix` and to the CI matrix.
4. Add new source files to Git's index so Nix includes them, then run `nix run .#regenerate-templates` and `nix flake check`.

## Workflow

Tasks follow intent → spec → plan (`intent/`, `spec/`, `plan/`), and each needs approval before the next stage starts.
When implementing, cite the plan step. If you must deviate, update `plan/` in the same commit as the code.
