---
status: approved
issue: 12
intent: intent/2026-09-16-12-generation-and-secret-paths.md
---

# Spec: Reliable generation and secret path handling

## Design

### 1. Separate repository regeneration from project initialization

Keep `pkgs/init.sh` non-overwriting for ordinary project initialization and provider additions. Add a maintainer app, `nix run .#regenerate-templates`, backed by `pkgs/regenerate-templates.sh`, which runs from the repository root and rebuilds every provider in the existing `flake.nix` provider list.

The app uses the same packaged initializer as `apps.default`. Generate all providers into a temporary directory first; if any generation fails, leave the checkout's templates untouched. After successful generation, remove temporary `.git` directories and replace only the fixed `templates/<provider>` directories with the fresh output. This removes obsolete generated files as well as updating existing ones. Never replace `templates/base`.

Before replacement, require the current directory to be its Git worktree root, verify the repository layout (`flake.nix`, `pkgs/init.sh`, and `templates/base`), and reject symlinked template roots/provider destinations or nested Git repositories in provider destinations. The command explicitly documents that generated provider directories are replaced. Temporary staging is cleaned on exit. Filesystem failure during replacement may leave a partial refresh; report failure and use Git to restore affected generated directories.

Update the freshness-check diagnostic in `flake.nix`, contributor instructions in `AGENTS.md`, and regeneration instructions in `README.md` to use this app. Regenerate committed templates through it. Ordinary initialization continues preserving user-owned files and existing MCP customizations.

### 2. Update the YAML imports list structurally

Add `pkgs.yq-go` to the initializer's runtime inputs in `flake.nix`; it is already used in `modules/common/devenv.nix`. In `pkgs/init.sh`, replace the EOF append with an update to the top-level `imports` sequence.

For an existing `devenv.yaml`, validate a single mapping document whose `imports` value is a sequence of strings before making project changes. Reject malformed YAML and unsupported imports shapes with an actionable error and leave the project unchanged. Supporting unrelated, uninitialized devenv projects is outside this fix.

Append only absent provider imports using parsed string equality, preserving their existing order, unrelated settings, and existing comments where supported by the YAML emitter. Skip rewriting when every requested import is already present, making repeated additions byte-stable. Write changed YAML to a temporary sibling and rename only after successful parsing and transformation. Formatting may be normalized on the first actual update; document this limitation.

Remove the obsolete requirement that `imports` be last from `templates/base/devenv.yaml`. Preserve existing behavior for skills, MCP merges, and provider instruction sections.

### 3. Pass recipient inputs as data

In the shared `recipient_args` function in `modules/common/devenv.nix`, use a fixed Nix function expression with `nix-instantiate --argstr` arguments for the absolute `secrets.nix` filename and the secret name. Import the supplied path string and select the corresponding secret attribute without interpolating either value into Nix source.

Keep encryption and decryption at runtime. Both `secret-add` and `secret-rekey` use this shared function, so both receive the fix. Retain secret-name validation, nonempty-recipient checks, and ciphertext replacement only after successful encryption.

### 4. Focused regression and MCP coverage

Add a small shell regression script under `tests/` and wire it into `flake.nix` checks. Use temporary fixtures, the packaged initializer, and the regeneration app. Cover:

- Customized YAML with a setting after imports, quoted/inline imports, and multiple providers: the intended list changes and unrelated values survive.
- Repeated provider addition: no duplicates and no content changes on a second run.
- Malformed YAML or invalid imports types: failure without project mutation.
- Existing user skills and MCP overrides: preserved during ordinary provider addition.
- Stale, missing, and obsolete generated files: regeneration produces exactly fresh initializer output; a second regeneration has no diff.
- Unsafe regeneration destinations: rejected before replacing any template.

Extend the existing secrets CI smoke test in `.github/workflows/ci.yml` to use a project directory containing spaces. Exercise actual `secret-add`, `secret-run`, and `secret-rekey` scripts with a disposable age identity. Verify round trips through assertions, without printing plaintext; retain the plaintext-file hook check. Include recipient evaluation failure and assert existing ciphertext is unchanged.

Add offline assertions to the flake checks for generated MCP configuration: valid server objects and command/argument shapes, exact package pins for npx/uvx servers, required read-only flags/environment restrictions where currently configured, read-token mappings, and the GCP allowlist file's presence and expected contents. Test the generated configurations, so merge or copy regressions are detected too.

Add one bounded Terraform MCP stdio smoke test to the existing Linux CI environment. Launch it using its generated command/arguments, send `initialize`, `notifications/initialized`, and `tools/list`, and assert successful protocol responses and a nonempty tool list. Use a small standard-library Python script under `tests/`, with a timeout and child-process cleanup; it must not invoke tools or supply credentials. Provide Python only to the CI test environment, not every generated project.

The offline configuration checks do not establish provider-server compatibility or authorization. Remote endpoints and cloud-provider MCP startup are excluded from required tests in this task because they can depend on registry downloads, authentication, and browser flows. Live-account read success/write rejection remains tracked by issue #11; document this limit rather than claiming complete MCP runtime verification.

## Alternatives rejected

- Overwrite files in the ordinary initializer: would destroy user edits and MCP overrides.
- Only overwrite generated files without removing old files: leaves deleted source content in published templates.
- Keep appending YAML or implement a line-based YAML parser: fails on valid customized layouts and alternate YAML syntax.
- Escape spaces in the embedded Nix expression: leaves other special characters untreated; typed arguments remove the source interpolation.
- Launch every cloud server in required CI: adds authentication/network-dependent failures and cannot prove read-only permissions without live accounts.
- Add a test framework or general MCP client library: shell assertions and Python's standard library cover this scope.

## Risks

- The regeneration command deliberately replaces generated provider directories. Scope checks, generation before replacement, and Git recovery bound this risk; user projects must use the ordinary initializer.
- YAML formatting can change during an actual provider addition; semantic settings and import order must be preserved.
- Tests that resolve MCP packages or contact remote servers would be nondeterministic; keep flake checks offline and the handshake local to the installed Terraform server.
- This task does not change installed provider versions, cloud resources, account credentials, or system configuration.

## Verification

- `nix flake check -L`: existing freshness/skill checks and new generator/MCP configuration regressions pass on the current system.
- Run the maintainer regeneration command twice: first output matches fresh generation, second run changes nothing.
- Run the updated secrets smoke test in a generated project with spaces, overriding the cloud input to this checkout; creation, execution, and rekeying succeed, and failure preserves ciphertext.
- Run the Terraform MCP handshake check in the generated environment; initialization and tool discovery succeed within the timeout without cloud access.
- Run the existing provider CI matrix and workflow linting after implementation. Preserve the current informative-only macOS policy and report which platforms were actually tested.
- Inspect the final diff: only intended source, tests, documentation, and regenerated artifacts change; no plaintext credentials appear.
