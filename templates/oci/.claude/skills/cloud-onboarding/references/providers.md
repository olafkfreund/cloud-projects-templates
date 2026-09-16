# Provider routing

Read only the selected provider's installed skill and its discovery procedure.
In a single-provider project, other provider skills may not be installed; add a
provider through the generator only if the user requests work on that provider.

| Provider | Implementation | Procedure in sibling skill | Coverage focus |
| --- | --- | --- | --- |
| AWS | Automated `cloud-onboard-aws` | `aws/references/cli-cheatsheet.md` | IAM root summary, EC2, RDS instances, general-purpose S3, CloudTrail |
| Azure | Manual | `azure/references/cli-cheatsheet.md` | Explicit subscriptions, Resource Graph, existing Advisor recommendations |
| GCP | Manual | `gcp/references/cli-cheatsheet.md` | Explicit project/organization, Cloud Asset Inventory via CLI |
| OCI | Manual | `oci/references/cli-cheatsheet.md` | Tenancy/compartments/regions, Search, existing Cloud Advisor |
| Kubernetes | Manual | `kubernetes/references/cli-cheatsheet.md` | Explicit context/namespaces, metadata and non-mutating misconfiguration checks |
| Cloudflare | Manual | `cloudflare/references/cli-cheatsheet.md` | Explicit account/zones, existing Security Insights |
| Hetzner | Manual | `hetzner/references/cli-cheatsheet.md` | Explicit project token, selected inventory metadata |
| DigitalOcean | Manual | `digitalocean/references/cli-cheatsheet.md` | Explicit account/project, resource inventory limited by token scopes |

Manual procedures produce a report using [the contract](report-format.md), not a
claim that an executable collector exists. Record the exact commands, versions,
observation time, pagination, and permission gaps. Native recommendations require
human interpretation; service unavailability never authorizes activation.

Do not assume listed projects equal all projects the user intended. Compare
expected scope with observed scope; Resource Graph and token-scoped APIs can
silently omit inaccessible resources. Establish scope with the user, not by
guessing from whichever CLI login is currently active.
