# OCI IAM: policies, principals and the read-only agent profile

Verified 2026-09-15 against [Policy syntax](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policysyntax.htm) and [Policy reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/policyreference.htm).

## Syntax

```
Allow <subject> to <verb> <resource-type> in <location> [where <conditions>]
```

- **subject**: `group <name>`, `dynamic-group <name>`, `any-group`, `any-user` (only with a `where` clause), `service <name>`.
- **location**: `in tenancy` or `in compartment <name>` / `in compartment <parent>:<child>`. Prefer compartments.
- **conditions**: `where request.user.mfaTotpVerified='true'`, `where target.compartment.id != '<ocid>'`, `where all {...}` / `where any {...}`; string values in single quotes, patterns as `/prefix*/`.

## Verbs: inspect vs read vs use vs manage

Cumulative, from the [Policy reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/policyreference.htm):

| Verb | Oracle's target user | Grants |
|------|---------------------|--------|
| `inspect` | Third-party auditors | List resources **without** user-specified metadata or confidential contents (exceptions: policy statements and networking resources are returned in full) |
| `read` | Internal auditors | `inspect` + get the resource itself and its metadata (tags, display names, configuration) |
| `use` | Day-to-day users | `read` + update existing resources, except updates that equal create (e.g. `UpdatePolicy`, `UpdateSecurityList` need `manage`); no create/delete |
| `manage` | Administrators | Everything |

Why agents get `read`, not `inspect`: `inspect` hides tags and most attributes, so an agent cannot answer "what is this instance's shape and owner". `read` returns full resource bodies but still cannot mutate. Note that `read` on `all-resources` exposes configuration (e.g. security rules, bucket names) and, for some services, metadata that may be sensitive; restrict the compartment if that matters.

Resource families worth knowing: `all-resources`, `virtual-network-family`, `instance-family`, `volume-family`, `object-family`, `database-family`, `cluster-family` (OKE), `file-family`, `dns`. IAM has no family; name `users`, `groups`, `policies`, `compartments` individually.

## Read-only agent policy (required)

Create a group `ro-agents`, put the agent user in it, and attach this policy at the root compartment:

```
Allow group ro-agents to read all-resources in tenancy
```

Narrower variants (prefer when possible):

```
Allow group ro-agents to read all-resources in compartment prod
Allow group ro-agents to inspect compartments in tenancy
Allow group ro-agents to read audit-events in tenancy
Allow group ro-agents to read usage-reports in tenancy
```

Explicitly do **not** add `use` or `manage`. Do not put the agent user in `Administrators`. Because OCI policies are allow-only, the absence of `use`/`manage` is the deny.

Create it with the CLI (as an admin, once):

```
oci iam group create --name ro-agents --description "Read-only AI agent sessions"
oci iam user create --name agent-bot --description "AI agent read-only principal" --email agent@example.com
oci iam group add-user --group-id <group-ocid> --user-id <user-ocid>
oci iam policy create --compartment-id <tenancy-ocid> --name ro-agents-read \
  --description "AI agents: read all resources, no mutations" \
  --statements '["Allow group ro-agents to read all-resources in tenancy"]'
```

Reference: [Common policies](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/commonpolicies.htm), [Policy syntax](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policysyntax.htm).

## Dedicated CLI profile for agent sessions

Agents must not use the human `DEFAULT` profile. Give them their own profile named `ro-agent`, authenticated with a security token, so the credential is short-lived and bound to `ro-agents`.

1. Sign in as the agent user (federated or local) and create a token-backed profile:

```
oci session authenticate --profile-name ro-agent --region <region> --no-browser
```

This writes a `[ro-agent]` section to `~/.oci/config` with `security_token_file=...` and a generated key pair; nothing is printed. Tokens last 1 hour and can be refreshed up to 24 h with `oci session refresh --profile ro-agent`. [Token-based auth](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/clitoken.htm)

2. Start every agent session with:

```
export OCI_CLI_PROFILE=ro-agent
export OCI_CLI_AUTH=security_token
oci session validate --profile ro-agent --auth security_token
```

