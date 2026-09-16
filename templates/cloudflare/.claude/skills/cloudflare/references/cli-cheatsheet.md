# Cloudflare CLI cheatsheet

Every command runs under `secret-run`. Reads use `CLOUDFLARE_READ_TOKEN`; anything that changes state uses `CLOUDFLARE_API_TOKEN`. When a tool wants a different variable name, map it **inside** `bash -c '…'` (single quotes) so the expansion happens after decryption. `secret-run --only X -- env Y="$X" cmd` does not work: the outer shell expands `$X` to empty before `secret-run` runs.

## Raw API (curl)

Useful for anything the CLIs do not cover. Base URL `https://api.cloudflare.com/client/v4`.

```bash
# verify a token and see its status
secret-run --only CLOUDFLARE_READ_TOKEN -- bash -c \
  'curl -s -H "Authorization: Bearer $CLOUDFLARE_READ_TOKEN" https://api.cloudflare.com/client/v4/user/tokens/verify'

# list zones (id, name, status)
secret-run --only CLOUDFLARE_READ_TOKEN -- bash -c \
  'curl -s -H "Authorization: Bearer $CLOUDFLARE_READ_TOKEN" "https://api.cloudflare.com/client/v4/zones?per_page=50" | jq ".result[] | {id,name,status}"'

# DNS records for a zone
secret-run --only CLOUDFLARE_READ_TOKEN -- bash -c \
  'curl -s -H "Authorization: Bearer $CLOUDFLARE_READ_TOKEN" "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records" | jq ".result[] | {type,name,content,proxied}"'
```

Token verification endpoint: [create token](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/).

## flarectl

