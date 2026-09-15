# oci CLI cheatsheet

Verified 2026-09-15. Docs: [CLI configuration](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliconfigure.htm), [Config file](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm), [Token auth](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/clitoken.htm), [Command reference](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/).

## Config and profiles

- Config: `~/.oci/config` (INI, `[DEFAULT]` plus named profiles; profiles inherit from DEFAULT). Override with `OCI_CLI_CONFIG_FILE`.
- CLI defaults: `~/.oci/oci_cli_rc` (`oci setup oci-cli-rc`), override with `OCI_CLI_RC_FILE`.
- Profile precedence: `--profile` > `OCI_CLI_PROFILE` > `default_profile` in `[OCI_CLI_SETTINGS]`.
- Keys: `user`, `tenancy`, `region`, `fingerprint`, `key_file`, optional `pass_phrase` (avoid storing), `security_token_file` (token profiles).

```ini
[DEFAULT]
tenancy=ocid1.tenancy.oc1..aaaa
region=eu-frankfurt-1
[ro-agent]                       ; created by `oci session authenticate`
user=ocid1.user.oc1..bbbb
fingerprint=aa:bb:...
key_file=~/.oci/sessions/ro-agent/oci_api_key.pem
security_token_file=~/.oci/sessions/ro-agent/token
region=eu-frankfurt-1
```

## Authenticate

```
oci session authenticate --profile-name dev --region eu-frankfurt-1        # browser
oci session authenticate --profile-name ro-agent --region eu-frankfurt-1 --no-browser
oci session validate --profile dev --auth security_token
oci session refresh  --profile dev                                         # extend, up to 24 h
export OCI_CLI_PROFILE=dev OCI_CLI_AUTH=security_token                     # every shell
oci os ns get --auth instance_principal                                    # on an OCI instance
```

Never run `oci setup config` on a shared or agent machine unless a PEM is unavoidable; if it is, keep it in agenix: `secret-add oci-key` then `secret-run --only oci-key -- oci ...`.

## Useful global options

| Option | Effect |
|--------|--------|
| `--profile NAME` | Pick config profile |
| `--auth security_token|instance_principal|resource_principal` | Auth mode |
| `--region` | Override region |
| `--output table|json` | Human vs machine output |
| `--query '<JMESPath>'` | Filter/shape JSON; named queries via `query://name` from `[OCI_CLI_CANNED_QUERIES]` |
| `--all` | Follow pagination |
| `--dry-run` (where supported) | Show request without sending |
| `--generate-full-command-json-input` | Emit an input skeleton for complex creates |

Shorthands: `-c` = `--compartment-id`, `-ns` = `--namespace-name`, `-bn` = `--bucket-name`.

## Discover the tenancy (read-only)

```
T=$(oci iam tenancy get --tenancy-id "$(oci iam compartment list --query 'data[0]."compartment-id"' --raw-output)" --query data.id --raw-output)
oci iam region-subscription list --output table
oci iam compartment list -c "$T" --compartment-id-in-subtree true --all \
  --query 'data[?"lifecycle-state"==`ACTIVE`].{name:name,id:id,parent:"compartment-id"}' --output table
oci iam group list --all --query 'data[].{name:name,id:id}' --output table
oci iam policy list -c "$T" --all --query 'data[].{name:name,statements:statements}'
oci iam dynamic-group list --all --query 'data[].{name:name,rule:"matching-rule"}'
oci iam tag-namespace list -c "$T" --all --output table
oci limits resource-availability get --service-name compute --limit-name standard-e4-core-count -c "$T"
```

## Network

```
C=<compartment-ocid>
oci network vcn list -c $C --query 'data[].{name:"display-name",cidr:"cidr-blocks",id:id}' --output table
oci network subnet list -c $C --vcn-id <vcn> --query 'data[].{name:"display-name",cidr:"cidr-block",public:!"prohibit-public-ip-on-vnic"}' --output table
oci network nsg list -c $C --output table
oci network nsg rules list --nsg-id <nsg> --query 'data[?direction==`INGRESS`].{src:source,proto:protocol,tcp:"tcp-options"}'
oci network security-list list -c $C --query 'data[].{name:"display-name",ingress:"ingress-security-rules"[?source==`0.0.0.0/0`]}'
oci network drg list -c $C --output table
oci network drg-attachment list -c $C --drg-id <drg> --output table
oci network drg-route-table list --drg-id <drg> --output table
```

