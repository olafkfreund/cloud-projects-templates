---
status: draft
issue: 18
author: olafkfreund
---

# Intent: Complete onboarding and usage documentation

## Problem

The root README and provider references were updated for automated onboarding,
but the documentation does not yet provide a consistent first-use journey:

- Generated projects have agent instructions but no user-facing README.
- The root first-assessment walkthrough is AWS-only, although commands now exist
  for all eight providers. Credential preparation, scope selection and identity
  expectations are scattered across technical references.
- The provider routing table suggests GCP organization discovery and OCI Cloud
  Advisor collection, while the automated collectors support one GCP project
  and explicitly defer OCI Advisor ingestion.
- The tool tables highlight only the AWS onboarding executable; contributor
  validation text describes AWS fixtures without the new multi-provider checks.
- Existing-project update guidance repeats itself and lacks one clear sequence
  for module updates, copied documentation/skills/recipes and custom task files.
- Users lack a concise troubleshooting path for unavailable commands, identity
  mismatches, denied reads, collection limits and protected report paths.

Existing command examples, provider coverage/permission references and the
report schema guide are useful and should remain the basis for the corrections.

## Proposed outcome

A user can navigate from the repository README or a generated project's README
through setup, existing read-only credentials, explicit provider scope, a first
assessment, report interpretation and a subsequent reassessment. All eight
providers and shell/direnv, just and flake entry points are discoverable.

Documentation distinguishes failed checks from incomplete evidence, explains
exit codes and private report handling, accurately states automated coverage,
and helps users troubleshoot common failures without widening access or changing
cloud resources. Existing-project users can update remote modules and review
copied-file changes without losing customizations.

## Affected users and systems

Repository readers, users of new and existing generated projects, and agents
following the shared onboarding references. Likely affected sources are the
root README, generated-project documentation sources, shared command/provider
references, and any necessary generator adoption logic and checks. Generated
provider templates must be refreshed through the maintainer command.

## Constraints

- Keep documentation aligned with implemented CLI help and report behavior;
  do not add collector features or claim live-account validation.
- Reuse existing references instead of duplicating provider permission catalogs.
- Preserve custom READMEs, task files, skills and other project content.
- Do not hand-edit generated templates or expose credentials/report contents.
- Respect skill/reference size limits if those files change.
- Validate local links, documented commands and generated-template freshness;
  run the repository-required flake checks before pushing implementation.
- Follow the issue-driven intent → spec → plan approval gates.

## Open questions

None. The design stage will specify documentation locations, navigation and
safe adoption behavior for existing projects.