Reads `CF_API_TOKEN` (or the legacy `CF_API_KEY`/`CF_API_EMAIL`, which we do not use) ([flarectl README](https://github.com/cloudflare/cloudflare-go/blob/master/cmd/flarectl/README.md)).

```bash
# read-only
secret-run --only CLOUDFLARE_READ_TOKEN -- bash -c 'CF_API_TOKEN=$CLOUDFLARE_READ_TOKEN flarectl zone list'
secret-run --only CLOUDFLARE_READ_TOKEN -- bash -c 'CF_API_TOKEN=$CLOUDFLARE_READ_TOKEN flarectl zone info --zone example.com'
secret-run --only CLOUDFLARE_READ_TOKEN -- bash -c 'CF_API_TOKEN=$CLOUDFLARE_READ_TOKEN flarectl dns list --zone example.com'
secret-run --only CLOUDFLARE_READ_TOKEN -- bash -c 'CF_API_TOKEN=$CLOUDFLARE_READ_TOKEN flarectl firewall rules list --zone example.com'

# write (prefer Terraform; use only for a one-off that is then imported)
secret-run --only CLOUDFLARE_API_TOKEN -- bash -c \
  'CF_API_TOKEN=$CLOUDFLARE_API_TOKEN flarectl dns create --zone example.com --name app --type CNAME --content app.example.net --proxy'
```

`flarectl --help` lists the rest. Output is a table; add `--json` where supported for scripting.

## wrangler

Reads `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` from the environment; `wrangler login` (OAuth) is for laptops only, never CI ([system environment variables](https://developers.cloudflare.com/workers/wrangler/system-environment-variables/), [commands](https://developers.cloudflare.com/workers/wrangler/commands/)).

```bash
# identity
secret-run --only CLOUDFLARE_READ_TOKEN -- bash -c 'CLOUDFLARE_API_TOKEN=$CLOUDFLARE_READ_TOKEN wrangler whoami'

# Workers ( https://developers.cloudflare.com/workers/wrangler/commands/workers/ )
wrangler dev                                                  # local, no token needed
secret-run --only CLOUDFLARE_API_TOKEN -- wrangler deploy
secret-run --only CLOUDFLARE_API_TOKEN -- wrangler versions list
secret-run --only CLOUDFLARE_API_TOKEN -- wrangler rollback
secret-run --only CLOUDFLARE_API_TOKEN -- wrangler secret put API_KEY      # prompts for the value; never pass it on the CLI
secret-run --only CLOUDFLARE_API_TOKEN -- wrangler secret list
secret-run --only CLOUDFLARE_READ_TOKEN -- bash -c 'CLOUDFLARE_API_TOKEN=$CLOUDFLARE_READ_TOKEN wrangler tail <worker>'

# KV ( https://developers.cloudflare.com/workers/wrangler/commands/kv/ )
secret-run --only CLOUDFLARE_READ_TOKEN -- bash -c 'CLOUDFLARE_API_TOKEN=$CLOUDFLARE_READ_TOKEN wrangler kv namespace list'
secret-run --only CLOUDFLARE_READ_TOKEN -- bash -c 'CLOUDFLARE_API_TOKEN=$CLOUDFLARE_READ_TOKEN wrangler kv key list --namespace-id <id>'
secret-run --only CLOUDFLARE_API_TOKEN -- wrangler kv key put --namespace-id <id> <key> <value>

# R2 ( https://developers.cloudflare.com/workers/wrangler/commands/r2/ )
secret-run --only CLOUDFLARE_READ_TOKEN -- bash -c 'CLOUDFLARE_API_TOKEN=$CLOUDFLARE_READ_TOKEN wrangler r2 bucket list'
secret-run --only CLOUDFLARE_READ_TOKEN -- bash -c 'CLOUDFLARE_API_TOKEN=$CLOUDFLARE_READ_TOKEN wrangler r2 bucket info <bucket>'
secret-run --only CLOUDFLARE_API_TOKEN -- wrangler r2 object put <bucket>/<key> --file ./local.file
secret-run --only CLOUDFLARE_READ_TOKEN -- bash -c 'CLOUDFLARE_API_TOKEN=$CLOUDFLARE_READ_TOKEN wrangler r2 object get <bucket>/<key>'

# D1 ( https://developers.cloudflare.com/workers/wrangler/commands/d1/ )
secret-run --only CLOUDFLARE_READ_TOKEN -- bash -c 'CLOUDFLARE_API_TOKEN=$CLOUDFLARE_READ_TOKEN wrangler d1 list'
wrangler d1 execute <db> --local --command "select 1"          # local sqlite, no token
secret-run --only CLOUDFLARE_API_TOKEN -- wrangler d1 migrations apply <db> --remote

# Pages, existing projects only ( https://developers.cloudflare.com/workers/wrangler/commands/pages/ )
secret-run --only CLOUDFLARE_READ_TOKEN -- bash -c 'CLOUDFLARE_API_TOKEN=$CLOUDFLARE_READ_TOKEN wrangler pages project list'
secret-run --only CLOUDFLARE_API_TOKEN -- wrangler pages deploy ./dist --project-name <name>
```

Wrangler 3.60+ uses `kv namespace`, `kv key` (space), not the old `kv:namespace` colon form.

## cloudflared

Two ways to run a tunnel ([Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/), [get started](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/)):

**Remotely managed (default).** Terraform creates the tunnel and its ingress (see [terraform.md](terraform.md)); the host only needs the connector token.

```bash
secret-add TUNNEL_TOKEN                                     # from the dashboard or the tunnel resource's token attribute
secret-run --only TUNNEL_TOKEN -- bash -c 'cloudflared tunnel run --token $TUNNEL_TOKEN'
sudo cloudflared service install <TOKEN>                    # persistent; dashboard shows the exact line ( https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/ )
```

**Locally managed.** Config lives in `~/.cloudflared/config.yml` on the host ([create a local tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/create-local-tunnel/)).

```bash
cloudflared tunnel login                                    # browser; writes cert.pem
cloudflared tunnel create app                               # writes <UUID>.json credentials
cloudflared tunnel route dns app app.example.com            # CNAME to <UUID>.cfargotunnel.com
cloudflared tunnel run app
cloudflared tunnel list
cloudflared tunnel info app
```

Diagnostics:

```bash
cloudflared --version
cloudflared tunnel list --show-recently-disconnected
journalctl -u cloudflared -f                                # when installed as a service
```

Run at least two replicas of `cloudflared` per tunnel in production ([tunnel availability](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-availability/)).

## Terraform

```bash
secret-run --only CLOUDFLARE_API_TOKEN,R2_ACCESS_KEY_ID,R2_SECRET_ACCESS_KEY -- bash -c \
  'AWS_ACCESS_KEY_ID=$R2_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY=$R2_SECRET_ACCESS_KEY terraform init'
secret-run --only CLOUDFLARE_API_TOKEN,R2_ACCESS_KEY_ID,R2_SECRET_ACCESS_KEY -- bash -c \
  'AWS_ACCESS_KEY_ID=$R2_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY=$R2_SECRET_ACCESS_KEY terraform plan -out=plan.tfplan'
tflint --recursive && trivy config .
secret-run --only CLOUDFLARE_API_TOKEN,R2_ACCESS_KEY_ID,R2_SECRET_ACCESS_KEY -- bash -c \
  'AWS_ACCESS_KEY_ID=$R2_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY=$R2_SECRET_ACCESS_KEY terraform apply plan.tfplan'
```

A `plan` with the read token is a useful review trick: `CLOUDFLARE_API_TOKEN=$CLOUDFLARE_READ_TOKEN terraform plan` refreshes state and shows the diff without being able to apply it.

## Import from the dashboard

```bash
secret-run --only CLOUDFLARE_READ_TOKEN -- bash -c \
  'CLOUDFLARE_API_TOKEN=$CLOUDFLARE_READ_TOKEN cf-terraforming generate --resource-type cloudflare_dns_record --zone $ZONE_ID'
secret-run --only CLOUDFLARE_READ_TOKEN -- bash -c \
  'CLOUDFLARE_API_TOKEN=$CLOUDFLARE_READ_TOKEN cf-terraforming import --resource-type cloudflare_dns_record --zone $ZONE_ID'
```

`cf-terraforming` is not in the shell by default; see [import Cloudflare resources](https://developers.cloudflare.com/terraform/advanced-topics/import-cloudflare-resources/) for installation.

## Onboarding discovery

Use the automated `cloud-onboard-cloudflare` collector first; see
[scope, examples, permissions and coverage](onboarding.md). The commands below
are supplementary manual investigation procedures, not additional automation.

Use GET `/accounts/<account-id>/security-center/insights?page=1&per_page=100`
with the read token through the authenticated API pattern above. Check HTTP
status and `success` before interpreting results. Select only issue ID, type,
severity, status, and timestamp from `result.issues`; omit payload and subject.
Follow `result.page`, `result.per_page`, and `result.count` across pages, or record
partial coverage. Zone lists have their own `result_info` pagination. Do not
follow remediation links or fetch extended contexts automatically.

The token needs read permissions for the exact account/zone API; availability
also depends on the account's services. Denied/unavailable insights are unknown.
Review DNS/proxy/TLS and existing recommendations with selected read fields;
never retrieve Worker secret values or enable services. Use the shared
[report contract](../../cloud-onboarding/references/report-format.md).

Sources: [Insights API](https://developers.cloudflare.com/api/resources/security_center/subresources/insights/methods/list/),
[read permissions](https://developers.cloudflare.com/fundamentals/api/reference/permissions/).
