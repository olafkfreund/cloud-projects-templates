---
status: approved
issue: 19
intent: intent/2026-09-28-19-secret-management-helpers.md
---

# Spec: Secret deletion and recipient helpers

## Design

Extend `modules/common/devenv.nix`, which is imported by every generated
project, with two scripts:

- `secret-delete NAME` accepts only the existing environment-variable name
  format. It requires the exact `secrets/$NAME.age` ciphertext and matching
  declaration in `secrets.nix`, refuses symlinks and missing/ambiguous targets,
  removes both entries, and reports the Git diff without reading the secret.
- `secret-user-add PUBLIC_KEY [LABEL]` validates one SSH public key with
  `ssh-keygen`, rejects duplicates and malformed keys, adds it to the shared
  `recipients` list in `secrets.nix`, then invokes the existing `secret-rekey`
  flow. If rekeying cannot complete, it restores the recipient declaration and
  refuses success. The optional label is constrained to safe comment text.

Add `openssh` to the helper runtime packages for public-key validation. Keep
secret values on stdin or in the existing hidden prompt; no helper accepts a
secret value as an argument or writes plaintext to disk.

Update the secrets skill and generated `AGENTS.md` guidance with the commands,
including the important distinction that removing a recipient from
`secrets.nix` requires rekeying and rotating credentials that may remain in Git
history.

Extend `tests/secrets.sh` with disposable-key cases for successful user add and
rekey, duplicate/malformed key refusal, successful delete, missing-secret
refusal, and proof that the encrypted value remains unrevealed. Keep the test
credential-free and use the existing temporary identity.

## Alternatives rejected

- **Require users to edit `secrets.nix` manually:** rejected because it is the
  exact onboarding gap this issue addresses.
- **Add a second SOPS backend:** rejected for this change; the generated
  projects already standardize on agenix-format age files and one helper
  surface.
- **Let `secret-user-add` only edit recipients:** rejected because existing
  ciphertext would not be usable by the new recipient until rekeyed.
- **Accept a secret value as a positional argument:** rejected because shell
  history and process inspection can expose it.

## Risks

- A failed rekey can leave some ciphertext files updated before the command
  stops; the original recipient remains in the list until a successful run, so
  the command must preserve recovery and report the partial state.
- Removing a recipient cannot revoke access to old Git revisions; the skill must
  require provider-side rotation for compromised secrets.
- `ssh-keygen` adds a small runtime dependency to every generated environment.

## Verification

- Run `tests/secrets.sh` in a generated project with a temporary age identity.
- Run `nix flake check` for generated-template freshness, shell checks, and
  skill validation.
- Confirm `secret-delete --help` and `secret-user-add --help` do not require
  credentials or print secret values.
