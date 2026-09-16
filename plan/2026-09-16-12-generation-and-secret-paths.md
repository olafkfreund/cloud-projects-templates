---
status: draft
issue: 12
spec: spec/2026-09-16-12-generation-and-secret-paths.md
---

# Plan: Reliable generation and secret path handling

Implement on `fix/12-generation-and-secret-paths`. No implementation starts until this plan is approved. Each implementation update cites the relevant step; any deviation changes this plan in the same commit as the code.

## Approved decisions

### D1. Regeneration is a separate maintainer operation

- Keep ordinary `pkgs/init.sh` initialization and provider addition non-overwriting for user-owned files, including skills and existing MCP customizations.
- Add `pkgs/regenerate-templates.sh` and expose it as `nix run .#regenerate-templates` from `flake.nix`. It runs at the checkout root and uses the same packaged initializer as the default app, with providers supplied from the existing flake provider list.
- Validate the current directory is its Git worktree root and contains `flake.nix`, `pkgs/init.sh`, and `templates/base`. Reject symlinked template roots/provider destinations and nested Git repositories in provider destinations before any replacement.
- Generate every provider in temporary staging before replacing anything. On generation failure, the checkout is untouched. Remove staging `.git` directories, then replace only the fixed `templates/<provider>` destinations, including removal of obsolete generated content. Never replace `templates/base`.
- Clean staging on exit. A filesystem failure during replacement may leave a partial refresh; fail visibly and document Git recovery. The command explicitly states that generated directories are replaced.
- Update the freshness-check diagnostic, `AGENTS.md`, and `README.md` to use this command. Regenerate committed templates through it, never by hand.

### D2. Parse and update YAML imports

- Add `pkgs.yq-go` to the initializer's runtime inputs; do not add a custom YAML parser.
- Validate any existing `devenv.yaml` before project mutations, including Git initialization: exactly one mapping document with an `imports` sequence containing only strings. Reject malformed YAML and unsupported shapes with an actionable error and no project changes. Adapting unrelated, uninitialized devenv projects is outside this task.
- Append missing provider imports by parsed string equality. Preserve import order and unrelated semantic settings; preserve comments where the emitter supports them. Support settings after imports, quoted items, and inline sequences.
- If all requested imports already exist, do not rewrite YAML. Otherwise write to a temporary sibling and rename only after successful transformation and parsing. Clean temporary files on failure.
- Formatting may normalize on an actual update; document this limit. Remove the obsolete imports-last comment from `templates/base/devenv.yaml`.
- Preserve skill copying, MCP merge behavior, and provider instruction sections.

### D3. Recipient paths are data, not Nix source

- Change the shared `recipient_args` in `modules/common/devenv.nix` to a fixed Nix function expression receiving the absolute secrets filename and secret name with `nix-instantiate --argstr`.
- Import the supplied path string and select the secret attribute without interpolating either argument into source text. Both `secret-add` and `secret-rekey` use the same fix.
- Retain secret-name validation, nonempty-recipient checks, runtime-only encryption/decryption, and ciphertext replacement only after successful encryption. No plaintext files or logged secret values.

### D4. Focused checks with existing tools

- Use small shell regression scripts and standard-library Python for the MCP handshake; no test framework or MCP client dependency.
- Wire offline generator and generated-MCP-configuration assertions into `flake.nix` checks. Do not download MCP packages or contact cloud endpoints in flake checks.
- Generator cases: customized YAML, alternate import syntax, multiple providers, byte-stable repeat runs, malformed documents and invalid import types rejected without mutation, preservation of user skills/MCP overrides, stale/missing/obsolete generated files repaired, repeat regeneration unchanged, and unsafe destinations rejected before replacement.
- Extend the existing secrets smoke test to a project path with spaces. Use disposable age credentials and the actual generated scripts; test add/run/rekey round trips without printing plaintext, recipient-evaluation failure preserving existing ciphertext, and the existing plaintext-file commit-hook rejection.
- Check generated MCP server object and command/argument shapes, exact npx/uvx package pins, configured read-only restrictions, read-token mappings, and the GCP allowlist's presence and expected contents.
- Add a bounded local Terraform MCP handshake in the Linux CI environment. Read its command/arguments from generated `.mcp.json`; send `initialize`, `notifications/initialized`, and `tools/list`; assert successful responses and a nonempty tool list. Never invoke a tool or supply credentials. Enforce timeout and process cleanup. Python is test-only, not added to all generated projects.
- These checks do not prove cloud-provider compatibility or authorization. Required tests exclude cloud-provider startup and remote endpoints; live-account read-success/write-rejection verification stays in #11. Document the limit.

