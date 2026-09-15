# Terraform on Hetzner Cloud

Hetzner-specific conventions: provider, remote state on Object Storage, resource patterns and gotchas. Generic Terraform practice (layout, modules, testing, CI) lives in the [terraform skill](../../terraform/SKILL.md); do not duplicate it here. Provider docs: [registry.terraform.io/providers/hetznercloud/hcloud](https://registry.terraform.io/providers/hetznercloud/hcloud/latest/docs), source [github.com/hetznercloud/terraform-provider-hcloud](https://github.com/hetznercloud/terraform-provider-hcloud) (v1.69.0 released 2026-09-11, [releases](https://github.com/hetznercloud/terraform-provider-hcloud/releases)).

## Provider

```hcl
terraform {
  required_version = ">= 1.10"
  required_providers {
    hcloud = { source = "hetznercloud/hcloud", version = "~> 1.69" }
  }
}

provider "hcloud" {
  # No `token` argument. The provider reads HCLOUD_TOKEN from the environment
  # (https://github.com/hetznercloud/terraform-provider-hcloud/blob/main/docs/index.md).
}
```

The provider accepts `token` but we never set it: a token in HCL or tfvars ends up in git or in the plan file. `plan` runs with the Read token, `apply` with the Read & Write token mapped inside `secret-run`:

```bash
secret-run --only HCLOUD_TOKEN -- terraform plan -out=plan.tfplan
secret-run --only HCLOUD_TOKEN_RW -- bash -c 'HCLOUD_TOKEN=$HCLOUD_TOKEN_RW terraform apply plan.tfplan'
```

Single quotes matter: `-- env HCLOUD_TOKEN="$HCLOUD_TOKEN_RW" terraform apply` expands in the outer shell before decryption and passes an empty token. Data sources also work under the Read token, so `plan` never needs write access.

## Backend: Hetzner Object Storage via the S3 backend

**Semi-verified (community tutorial + [hashicorp/terraform#36924](https://github.com/hashicorp/terraform/issues/36924); official page unavailable).** Hetzner publishes no official Terraform-state page; the flags below come from the Terraform S3 backend docs for S3-compatible providers ([S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3), where HashiCorp calls non-AWS support "best effort"), from the closed issue above (which shows STS/IAM calls leaking without `skip_requesting_account_id`) and from community write-ups on [community.hetzner.com](https://community.hetzner.com/tutorials/). Test `init`, `plan`, `apply` and a second `init` from a clean checkout before relying on it.

```hcl
terraform {
  backend "s3" {
    bucket = "<org>-tfstate-<project>"
    key    = "<project>/<env>/terraform.tfstate"
    region = "fsn1"                       # the Object Storage location string, not an AWS region
    endpoints = {
      s3 = "https://fsn1.your-objectstorage.com"   # or nbg1 / hel1
    }
    use_path_style              = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    # use_lockfile = true   # see "State locking" below before enabling
  }
}
```

Credentials come from the environment as `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (per-project S3 keys, [Generating S3 keys](https://docs.hetzner.com/storage/object-storage/getting-started/generating-s3-keys/)). Store them with `secret-add` and map them the same way as the token:

```bash
secret-run --only HCLOUD_TOKEN,HETZNER_S3_ACCESS_KEY,HETZNER_S3_SECRET_KEY -- bash -c \
  'AWS_ACCESS_KEY_ID=$HETZNER_S3_ACCESS_KEY AWS_SECRET_ACCESS_KEY=$HETZNER_S3_SECRET_KEY terraform init'
```

Bucket requirements: versioning enabled (Hetzner lists versioning and object lock among supported actions, [supported actions](https://docs.hetzner.com/storage/object-storage/supported-actions/)); a bucket policy restricting the bucket to the state key pair ([S3 credentials FAQ](https://docs.hetzner.com/storage/object-storage/faq/s3-credentials)); ideally its own project, because S3 keys are project-wide by default. State holds secrets in plain text.

### State locking

`use_lockfile = true` relies on S3 conditional writes. Hetzner's supported-actions page notes limitations on conditional PUT/DELETE on versioned buckets and does not list `If-None-Match` explicitly, so **whether the lock file works on Hetzner is uncertain** at the time of writing. Until you have tested it (two concurrent `terraform apply` runs, second must fail to lock): leave `use_lockfile` off, run `apply` only from CI with concurrency set to one job per state key, and never apply from a laptop against a state CI also writes. If a test shows the lock works, enable it and record the test in the spec.

Fallback if the backend misbehaves: the `http` backend against a small state server you run, or a different provider's object storage. Do not fall back to local state.

## Resource patterns

```hcl
locals {
  labels = { project = var.project, environment = var.environment, owner = var.owner, managed_by = "terraform" }
}

resource "hcloud_ssh_key" "ops"      { name = "ops-${var.environment}"; public_key = file(var.ssh_public_key_path); labels = local.labels }

resource "hcloud_network" "main"     { name = "${var.project}-${var.environment}"; ip_range = "10.0.0.0/8"; labels = local.labels }
resource "hcloud_network_subnet" "app" {
  network_id = hcloud_network.main.id; type = "cloud"; network_zone = "eu-central"; ip_range = "10.0.2.0/24"
}

resource "hcloud_firewall" "internal" {
  name   = "internal-${var.environment}"
  labels = local.labels
  # no inbound rules: default deny (https://docs.hetzner.com/cloud/firewalls/overview/)
  apply_to { label_selector = "environment=${var.environment},exposure=private" }
}

resource "hcloud_placement_group" "web" { name = "web-${var.environment}"; type = "spread"; labels = local.labels }

resource "hcloud_server" "web" {
  count              = 3
  name               = "web-${count.index}"
  server_type        = "cx22"
  image              = "debian-12"
  location           = "fsn1"
  ssh_keys           = [hcloud_ssh_key.ops.id]
  placement_group_id = hcloud_placement_group.web.id
  labels             = merge(local.labels, { role = "web", exposure = "private" })
  backups            = true
  delete_protection  = var.environment == "prod"
  rebuild_protection = var.environment == "prod"
  public_net { ipv4_enabled = false; ipv6_enabled = true }
  network   { network_id = hcloud_network.main.id }
  user_data = file("${path.module}/cloud-init.yaml")
  depends_on = [hcloud_network_subnet.app]
}

resource "hcloud_load_balancer" "web" { name = "web-${var.environment}"; load_balancer_type = "lb11"; location = "fsn1"; labels = local.labels }
resource "hcloud_load_balancer_network" "web" { load_balancer_id = hcloud_load_balancer.web.id; network_id = hcloud_network.main.id }
resource "hcloud_load_balancer_target" "web" {
  load_balancer_id = hcloud_load_balancer.web.id; type = "label_selector"; label_selector = "role=web"; use_private_ip = true
  depends_on = [hcloud_load_balancer_network.web]
}
resource "hcloud_load_balancer_service" "https" {
  load_balancer_id = hcloud_load_balancer.web.id; protocol = "https"; listen_port = 443; destination_port = 80
  http { certificates = [hcloud_managed_certificate.web.id]; redirect_http = true }
}

resource "hcloud_volume" "data" { name = "data-${var.environment}"; size = 50; location = "fsn1"; format = "ext4"; delete_protection = true; labels = local.labels }
resource "hcloud_volume_attachment" "data" { volume_id = hcloud_volume.data.id; server_id = hcloud_server.db.id; automount = true }
```

Resource and argument names: [provider docs](https://registry.terraform.io/providers/hetznercloud/hcloud/latest/docs). Server types, images and locations: `hcloud server-type list`, `hcloud image list`, `hcloud location list`.

## Gotchas

- **Subnet before server.** A server joining a network needs the subnet to exist; add `depends_on` on the subnet, or the create fails with "no subnet available".
- **Zone mismatch.** A subnet's `network_zone` must match the server's location zone ([Locations](https://docs.hetzner.com/cloud/general/locations/)). `location = "ash"` with `network_zone = "eu-central"` fails at apply, not at plan.
- **Volumes and servers share a location**; use `location` on both or `server_id` on the volume, never mix `location` and `server_id`.
- **Disabling public IPv4 removes default egress.** Add a NAT gateway server and `hcloud_network_route` (`destination = "0.0.0.0/0"`) plus a cloud-init route on the clients, or keep IPv6 for egress where the dependency supports it.
- **`image` changes force replacement.** Pin to a snapshot ID for immutable rollouts; use `lifecycle { ignore_changes = [image] }` only for pets you rebuild by hand.
- **Placement group is full at 10 servers** ([Placement groups](https://docs.hetzner.com/cloud/placement-groups/overview/)); shard larger sets.
- **Firewall by selector, not by `firewall_ids`.** Both work; the selector also covers servers created outside this root and is what the review checklist expects.
- **CCM-managed load balancers** carry the `hcloud-ccm/service-uid` label. Never manage them from Terraform; import nothing from a cluster's namespace.
- **Images and data sources under the Read token** work; `hcloud_server` data sources need the resource to exist, so bootstrap roots go first.
- **Labels are the tagging system.** Keys and values follow Kubernetes label rules; `managed_by=terraform` is mandatory so `hcloud all list -l managed_by!=terraform` shows drift created by hand.
