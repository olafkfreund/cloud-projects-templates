---
status: draft
issue: 19
author: olafkfreund
---

# Intent: Secret deletion and recipient helpers

## Problem

Generated projects already provide agenix helpers for adding, editing,
listing, running, and rekeying encrypted secrets. They do not provide a safe,
discoverable way to delete a secret or add another authorized user to the
recipient set. Users must edit `secrets.nix` manually, which makes malformed
entries and incomplete rekey operations more likely.

## Proposed outcome

Generated projects provide credential-free shell helpers to delete one
encrypted secret and to add a validated SSH public key as an authorized
recipient. The operations leave `secrets.nix` and encrypted files in a
reviewable Git diff and never expose secret values.

## Affected users and systems

- Users of generated AWS, Azure, GCP, Kubernetes, and other cloud projects.
- `modules/common/devenv.nix` and its generated copies.
- `skills/secrets/SKILL.md` and generated agent guidance.
- `tests/secrets.sh` and the generated-project checks.

## Constraints

- Keep the existing agenix/age format and command surface.
- Secret names must remain safe environment-variable identifiers.
- Public keys must be validated before modifying recipients.
- Never accept secret values as command-line arguments or print them.
- Deletion must refuse missing or ambiguous targets and must not remove a
  directory outside `secrets/`.
- Adding a user must make the rekey requirement explicit; changing recipients
  without re-encrypting is not success.
- Preserve the unrelated in-progress documentation work already on the base
  branch.

## Open questions

- Should adding a user automatically rekey all secrets, or require a separate
  explicit `secret-rekey` confirmation after updating recipients?
- Should deletion remove the recipient declaration immediately and leave the
  encrypted file staged for review, or remove both together atomically?
