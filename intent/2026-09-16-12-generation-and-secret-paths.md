---
status: approved
issue: 12
author: olafkfreund
---

# Intent: Reliable generation and secret path handling

## Problem

The review reproduced three failures:

- Regenerating committed templates retains old skills and other generated content, so the documented regeneration command cannot repair stale templates.
- Adding a provider appends its import at the end of devenv.yaml, which can corrupt the configuration when another top-level setting follows imports.
- Secret recipient evaluation treats the project path as Nix source; spaces in that path cause a syntax error in secret-add and secret-rekey.

Existing checks pass despite these failures. CI also lacks MCP startup/configuration smoke coverage.

## Proposed outcome

- Maintainers can regenerate committed templates to match their source, including changed and removed generated content.
- Users can add providers to customized project configurations without corrupting YAML or losing their settings; repeated additions remain idempotent.
- Secret creation and rekeying work in project directories containing spaces, without exposing plaintext.
- Automated regression checks catch all three reproduced failures.
- The design identifies useful credential-free MCP startup/configuration checks and their practical limits. Live-account permission verification remains in issue #11.

## Affected users and systems

Repository maintainers, users of generated projects across all providers, the shared secrets scripts, and CI. No cloud resources or machine configuration need to change.

## Constraints

- Preserve user-owned files and existing MCP customizations when adding providers.
- Generate committed templates through the shared generator; never hand-edit them.
- Keep secrets at runtime and never write or log plaintext during verification.
- Use temporary projects and disposable test credentials for regression checks.
- Keep the implementation small and reuse existing tools where practical.
- Run nix flake check and targeted regression checks before completion; do not require live cloud credentials for these tests.
- Follow separate intent, spec, and plan approval commits before implementation.

## Open questions

None for problem framing. The spec will resolve regeneration behavior, safe YAML updates, path handling, and feasible MCP smoke-test scope.