### D5. Scope and tradeoffs

- No changes to installed provider versions, cloud resources, real credentials, or machine configuration.
- Reject overwrite-in-place for user projects, overwrite-only regeneration that leaves deleted files behind, line-based YAML parsing, and ad hoc Nix-source escaping.
- Preserve the existing provider CI matrix and its informative-only macOS policy. Report actual platforms exercised rather than implying unrun platforms passed.

## Steps

1. **Structural imports and generator regression checks.**
   - Update `pkgs/init.sh` to preflight existing YAML and update its imports structurally and atomically under D2.
   - Add `yq-go` to the initializer in `flake.nix`; add `tests/generation.sh` and expose a `generation` flake check with its required command paths supplied explicitly.
   - Test a generated project customized with settings after imports, quoted and inline lists, multiple providers, existing skill edits, and MCP overrides. Compare snapshots on a second run.
   - Test malformed YAML, multiple documents, non-mapping roots, and imports containing a scalar, mapping, or non-string element. Snapshot before each failing invocation and assert no changes, including no new Git directory.
   - Remove the imports-last requirement from `templates/base/devenv.yaml`.
   - → Verify: build the initializer (its shellcheck must pass) and run `checks.<system>.generation`. Full freshness validation follows regeneration in step 5.

2. **Safe maintainer regeneration.**
   - Add `pkgs/regenerate-templates.sh`; expose the package and app in `flake.nix`, using its existing provider list and packaged initializer.
   - Implement D1 preflight, all-provider staging, fixed-destination replacement, `.git` cleanup, and exit cleanup. Use a temporary sibling of the checkout for staging so staging does not become template content.
   - Extend `tests/generation.sh` with temporary Git checkout fixtures containing the required layout. Introduce stale file content, a missing file, and an obsolete generated file, then compare regenerated output against fresh initialization for all providers.
   - Assert second-run equality. Assert non-root invocation, template-root/provider symlinks, and nested Git repositories are rejected without changing other destinations. Inject an initializer failure through the script's test invocation to verify no destination changes before all generation succeeds.
   - → Verify: generation flake check passes and the new packaged shell script passes shellcheck.

3. **Secret path fix and reusable secrets smoke test.**
   - Update only the shared recipient argument evaluation in `modules/common/devenv.nix` under D3.
   - Move the existing smoke-test assertions into `tests/secrets.sh` so local runs and `.github/workflows/ci.yml` execute the same test. Keep disposable identity setup, round-trip assertions, plaintext scan, and commit-hook rejection; never enable shell tracing.
   - Generate the test project under a directory with spaces. Test secret-add and rekey success, then deliberately cause recipient evaluation to fail and assert a nonzero exit and unchanged ciphertext. Restore the fixture and confirm decryption still works.
   - Keep test values and private test identity out of tracked files and command output; remove disposable files on exit.
   - → Verify: run the script inside a generated devenv shell with the cloud input overridden to this checkout; run `devenv test` for the shared module change.

4. **MCP configuration assertions and local handshake.**
   - Add `tests/mcp-config.sh`, invoked by an offline flake check against freshly generated provider projects, implementing D4 configuration assertions.
   - Add `tests/mcp-smoke.py`, a small stdlib-only test for the Terraform server selected from a generated `.mcp.json`. Use a fixed overall deadline, match response IDs, reject protocol errors, and terminate/reap the process on every exit path.
   - Wire the local handshake into the existing Linux CI test environment, supplying Python only for the test. Clear inherited Terraform/cloud credentials for the child; do not resolve or launch other configured servers.
   - → Verify: offline MCP assertions pass; Terraform initialization and tool discovery pass. A deliberately invalid command and a silent fake child both fail promptly and leave no running child process.