## Compute, OKE, database, storage

```
oci compute instance list -c $C --all --query 'data[?"lifecycle-state"==`RUNNING`].{name:"display-name",shape:shape,ad:"availability-domain",fd:"fault-domain",tags:"defined-tags"}' --output table
oci compute instance list-vnics --instance-id <id> --query 'data[].{priv:"private-ip",pub:"public-ip"}'
oci ce cluster list -c $C --query 'data[].{name:name,ver:"kubernetes-version",type:type,endpoint:"endpoint-config"}'
oci ce cluster create-kubeconfig --cluster-id <id> --file ~/.kube/oci-<name> --token-version 2.0.0 --kube-endpoint PRIVATE_ENDPOINT
oci ce node-pool list -c $C --cluster-id <id> --output table
oci db autonomous-database list -c $C --query 'data[].{name:"display-name",state:"lifecycle-state",private:"private-endpoint",mtls:"is-mtls-connection-required"}' --output table
oci os ns get
oci os bucket list -c $C --query 'data[].{name:name,public:"public-access-type",versioning:versioning}' --output table
oci os object list -bn <bucket> --all --query 'data[].{name:name,size:size}'
```

## Security posture and cost

```
oci cloud-guard configuration get -c "$T"
oci cloud-guard problem list -c "$T" --compartment-id-in-subtree true --risk-level CRITICAL --lifecycle-state ACTIVE --all --query 'data.items[].{name:"resource-name",type:"detector-rule-id"}'
oci cloud-guard security-zone list -c "$T" --all --output table
oci kms management vault list -c $C --output table
oci audit event list -c $C --start-time 2026-09-14T00:00:00Z --end-time 2026-09-15T00:00:00Z --query 'data[].{t:"event-time",n:"event-name",p:data."identity"."principal-name"}'
oci logging log-group list -c $C --all --output table
oci budgets budget list -c "$T" --all --query 'data[].{name:"display-name",amount:amount,spent:"actual-spend",forecast:"forecasted-spend"}' --output table
oci usage-api usage-summary request-summarized-usages --tenant-id "$T" --time-usage-started 2026-09-01T00:00:00Z --time-usage-ended 2026-09-15T00:00:00Z --granularity DAILY --group-by '["service"]'
oci optimizer recommendation list -c "$T" --compartment-id-in-subtree true --category-id <cost-category-ocid>
```

## Tagging

```
oci iam tag-namespace create -c "$T" --name Ops --description "Governed operational tags"
oci iam tag create --tag-namespace-id <ns> --name Env --description "dev|staging|prod" \
  --validator '{"validatorType":"ENUM","values":["dev","staging","prod"]}'
oci iam tag-default create -c $C --tag-definition-id <tag> --value dev --is-required true
oci search resource structured-search --query-text "query all resources where definedTags.namespace = 'Ops' && definedTags.key = 'Owner' && definedTags.value = 'platform'"
oci search resource structured-search --query-text "query all resources where (definedTags.namespace != 'Ops')"   # find untagged
```

## Habits

- Default to `--query` + `--output table`; pipe JSON only to `jq` when you need it.
- Export `OCI_CLI_PROFILE` per environment shell; never rely on `DEFAULT` for prod.
- Agent sessions: `OCI_CLI_PROFILE=ro-agent`. Anything that returns `NotAuthorizedOrNotFound` is the boundary working, not a bug.
- Mutating commands (`create`, `update`, `delete`, `launch`, `terminate`) belong in Terraform, not in shell history; the exception is `oci session *` and one-off `oci iam` bootstrap steps documented in [iam.md](iam.md).
- Always pass `-c` explicitly; many list commands silently default to the root compartment.
