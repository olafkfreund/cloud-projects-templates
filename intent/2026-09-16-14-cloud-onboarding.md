---
status: approved
issue: 14
author: olafkfreund
---

# Intent: Cloud onboarding and evidence-based reporting

## Problem

Generated projects include provider guidance and troubleshooting commands, but
have no repeatable onboarding assessment or consistent report of environment
state, missing controls, and assessment coverage. An inaccessible resource can
be mistaken for an absent resource, and configuration checks alone cannot prove
operational readiness or compliance. Some existing discovery instructions also
depend on unavailable tools or operations that change the environment.

## Proposed outcome

- Generated projects have shared cloud-onboarding and cloud-troubleshoot skills
  that build on the existing provider references.
- The first release provides a complete, bounded AWS onboarding workflow with
  explicit account and region scope, resource discovery, evidence-based checks,
  and local human-readable and machine-readable reports.
- Reports identify the observed state, priority improvements, evidence sources,
  collection time, tool/check versions, and coverage limitations. Results
  distinguish pass, fail, unknown, not applicable, and manual review.
- Reports distinguish missing controls from denied access, unsupported checks,
  disabled services, and collection failures. They do not claim completeness
  outside the declared scope or treat a configured backup as a proven restore.
- All eight providers have clear onboarding and troubleshooting guidance, with
  automated versus manual coverage stated honestly. Additional provider
  collectors and baseline comparison are follow-up work, not implied features
  of the AWS first release.
- Troubleshooting gathers relevant evidence for a named symptom and explains
  likely causes, uncertainty, and next steps without changing cloud resources.
- Known guidance gaps are addressed: Azure Resource Graph availability, GCP
  asset-discovery access, read-only Kubernetes assessment, and invalid discovery
  or credential-helper examples encountered in the affected references.
- Existing projects can adopt the shared skills without silently overwriting
  local customizations. New projects receive them through the normal generator.

## Affected users and systems

Maintainers and users of generated AWS, Azure, GCP, OCI, Kubernetes, Cloudflare,
Hetzner, and DigitalOcean projects. Changes may affect shared skills, provider
references and tools, the generator, report handling, documentation, tests, and
regenerated templates. This repository remains a project generator, not a hosted
cloud monitoring service.

## Constraints

- Use existing provider CLIs, native APIs, and established assessment tools where
  useful; avoid building another general-purpose scanner or dashboard.
- Discovery and assessment are read-only. Do not enable services, change roles,
  create Kubernetes collector jobs, execute workload commands, or remediate
  resources as part of onboarding. Mutating follow-up actions are separate work.
- Require explicit target scope and verify identity before collection. Record
  pagination, inaccessible scopes, timeouts, and partial failures honestly.
- Collect selected metadata rather than unrestricted payloads, secret values,
  or application logs. Keep reports local and Git-ignored by default; metadata
  can still be sensitive and must not be published automatically.
- Best-practice findings must have identifiable evidence and official references.
  Business context and unobservable controls require manual review; reports are
  not compliance certification. AI explanations must not invent collected facts.
- Preserve Terraform-only IaC, agenix secret handling, declarative project tools,
  pinned read-only MCP configuration, and repository skill-format requirements.
- Verify behavior with credential-free tests, including partial collection and
  denied access. Regenerate templates and pass nix flake check before pushing
  implementation. Live-account validation requires an explicitly selected scope
  and available credentials; it must not be represented as completed otherwise.
- Follow separate intent, spec, and plan approval gates before implementation.

## Open questions

None blocking intent review. AWS is the proposed first automated provider;
the specification will enumerate supported resources and checks, report fields,
permission requirements, and safe existing-project adoption behavior.