5. **Documentation and regenerated templates.**
   - Update `AGENTS.md`, `README.md`, and the stale-template error in `flake.nix` with `nix run .#regenerate-templates` and its replacement semantics.
   - Document YAML formatting normalization and the precise MCP verification boundary, retaining #11 for live-account permissions.
   - Add new source files to Git's index before invoking the flake so its source snapshot includes them. Run the regeneration app; inspect all template changes, including the base YAML comment removal and any emitter formatting changes.
   - → Verify: every provider template matches fresh initialization; repeat regeneration and confirm a byte-identical snapshot; run `nix flake check -L`.

6. **Final verification and PR.**
   - Run the focused checks listed below and workflow linting; inspect the final diff for scope, plaintext, and unintended generated changes.
   - Commit implementation with Conventional Commit messages referencing #12. Preserve separate approval commits; include any approved-plan deviations with their corresponding implementation commit.
   - Push the task branch only after `nix flake check` passes. Open a PR with `Closes #12` and links to the intent, spec, and this plan, and run the existing CI provider matrix.
   - → Verify: required Linux CI is green; report macOS results and any unavailable runtime verification. Do not merge as part of this task.

## Tests

Run commands individually and inspect each result. Resolve `<system>` from `builtins.currentSystem` before using the targeted flake attributes.

| Check | Command or procedure | Expected result |
|---|---|---|
| Generator package | `nix build .#default --no-link` | Shellcheck/build succeeds |
| Generator regressions | `nix build .#checks.<system>.generation --no-link -L` | All YAML, preservation, regeneration, and failure cases pass |
| MCP configuration | `nix build .#checks.<system>.mcp-config --no-link -L` | All provider configurations satisfy their offline assertions |
| Full flake | `nix flake check -L` | Freshness, skills, generator, and MCP configuration checks pass |
| Regeneration | `nix run .#regenerate-templates`, snapshot templates, repeat, compare | Second run changes no files |
| Secrets/runtime | Generate a temporary AWS project whose path contains spaces; enter it with `devenv --override-input cloud "path:<checkout>" shell -- bash <checkout>/tests/secrets.sh` | Add/run/rekey and failure-preservation assertions pass; plaintext hook rejects a staged plaintext file |
| Shared environment | In that project: `devenv --override-input cloud "path:<checkout>" test` | Package version checks and hooks pass |
| Terraform MCP | In the generated environment with test-only Python: `python3 <checkout>/tests/mcp-smoke.py .mcp.json` | Initialize and tools/list succeed within deadline, with no tool invocation |
| Workflow lint | Run actionlint against `.github/workflows/ci.yml` using the available executable or an ephemeral Nix shell | No workflow errors |
| Provider matrix | Existing GitHub Actions jobs for all providers and combinations | Required Linux jobs pass; macOS results reported under existing policy |
| Diff hygiene | `git diff --check` and inspect changed source/generated files | No whitespace errors, plaintext credentials, or unintended scope changes |

No cloud-provider MCP startup or live-account authorization check is implied by these results; that work remains in #11.

## Rollback

- Before implementation, this branch contains only task documents and approval records; no runtime behavior has changed.
- Revert individual implementation commits to roll back source, tests, documentation, and their regenerated artifacts together. Preserve unrelated user changes.
- If regeneration fails during replacement, inspect `git diff` and restore only affected tracked `templates/<provider>` paths from the known-good commit. Remove only confirmed regeneration-created untracked files. Never clean the whole checkout or restore `templates/base` indiscriminately.
- Existing generated projects remain pinned to their cloud input until updated. Projects that already updated can pin their cloud input to the prior known-good revision; do not delete their lockfile or overwrite local customizations.
- Tests use disposable identities and no real cloud credentials. A code rollback does not undo real secret rotation or revoke historical ciphertext; this task performs neither.
