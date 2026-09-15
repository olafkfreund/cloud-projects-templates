# doctl cheatsheet

`doctl` is the official CLI ([doctl](https://github.com/digitalocean/doctl), [reference](https://docs.digitalocean.com/reference/doctl/reference/)). It reads `DIGITALOCEAN_ACCESS_TOKEN` (only when the `default` context is active) or `--access-token`. Every command below runs through `secret-run` so the token exists only in the child process.

## Auth

```bash
# Read-only work (agents, inspection): map the read token to the name doctl expects, inside the command
secret-run --only DIGITALOCEAN_READ_TOKEN -- bash -c 'DIGITALOCEAN_ACCESS_TOKEN=$DIGITALOCEAN_READ_TOKEN doctl account get'

# Deploy work: the deploy token already has the right name
secret-run --only DIGITALOCEAN_ACCESS_TOKEN -- doctl account get
secret-run --only DIGITALOCEAN_ACCESS_TOKEN -- doctl account ratelimit     # API quota left

# Do NOT do this: the outer shell expands $DIGITALOCEAN_READ_TOKEN before secret-run decrypts it (empty value)
# secret-run --only DIGITALOCEAN_READ_TOKEN -- env DIGITALOCEAN_ACCESS_TOKEN="$DIGITALOCEAN_READ_TOKEN" doctl account get
```

`doctl auth init` writes the token to a config file on disk; do not use it in this project. Contexts (`doctl auth list|switch|remove`) are for personal machines only ([doctl auth](https://docs.digitalocean.com/reference/doctl/reference/auth/)). `doctl account get` is the "who am I" check: confirm the team email before any write.

Define a helper once per shell to keep the lines short:

```bash
doro() { secret-run --only DIGITALOCEAN_READ_TOKEN -- bash -c 'DIGITALOCEAN_ACCESS_TOKEN=$DIGITALOCEAN_READ_TOKEN doctl "$@"' _ "$@"; }
dorw() { secret-run --only DIGITALOCEAN_ACCESS_TOKEN -- doctl "$@"; }
```

## Output

```bash
doro compute droplet list --format ID,Name,Region,PublicIPv4,Tags --no-header
doro compute droplet list -o json | jq '.[] | {name, vpc_uuid, tags}'
```

`--format` takes column names from the table header; `-o json` is easier for agents.

## Read and inspect

```bash
doro projects list
doro projects resources list <project-id>
doro compute region list
doro compute size list                                  # slugs for Droplets
doro compute image list-distribution --public

doro vpcs list
doro vpcs get <vpc-id>
doro vpcs peerings list

doro compute firewall list
doro compute firewall list-by-droplet <droplet-id>      # effective rules for one Droplet
doro compute load-balancer list
doro compute ssh-key list
doro compute tag list

doro compute droplet get <id>
doro compute droplet-action list <id>                   # power/resize history
doro compute snapshot list
doro compute volume list

doro kubernetes cluster list
doro kubernetes cluster get <name>
doro kubernetes cluster node-pool list <name>
doro kubernetes options versions                        # upgradeable versions

doro apps list
doro apps get <app-id>
doro apps spec get <app-id>                             # current app spec
doro apps list-deployments <app-id>
doro apps logs <app-id> --type run --tail 100

doro databases list
doro databases get <db-id>
doro databases firewalls list <db-id>                   # trusted sources
doro databases user list <db-id>

doro registry get
doro registry repository list-v2
doro monitoring alert list
doro monitoring uptime list
```

References: [compute](https://docs.digitalocean.com/reference/doctl/reference/compute/), [vpcs](https://docs.digitalocean.com/reference/doctl/reference/vpcs/), [kubernetes](https://docs.digitalocean.com/reference/doctl/reference/kubernetes/), [apps](https://docs.digitalocean.com/reference/doctl/reference/apps/), [databases](https://docs.digitalocean.com/reference/doctl/reference/databases/), [registry](https://docs.digitalocean.com/reference/doctl/reference/registry/), [monitoring](https://docs.digitalocean.com/reference/doctl/reference/monitoring/).

## Writes (deploy token; prefer Terraform)

Use these for one-off operations and incident response. Anything that should persist goes into Terraform.

```bash
# Droplet with SSH key, VPC, tags, monitoring and backups
dorw compute droplet create web-1 --region fra1 --size s-2vcpu-4gb --image ubuntu-24-04-x64 \
  --vpc-uuid <vpc-id> --ssh-keys <fingerprint> --tag-names prod-web,prod \
  --enable-monitoring --enable-backups --wait

# Firewall applied by tag: SSH from the office range, HTTP(S) from the load balancer
dorw compute firewall create --name prod-web --tag-names prod-web \
  --inbound-rules "protocol:tcp,ports:22,address:203.0.113.0/24 protocol:tcp,ports:443,load_balancer_uid:<lb-id>" \
  --outbound-rules "protocol:tcp,ports:all,address:0.0.0.0/0,address:::/0"

# Database trusted source by tag
dorw databases firewalls append <db-id> --rule tag:prod-app

# Snapshot before a risky change
dorw compute droplet-action snapshot <id> --snapshot-name "pre-upgrade-$(date +%F)" --wait

# DOKS: kubeconfig (revocable OAuth token on current versions), then kubectl
dorw kubernetes cluster kubeconfig save <name>
dorw kubernetes cluster upgrade <name> --version <ver>

# Container registry
dorw registry login                                   # docker login for the team registry
dorw registry kubernetes-manifest | kubectl apply -f -   # pull secret for a non-integrated cluster
dorw registry garbage-collection start

# App Platform
dorw apps create --spec app.yaml
dorw apps create-deployment <app-id>
```

Flag references: [droplet create](https://docs.digitalocean.com/reference/doctl/reference/compute/droplet/create/), [firewall create](https://docs.digitalocean.com/reference/doctl/reference/compute/firewall/create/), [secure a database](https://docs.digitalocean.com/products/databases/postgresql/how-to/secure/), [connect to DOKS](https://docs.digitalocean.com/products/kubernetes/how-to/connect-to-cluster/), [registry with Docker and Kubernetes](https://docs.digitalocean.com/products/container-registry/how-to/use-registry-docker-kubernetes/). Newer doctl also exposes `doctl registries …` for multiple registries; the same subcommands apply.

## Terraform through secret-run

```bash
secret-run --only DIGITALOCEAN_ACCESS_TOKEN,AWS_ACCESS_KEY_ID,AWS_SECRET_ACCESS_KEY -- terraform init
secret-run --only DIGITALOCEAN_ACCESS_TOKEN,AWS_ACCESS_KEY_ID,AWS_SECRET_ACCESS_KEY -- terraform plan -out=plan.tfplan
secret-run --only DIGITALOCEAN_ACCESS_TOKEN,AWS_ACCESS_KEY_ID,AWS_SECRET_ACCESS_KEY -- terraform apply plan.tfplan
```

`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` are the Spaces key pair the S3 backend reads ([Spaces backend](https://docs.digitalocean.com/products/spaces/reference/terraform-backend/)). `plan` with the read token works for roots that only read (data sources) but fails on refresh of resources needing write scopes, so use the deploy token for plan and apply.

## Troubleshooting

- **`401 Unable to authenticate you`**: token missing, expired or mapped with `env` on the outer shell (see Auth). Check `secret-list` and the token's expiry on the Tokens page.
- **`403 … does not have access`**: Custom Scopes token lacks the scope for that resource; add `<resource>:<action>` from the [scopes list](https://docs.digitalocean.com/reference/api/scopes/).
- **`--access-token` ignored**: a non-default `doctl auth` context is active; run `doctl auth switch --context default` or remove the context.
- **`429 Too Many Requests`**: `doro account ratelimit` shows the reset time; agents polling lists should slow down.
- **Command works with doctl but Terraform says forbidden**: Terraform read `DIGITALOCEAN_TOKEN` first; make sure only one of the two variables is set.
