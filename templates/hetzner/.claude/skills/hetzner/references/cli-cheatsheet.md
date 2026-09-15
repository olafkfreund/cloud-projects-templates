# hcloud CLI cheatsheet

`hcloud` is the official CLI ([github.com/hetznercloud/cli](https://github.com/hetznercloud/cli)). It reads `HCLOUD_TOKEN` from the environment, so no config file or context is needed ([configuration reference](https://github.com/hetznercloud/cli/blob/main/docs/reference/configuration.md)). Every command below is run as `secret-run --only HCLOUD_TOKEN -- hcloud ...`; the prefix is omitted for brevity. The token selects the project.

Do not run `hcloud context create`: it stores the token in `~/.config/hcloud/cli.toml`. Contexts are for personal laptops with a single Read token, never for shared or CI machines.

## Identity and sanity

```bash
hcloud server list                         # which project am I in? (token = project)
hcloud location list                       # fsn1 nbg1 hel1 ash hil sin, with network zones
hcloud server-type list                    # cx/cpx/cax/ccx names, cores, memory, disk
hcloud image list --type system            # OS images; --type snapshot for your own
hcloud version
```

## Output for scripts and agents

`--output` (`-o`) accepts `json`, `yaml`, `noheader` and `columns=...`; `describe` also takes `format='{{ .Field }}'` Go templates ([using output options](https://github.com/hetznercloud/cli/blob/main/docs/guides/using-output-options.md)). Use `-o json` for anything an agent reads.

```bash
hcloud server list -o json | jq '.[] | {id, name, status, ipv4: .public_net.ipv4.ip, labels}'
hcloud server list -o columns=id,name,status,datacenter,labels -o noheader
hcloud server describe web-1 -o format='{{ .ServerType.Name }} {{ .Datacenter.Location.Name }}'
hcloud all list -o json > inventory.json  # every resource in the project (no secrets inside)
```

## Read and inspect (Read token is enough)

```bash
hcloud server describe <name|id>
hcloud server list -l role=web             # label selector
hcloud network list; hcloud network describe <name>   # subnets, routes, attached servers
hcloud firewall list; hcloud firewall describe <name> # rules and applied_to selectors
hcloud load-balancer list; hcloud load-balancer describe <name>   # targets, services, health
hcloud volume list; hcloud volume describe <name>
hcloud placement-group list
hcloud primary-ip list; hcloud floating-ip list
hcloud ssh-key list
hcloud certificate list
hcloud image list --type snapshot,backup
hcloud server metrics <name> --type cpu,network --start 1h   # metrics without a monitoring stack
```

## Mutations (Read & Write token, deliberate)

Prefer Terraform for anything long-lived. The CLI is for break-glass, one-off inspection of behaviour, and cleanup. Map the write token inside the command, single quotes mandatory:

```bash
secret-run --only HCLOUD_TOKEN_RW -- bash -c 'HCLOUD_TOKEN=$HCLOUD_TOKEN_RW hcloud server reboot web-1'
secret-run --only HCLOUD_TOKEN_RW -- bash -c 'HCLOUD_TOKEN=$HCLOUD_TOKEN_RW hcloud server create-image --type snapshot --description pre-upgrade web-1'
secret-run --only HCLOUD_TOKEN_RW -- bash -c 'HCLOUD_TOKEN=$HCLOUD_TOKEN_RW hcloud firewall apply-to-resource <fw> --type label_selector --label-selector role=web'
secret-run --only HCLOUD_TOKEN_RW -- bash -c 'HCLOUD_TOKEN=$HCLOUD_TOKEN_RW hcloud server enable-backup db-1'
secret-run --only HCLOUD_TOKEN_RW -- bash -c 'HCLOUD_TOKEN=$HCLOUD_TOKEN_RW hcloud server enable-protection web-1 delete rebuild'
```

Why not `-- env HCLOUD_TOKEN="$HCLOUD_TOKEN_RW" hcloud ...`: the outer shell expands `$HCLOUD_TOKEN_RW` before `secret-run` has decrypted it, so `hcloud` receives an empty token and fails with an authentication error (or, worse, falls back to a context on disk).

Anything created by hand must be imported into Terraform or deleted before the task is closed; see [terraform.md](terraform.md).

## Raw API

```bash
hcloud api /v1/servers                     # GET with the current token, paginated JSON
hcloud api /v1/actions?status=running      # in-flight actions
```

The full endpoint list, pagination and rate-limit headers are in the [API reference](https://docs.hetzner.cloud/reference/cloud). Watch `RateLimit-*` response headers in loops.

## Kubernetes checks (if the kubernetes provider is selected)

```bash
kubectl -n kube-system get pods -l app.kubernetes.io/name=hcloud-cloud-controller-manager
kubectl -n kube-system get pods -l app.kubernetes.io/name=hcloud-csi
kubectl get nodes -o wide                  # ProviderID hcloud://<id> means CCM adopted the node
kubectl get svc -A | grep LoadBalancer     # each maps to `hcloud load-balancer list`
hcloud load-balancer list -l hcloud-ccm/service-uid   # LBs created by the CCM
```

CCM and CSI docs: [quickstart](https://github.com/hetznercloud/hcloud-cloud-controller-manager/blob/main/docs/guides/quickstart.md), [csi quickstart](https://github.com/hetznercloud/csi-driver/blob/main/docs/kubernetes/guides/quickstart.md). Cluster-level conventions: [kubernetes skill](../../kubernetes/SKILL.md).

## Object Storage

`hcloud` does not manage Object Storage. Use any S3 client with the per-project S3 credentials and the endpoint `https://<fsn1|nbg1|hel1>.your-objectstorage.com` ([Object Storage overview](https://docs.hetzner.com/storage/object-storage/overview/)). With the AWS CLI, `secret-run --only HETZNER_S3_ACCESS_KEY,HETZNER_S3_SECRET_KEY -- bash -c 'AWS_ACCESS_KEY_ID=$HETZNER_S3_ACCESS_KEY AWS_SECRET_ACCESS_KEY=$HETZNER_S3_SECRET_KEY aws --endpoint-url https://fsn1.your-objectstorage.com s3 ls s3://<bucket>'` (`--only A,B` takes a comma-separated list, see [secrets skill](../../secrets/SKILL.md)).
