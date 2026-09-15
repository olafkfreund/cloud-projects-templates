# IAM on Google Cloud

Verified 2026-09-15. Primary sources:
[Use IAM securely](https://docs.cloud.google.com/iam/docs/using-iam-securely),
[Service account best practices](https://docs.cloud.google.com/iam/docs/best-practices-service-accounts),
[Roles overview](https://docs.cloud.google.com/iam/docs/roles-overview).

## Principles

1. **Least privilege.** Predefined roles over basic roles; custom roles when
   a predefined one is still too broad
   ([Custom roles](https://docs.cloud.google.com/iam/docs/understanding-custom-roles)).
   Basic roles (`roles/owner`, `roles/editor`, `roles/viewer`) are a
   code-review reject on anything but a personal sandbox.
2. **Grant to groups**, at the lowest resource level that works. IAM
   inherits down the hierarchy, so an org-level grant reaches every project
   ([Groups](https://docs.cloud.google.com/iam/docs/groups-in-cloud-console)).
3. **Short-lived credentials only.** Human: ADC. Workload: attached service
   account or Workload Identity. CI: Workload Identity Federation. None of
   these produce a key file
   ([Short-lived credentials](https://docs.cloud.google.com/iam/docs/create-short-lived-credentials-direct)).
4. **Review with Recommender.** IAM role recommendations show unused
   permissions after 90 days; act on them
   ([Role recommendations](https://docs.cloud.google.com/policy-intelligence/docs/role-recommendations-overview)).

## Service accounts

[Best practices](https://docs.cloud.google.com/iam/docs/best-practices-service-accounts),
[Manage access](https://docs.cloud.google.com/iam/docs/manage-access-service-accounts)

- One SA per workload, named for its purpose (`sa-<app>-<env>`), created in
  the workload's project.
- Never use the default Compute or App Engine SA; they get Editor unless
  `iam.automaticIamGrantsForDefaultServiceAccounts` is enforced.
- `roles/iam.serviceAccountUser` on an SA lets a principal act as it; treat
  it as sensitive as the SA's own roles.
- `roles/iam.serviceAccountTokenCreator` is what impersonation needs; grant
  it on the SA resource, not the project.
- **Keys**: do not create them. If a legacy system forces one, rotate it,
  scope it, store it in agenix (`secret-add NAME`) and open a ticket to
  remove it ([Managing keys](https://docs.cloud.google.com/iam/docs/best-practices-for-managing-service-account-keys)).

## Human authentication: ADC + impersonation

[ADC](https://docs.cloud.google.com/docs/authentication/application-default-credentials),
[Provide ADC](https://docs.cloud.google.com/docs/authentication/provide-credentials-adc),
[Impersonation](https://docs.cloud.google.com/iam/docs/service-account-impersonation)

```sh
gcloud auth login                              # gcloud CLI itself
gcloud auth application-default login          # ADC for terraform / SDKs
gcloud config set auth/impersonate_service_account sa-terraform-dev@PROJECT.iam.gserviceaccount.com
```

Why impersonate: your user keeps only `roles/iam.serviceAccountTokenCreator`
on a few SAs; the SAs hold the real permissions. The audit log shows both
identities, and revoking access is one binding.

In the provider (see [terraform.md](terraform.md)):

```hcl
provider "google" {
  impersonate_service_account = var.terraform_sa
}
```

Or per-session: `GOOGLE_IMPERSONATE_SERVICE_ACCOUNT=sa@...`.

For AI-agent sessions, impersonate a Viewer-only SA; see [mcp.md](mcp.md).

## Workload identity

- **GKE**: Workload Identity Federation for GKE binds a Kubernetes SA to an
  IAM principal; no node SA sharing, no mounted keys
  ([GKE Workload Identity](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-identity)).
- **Cloud Run / Compute**: attach a dedicated runtime SA; the metadata
  server issues tokens
  ([Cloud Run identity](https://docs.cloud.google.com/run/docs/securing/service-identity),
  [Attach SAs](https://docs.cloud.google.com/iam/docs/attach-service-accounts)).
- **CI (GitHub Actions, GitLab)**: Workload Identity Federation exchanges
  the pipeline's OIDC token for a short-lived Google token. Restrict the
  attribute condition to the repo and branch that may deploy
  ([WIF](https://docs.cloud.google.com/iam/docs/workload-identity-federation),
  [WIF with pipelines](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)).

```hcl
resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.ci.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  attribute_condition = "assertion.repository == \"org/repo\""
  oidc { issuer_uri = "https://token.actions.githubusercontent.com" }
}
```

## Deny policies and access boundaries

- **Deny policies** override allow grants; use them for org-wide "never"
  rules such as blocking SA key creation or non-read-only MCP tool calls
  ([Deny overview](https://docs.cloud.google.com/iam/docs/deny-overview)).
- **Principal access boundary policies** cap what a set of principals can
  reach regardless of grants; useful for contractor or agent identities
  ([PAB policies](https://docs.cloud.google.com/iam/docs/principal-access-boundary-policies)).
- **Org policy** constrains what resources may look like; IAM constrains who
  may act. Use both ([Org policy](https://docs.cloud.google.com/resource-manager/docs/organization-policy/overview)).

## Auditing

[IAM audit logging](https://docs.cloud.google.com/iam/docs/audit-logging)

```sh
gcloud projects get-iam-policy PROJECT --format=yaml
gcloud asset search-all-iam-policies --scope=organizations/ORG_ID --query='policy:roles/owner'
gcloud logging read 'protoPayload.methodName="SetIamPolicy"' --project=PROJECT --limit=20
```

## Terraform patterns

- `google_project_iam_member` for additive grants; `_binding` replaces all
  members of a role, `_policy` replaces the whole policy and will delete
  grants made elsewhere. Default to `_member`.
- Use `google_service_account_iam_member` with
  `roles/iam.workloadIdentityUser` for GKE, `roles/iam.serviceAccountTokenCreator`
  for impersonation.
- Keep IAM in its own file per module so reviewers can diff grants.

## Review checklist

- [ ] No `roles/owner`, `roles/editor`, `roles/viewer` in the diff.
- [ ] No `google_service_account_key` resource, ever.
- [ ] Every SA has one purpose and lives in the workload project.
- [ ] Grants target groups or SAs, not `user:` principals.
- [ ] CI authenticates via WIF with a repository/branch condition.
- [ ] `serviceAccountUser` / `TokenCreator` granted on the SA, not the project.
- [ ] Data Access audit logs enabled for services holding sensitive data.