`OCI_CLI_PROFILE` is also what the MCP server reads (as `OCI_CONFIG_PROFILE`; see [mcp.md](mcp.md)). Profile precedence is `--profile` > `OCI_CLI_PROFILE` > `default_profile` in `~/.oci/oci_cli_rc`. [CLI configuration](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliconfigure.htm)

3. If a long-lived key is unavoidable (headless CI without OCI-hosted runners), store the PEM with agenix and inject it: `secret-add oci-agent-key`, then `secret-run --only oci-agent-key -- oci ...` with `key_file` pointing at the injected path. Never commit `~/.oci/config` or PEM files. Limit: 3 API keys per user; rotate by add-new, switch, delete-old. [Managing credentials](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingcredentials.htm)

4. Verify the boundary before trusting it:

```
oci iam compartment list --profile ro-agent --auth security_token >/dev/null && echo read-ok
oci iam tag-namespace create --profile ro-agent --auth security_token \
  --compartment-id <ocid> --name should-fail --description x 2>&1 | grep -q NotAuthorized && echo write-blocked
```

## Human and workload principals

| Principal | When | How |
|-----------|------|-----|
| Security token (human) | Laptops, interactive `terraform apply` under 1 h | `oci session authenticate --profile-name <env>`; provider `auth = "SecurityToken"` |
| Instance principal | Compute-hosted CI runners, bastion automation | Dynamic group rule `instance.compartment.id = '<ocid>'`; `OCI_CLI_AUTH=instance_principal`; provider `auth = "InstancePrincipal"`. All instance principals implicitly get `compartment_inspect`; anyone with SSH on the instance inherits its rights. [Instance principals](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/callingservicesfrominstances.htm) |
| Resource principal | Functions, Data Science, other managed services | Dynamic group `ALL {resource.type = 'fnfunc', resource.compartment.id = '<ocid>'}`; RPST cached 15 min. [Functions resource principals](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsaccessingociresources.htm) |
| OKE workload identity | Pods on enhanced clusters | `Allow any-user to <verb> <res> in compartment X where all {request.principal.type='workload', request.principal.namespace='ns', request.principal.service_account='sa', request.principal.cluster_id='<ocid>'}`. [Workload identity](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contenggrantingworkloadaccesstoresources.htm) |
| API key | Last resort | agenix-managed PEM, rotated, max 3 per user |

## Policy patterns

```
# Compartment admin, MFA required
Allow group prod-app-admins to manage all-resources in compartment prod:appdev where request.user.mfaTotpVerified='true'

# Operators: run but not reshape
Allow group prod-app-ops to use instance-family in compartment prod:appdev
Allow group prod-app-ops to read virtual-network-family in compartment prod:network

# App team consumes shared network without owning it
Allow group prod-app-admins to use virtual-network-family in compartment prod:network

# CI runner (instance principal) deploys one compartment and reads state bucket
Allow dynamic-group prod-ci-runners to manage all-resources in compartment prod:appdev
Allow dynamic-group prod-ci-runners to manage objects in compartment prod:security where target.bucket.name='tfstate-prod'

# Object Storage uses a Vault key
Allow service objectstorage-<region> to use keys in compartment prod:security

# Budgets and cost visibility
Allow group finops to read usage-reports in tenancy
Allow group finops to manage usage-budgets in tenancy
```

Sources: [Common policies](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/commonpolicies.htm), [Budgets](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm), [MFA](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/usingmfa.htm).

## Review checklist for any policy change

- [ ] Lowest verb that satisfies the use case; `manage all-resources` only for compartment admins
- [ ] `in compartment`, not `in tenancy`, unless the resource type is tenancy-level
- [ ] `any-user` / `any-group` always paired with a `where` clause
- [ ] Privileged statements carry `request.user.mfaTotpVerified='true'`
- [ ] Dynamic group rules match by compartment or tag, not by wildcard
- [ ] `ro-agents` stays at `read`; a PR that adds `use`/`manage` to it needs explicit sign-off (see [mcp.md](mcp.md))
- [ ] Policy is deployed via Terraform (`oci_identity_policy`) with `defined_tags`, not the console
