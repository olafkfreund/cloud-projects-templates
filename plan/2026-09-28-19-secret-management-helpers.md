---
status: draft
issue: 19
spec: spec/2026-09-28-19-secret-management-helpers.md
---

# Plan: Secret deletion and recipient helpers

Implement the missing agenix operations in the shared common devenv module so
all generated provider projects receive the same safe secret workflow.

## Steps

1. `modules/common/devenv.nix`: add `openssh` to the helper runtime packages;
   implement `secret-delete` with strict name/path/declaration checks; implement
   `secret-user-add` with `ssh-keygen` validation, duplicate detection, safe
   recipient insertion, and rollback around `secret-rekey` → verify shellcheck
   and generated evaluation.
2. `skills/secrets/SKILL.md`: document deletion, adding a user, rekeying, and
   the permanent Git-history limitation → verify the command guidance matches
   the actual scripts.
3. `templates/base/AGENTS.md`: add the two commands and their safety boundary
   to generated-project instructions → verify all generated provider guidance
   receives the shared policy.
4. `tests/secrets.sh`: exercise successful and refusal paths with temporary
   keys, verify ciphertext remains decryptable, and verify no plaintext value
   appears → run the disposable generated-project secret test.
5. Run `nix flake check` and inspect the generated template diff → verify no
   stale generated files or unrelated changes.

## Tests

- `bash tests/secrets.sh` inside a freshly generated disposable project.
- `nix flake check`.
- Shellcheck and generated-template freshness checks included by the flake.

## Rollback

Revert the module, skill, template guidance, and test commits. Existing
encrypted secrets remain usable with the current `secret-rekey` and
`secret-run` commands.
