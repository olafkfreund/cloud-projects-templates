# gcloud cheatsheet

Verified 2026-09-15. Reference: [gcloud CLI](https://docs.cloud.google.com/sdk/gcloud/reference),
[Scripting gcloud](https://docs.cloud.google.com/sdk/docs/scripting-gcloud).

The devenv shell ships `gcloud` with `gke-gcloud-auth-plugin`. Extra
components are declared in `devenv.nix`
(`google-cloud-sdk.withExtraComponents [ ... ]`), not installed at runtime
([Components](https://docs.cloud.google.com/sdk/docs/components)).

## Identity and context

[Authorizing](https://docs.cloud.google.com/sdk/docs/authorizing),
[Configurations](https://docs.cloud.google.com/sdk/docs/configurations)

```sh
gcloud auth login                                   # CLI credentials
gcloud auth application-default login               # ADC for terraform and SDKs
gcloud auth list                                    # who am I
gcloud config list                                  # project, region, impersonation
gcloud config configurations create dev             # one named config per env
gcloud config configurations activate dev
gcloud config set project PROJECT_ID
gcloud config set compute/region europe-west1
gcloud config set auth/impersonate_service_account SA@PROJECT.iam.gserviceaccount.com
gcloud auth print-access-token --impersonate-service-account=SA@...   # never paste this into a file
```

Always check `gcloud config list` before a mutating command. `--project`
on the command line beats the active config; use it in scripts.

## Output: filters and formats

[Filters](https://docs.cloud.google.com/sdk/gcloud/reference/topic/filters),
[Formats](https://docs.cloud.google.com/sdk/gcloud/reference/topic/formats)

```sh
gcloud compute instances list --filter='labels.env=prod AND status=RUNNING' \
  --format='table(name,zone.basename(),machineType.basename(),networkInterfaces[0].networkIP)'
gcloud projects list --format='value(projectId)'          # one per line, for loops
gcloud run services list --format=json | jq '.[].metadata.name'
gcloud storage buckets list --format='yaml(name,location,iamConfiguration)'
```

`--format=value(...)` for scripts, `table(...)` for humans, `json` for jq.

## Projects, folders, org policy

```sh
gcloud projects describe PROJECT_ID
gcloud projects create prj-d-team-app --folder=FOLDER_ID --labels=env=dev,owner=team   # see projects/create
gcloud services enable compute.googleapis.com run.googleapis.com --project=PROJECT_ID
gcloud resource-manager org-policies list --project=PROJECT_ID
gcloud resource-manager folders list --organization=ORG_ID
```

[projects create](https://docs.cloud.google.com/sdk/gcloud/reference/projects/create),
[services enable](https://docs.cloud.google.com/sdk/gcloud/reference/services/enable),
[org-policies list](https://docs.cloud.google.com/sdk/gcloud/reference/resource-manager/org-policies/list)

## IAM

```sh
gcloud projects get-iam-policy PROJECT_ID --format=yaml
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member=group:team@example.com --role=roles/run.developer --condition=None
gcloud iam service-accounts list --project=PROJECT_ID
gcloud iam service-accounts create sa-app-dev --display-name='app dev runtime'
gcloud iam service-accounts add-iam-policy-binding SA@... \
  --member=user:me@example.com --role=roles/iam.serviceAccountTokenCreator
gcloud asset search-all-iam-policies --scope=projects/PROJECT_ID --query='policy:roles/owner'
```

Prefer IaC for bindings; use the CLI to inspect, or for break-glass with a
ticket. Never `gcloud iam service-accounts keys create`.
[get-iam-policy](https://docs.cloud.google.com/sdk/gcloud/reference/projects/get-iam-policy),
[add-iam-policy-binding](https://docs.cloud.google.com/sdk/gcloud/reference/projects/add-iam-policy-binding),
[search-all-iam-policies](https://docs.cloud.google.com/sdk/gcloud/reference/asset/search-all-iam-policies)

## Compute

```sh
gcloud compute instances list --format='table(name,zone,status,labels)'
gcloud compute instances describe VM --zone=ZONE
gcloud compute ssh VM --zone=ZONE --tunnel-through-iap     # no external IP needed
gcloud compute instances create VM --zone=ZONE --machine-type=e2-small \
  --no-address --shielded-secure-boot --labels=env=dev,owner=team \
  --service-account=SA@... --scopes=cloud-platform
```

[instances list](https://docs.cloud.google.com/sdk/gcloud/reference/compute/instances/list),
[Create instance](https://docs.cloud.google.com/compute/docs/instances/create-start-instance)

## GKE

[Cluster access for kubectl](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl)

```sh
gcloud container clusters list
gcloud container clusters get-credentials CLUSTER --region=REGION --project=PROJECT_ID
kubectl get nodes          # uses gke-gcloud-auth-plugin from the shell
```

`get-credentials` writes kubeconfig using the auth plugin; if `kubectl`
reports a missing plugin, the shell's SDK is not the one on `PATH`.
[get-credentials](https://docs.cloud.google.com/sdk/gcloud/reference/container/clusters/get-credentials)

## Cloud Run

```sh
gcloud run services list --region=REGION
gcloud run deploy SERVICE --image=REGION-docker.pkg.dev/PROJECT/REPO/IMG:TAG \
  --region=REGION --service-account=SA@... --ingress=internal --no-allow-unauthenticated \
  --labels=env=dev,owner=team
gcloud run services update-traffic SERVICE --to-revisions=REV=10   # canary
```

[run deploy](https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy),
[Managing access](https://docs.cloud.google.com/run/docs/securing/managing-access)

## Storage

```sh
gcloud storage buckets list
gcloud storage buckets create gs://BUCKET --location=REGION \
  --uniform-bucket-level-access --public-access-prevention --default-storage-class=STANDARD
gcloud storage buckets update gs://BUCKET --versioning
gcloud storage ls gs://BUCKET
```

[buckets create](https://docs.cloud.google.com/sdk/gcloud/reference/storage/buckets/create)

## Logging and monitoring

[logging read](https://docs.cloud.google.com/sdk/gcloud/reference/logging/read)

```sh
gcloud logging read 'resource.type="cloud_run_revision" AND severity>=ERROR' \
  --project=PROJECT_ID --limit=50 --freshness=1h --format='value(timestamp,textPayload)'
gcloud logging read 'protoPayload.methodName:"SetIamPolicy"' --limit=20
gcloud logging sinks list
gcloud monitoring uptime list-configs 2>/dev/null || true
```

## Cost

```sh
gcloud billing projects describe PROJECT_ID
gcloud billing budgets list --billing-account=ACCOUNT_ID
gcloud recommender recommendations list --project=PROJECT_ID \
  --location=ZONE --recommender=google.compute.instance.MachineTypeRecommender
```

[budgets list](https://docs.cloud.google.com/sdk/gcloud/reference/billing/budgets/list),
[Recommender](https://docs.cloud.google.com/recommender/docs/overview)

## Secrets

Runtime secrets: Secret Manager, referenced by name from Cloud Run / GKE
([Best practices](https://docs.cloud.google.com/secret-manager/docs/best-practices)).
Local secrets: agenix.

```sh
secret-add GCP_BILLING_ACCOUNT                      # store, never echo
secret-run --only GCP_BILLING_ACCOUNT -- \
  sh -c 'gcloud billing budgets list --billing-account="$GCP_BILLING_ACCOUNT"'
```

Do not `gcloud secrets versions access` into a shell variable that then
gets echoed or written to a file.

## Habits

- `--quiet` only in CI; interactively, read the prompt.
- `--dry-run` where offered; otherwise `list`/`describe` before `delete`.
- Pin `--project`, `--region`/`--zone` explicitly in scripts.
- `gcloud topic startup` and `CLOUDSDK_CORE_DISABLE_PROMPTS=1` for
  non-interactive runs ([startup](https://docs.cloud.google.com/sdk/gcloud/reference/topic/startup)).

## Onboarding discovery

Use the automated `cloud-onboard-gcp` collector first; see
[scope, examples, permissions and coverage](onboarding.md). The commands below
are supplementary manual investigation procedures, not additional automation.

```sh
gcloud projects describe "$PROJECT_ID" --format='json(projectId,projectNumber)'
gcloud asset search-all-resources --scope="projects/$PROJECT_ID" --project="$PROJECT_ID" \
  --read-mask=name,assetType,location --format='json(name,assetType,location)' --page-size=100
```

Use the CLI: the project's GCP MCP allowlist does not expose asset discovery.
`cloudasset.assets.searchAllResources` is required on the intended scope. The CLI
follows pages; adding `--limit` bounds the results and must be recorded as possible
truncation. Only supported searchable asset types appear. A disabled Cloud Asset
API or denied scope is unknown; do not enable APIs or widen roles automatically.
Review existing Recommender/Security Command Center findings only when accessible;
not every activation has the same detectors. Select evidence fields and use the
shared [report contract](../../cloud-onboarding/references/report-format.md).

Sources: [asset search](https://docs.cloud.google.com/sdk/gcloud/reference/asset/search-all-resources),
[asset coverage](https://docs.cloud.google.com/asset-inventory/docs/asset-inventory-overview),
[Security Health Analytics availability](https://docs.cloud.google.com/security-command-center/docs/concepts-security-health-analytics).
