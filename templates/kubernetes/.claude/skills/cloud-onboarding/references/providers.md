# Provider routing

Read only the selected provider's installed skill and its discovery procedure.
In a single-provider project, other provider skills may not be installed; add a
provider through the generator only if the user requests work on that provider.

| Provider | Implementation | Procedure in sibling skill | Coverage focus |
| --- | --- | --- | --- |
| AWS | Automated `cloud-onboard-aws` | `aws/references/cli-cheatsheet.md` | IAM root summary, EC2, RDS instances, general-purpose S3, CloudTrail |
| Azure | Automated | `azure/references/cli-cheatsheet.md` | Explicit subscriptions, Resource Graph, existing Advisor recommendations |
| GCP | Automated | `gcp/references/cli-cheatsheet.md` | Explicit project/organization, Cloud Asset Inventory via CLI |
| OCI | Automated | `oci/references/cli-cheatsheet.md` | Tenancy/compartments/regions, Search, existing Cloud Advisor |
| Kubernetes | Automated | `kubernetes/references/cli-cheatsheet.md` | Explicit context/namespaces, metadata and non-mutating misconfiguration checks |
| Cloudflare | Automated | `cloudflare/references/cli-cheatsheet.md` | Explicit account/zones, existing Security Insights |
| Hetzner | Automated | `hetzner/references/cli-cheatsheet.md` | Explicit project token, selected inventory metadata |
| DigitalOcean | Automated | `digitalocean/references/cli-cheatsheet.md` | Explicit account/project, resource inventory limited by token scopes |

Supplementary manual procedures produce a report using [the contract](report-format.md), alongside the executable baseline. Record the exact commands, versions,
observation time, pagination, and permission gaps. Native recommendations require
human interpretation; service unavailability never authorizes activation.

Do not assume listed projects equal all projects the user intended. Compare
expected scope with observed scope; Resource Graph and token-scoped APIs can
silently omit inaccessible resources. Establish scope with the user, not by
guessing from whichever CLI login is currently active.

Each non-AWS provider has `cloud-onboard-<provider>` and a linked
`<provider>/references/onboarding.md` with its required identity and scope.
See [commands](commands.md) for shell, just, flake and adoption examples.
