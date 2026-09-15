# Terraform on DigitalOcean

DigitalOcean-specific conventions: backend, provider, resource patterns and gotchas. Generic Terraform practice (layout, modules, testing, CI) lives in the [terraform skill](../../terraform/SKILL.md); do not duplicate it here. Provider docs: [digitalocean/digitalocean](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs), source [digitalocean/terraform-provider-digitalocean](https://github.com/digitalocean/terraform-provider-digitalocean).

Run every Terraform command through `secret-run` so tokens exist only in the child process:

```bash
secret-run --only DIGITALOCEAN_ACCESS_TOKEN,AWS_ACCESS_KEY_ID,AWS_SECRET_ACCESS_KEY -- terraform plan -out=plan.tfplan
```

## Backend: Spaces via the S3 backend

Copied from the [Spaces Terraform backend reference](https://docs.digitalocean.com/products/spaces/reference/terraform-backend/), which requires Terraform 1.6.3 or newer:

```hcl
terraform {
  required_version = ">= 1.10"

  backend "s3" {
    endpoints = {
      s3 = "https://fra1.digitaloceanspaces.com"     # the bucket's Spaces region
    }
    bucket = "<org>-tfstate-fra1"
    key    = "myproject/prod/terraform.tfstate"

    # AWS-specific checks that do not apply to Spaces
    skip_credentials_validation = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_s3_checksum            = true
    region                      = "us-east-1"          # required by the backend, unused by Spaces

    use_lockfile = true                                # lock file next to the state, in the same bucket
  }
}
```

- Credentials are a Spaces access key pair in `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`, stored with `secret-add` and injected by `secret-run`. Never in the backend block, never in `-backend-config` files committed to Git.
- `use_lockfile = true` gives S3-style state locking without any lock table; there is no DynamoDB equivalent on Spaces, so without it two applies can race.
- The state bucket has `versioning { enabled = true }` and `acl = "private"`, and its access key is a limited key with Read/Write/Delete on that bucket only ([manage access](https://docs.digitalocean.com/products/spaces/how-to/manage-access/)).
- Create the bucket in a `bootstrap/` root with local state applied once, then migrate: the bucket cannot store its own state on the first run.
- One key per project and environment (`<project>/<env>/terraform.tfstate`); no workspaces sharing a key, because a wrong `TF_WORKSPACE` applies dev config with prod tokens.
- State holds database passwords and Spaces keys in plain text. Treat the bucket as a secret store.

## Provider

```hcl
terraform {
  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.100"
    }
  }
}

provider "digitalocean" {
  # No token here. Read from DIGITALOCEAN_TOKEN, then DIGITALOCEAN_ACCESS_TOKEN.
  # Spaces operations (buckets, CDN) read SPACES_ACCESS_KEY_ID / SPACES_SECRET_ACCESS_KEY.
}
```

The provider reads `DIGITALOCEAN_TOKEN` first, then `DIGITALOCEAN_ACCESS_TOKEN`; `spaces_access_id`/`spaces_secret_key` default to `SPACES_ACCESS_KEY_ID`/`SPACES_SECRET_ACCESS_KEY` ([provider arguments](https://github.com/digitalocean/terraform-provider-digitalocean/blob/main/docs/index.md)). If a root manages Spaces buckets, add those two names to `secret-run --only` as well; they can be the same key pair as the backend if that key has full access, but a limited state key cannot create buckets.

`~> 2.100` pins the 2.x line from 2.100.0 ([releases](https://github.com/digitalocean/terraform-provider-digitalocean/releases)); bump deliberately after reading the changelog.

## Project, VPC, firewall, Droplet

```hcl
resource "digitalocean_project" "this" {
  name        = "${var.project}-${var.environment}"
  environment = title(var.environment)         # Development | Staging | Production
  purpose     = "Web Application"
  resources   = [digitalocean_droplet.web.urn, digitalocean_database_cluster.pg.urn]
}

resource "digitalocean_vpc" "this" {
  name   = "${var.project}-${var.environment}"
  region = var.region
}

resource "digitalocean_ssh_key" "ops" {
  name       = "ops"
  public_key = file("keys/ops.pub")
}

resource "digitalocean_droplet" "web" {
  name       = "${var.project}-${var.environment}-web-1"
  region     = var.region
  size       = "s-2vcpu-4gb"
  image      = "ubuntu-24-04-x64"
  vpc_uuid   = digitalocean_vpc.this.id
  ssh_keys   = [digitalocean_ssh_key.ops.fingerprint]
  monitoring = true
  backups    = true
  user_data  = file("cloud-init/web.yaml")
  tags       = local.tags_web
}

resource "digitalocean_firewall" "web" {
  name = "${var.project}-${var.environment}-web"
  tags = [local.tag_web]

  inbound_rule {
    protocol                  = "tcp"
    port_range                = "443"
    source_load_balancer_uids = [digitalocean_loadbalancer.public.id]
  }
  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = var.admin_cidrs
  }
  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}
```

Tags are strings; create them explicitly with `digitalocean_tag` when several resources reference them, otherwise a Droplet destroy can race a firewall that still expects the tag ([digitalocean_tag](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/tag)). Keep `local.tags_*` in one `locals.tf` with at least `<project>`, `<env>` and `managed-by:terraform`.

## Load balancer, database, DOKS

```hcl
resource "digitalocean_certificate" "public" {
  name    = "${var.project}-${var.environment}"
  type    = "lets_encrypt"
  domains = [var.public_fqdn]                       # DNS must be on DigitalOcean for Let's Encrypt
}

resource "digitalocean_loadbalancer" "public" {
  name                   = "${var.project}-${var.environment}-public"
  region                 = var.region
  vpc_uuid               = digitalocean_vpc.this.id
  droplet_tag            = local.tag_web
  redirect_http_to_https = true

  forwarding_rule {
    entry_port       = 443
    entry_protocol   = "https"
    target_port      = 80
    target_protocol  = "http"
    certificate_name = digitalocean_certificate.public.name
  }
  healthcheck {
    port     = 80
    protocol = "http"
    path     = "/healthz"
  }
}

resource "digitalocean_database_cluster" "pg" {
  name                 = "${var.project}-${var.environment}-pg"
  engine               = "pg"
  version              = "16"
  size                 = "db-s-2vcpu-4gb"
  region               = var.region
  node_count           = var.environment == "prod" ? 2 : 1     # standby in production
  private_network_uuid = digitalocean_vpc.this.id
  tags                 = local.tags_common
}

resource "digitalocean_database_firewall" "pg" {
  cluster_id = digitalocean_database_cluster.pg.id
  rule {
    type  = "tag"
    value = local.tag_app
  }
}

resource "digitalocean_database_user" "app" {
  cluster_id = digitalocean_database_cluster.pg.id
  name       = "app"
}

resource "digitalocean_kubernetes_cluster" "this" {
  name          = "${var.project}-${var.environment}"
  region        = var.region
  version       = var.doks_version                   # from `doctl kubernetes options versions`
  vpc_uuid      = digitalocean_vpc.this.id
  ha            = var.environment == "prod"
  auto_upgrade  = true
  surge_upgrade = true
  maintenance_policy {
    day        = "sunday"
    start_time = "02:00"
  }

  node_pool {
    name       = "default"
    size       = "s-2vcpu-4gb"
    auto_scale = true
    min_nodes  = 2
    max_nodes  = 6
    tags       = local.tags_common
  }
}
```

Docs: [loadbalancer](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/loadbalancer), [certificate](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/certificate), [database_cluster](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/database_cluster), [database_firewall](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/database_firewall), [kubernetes_cluster](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/kubernetes_cluster). Use the private hostname output (`private_host`) in application config, never `host`. Wire `kubectl`/Helm via the [kubernetes skill](../../kubernetes/SKILL.md) using `doctl kubernetes cluster kubeconfig save`, not the `kube_config` output (it lands in state).

## Spaces, CDN, registry, alerts

```hcl
resource "digitalocean_spaces_bucket" "assets" {
  name   = "${var.project}-${var.environment}-assets"
  region = "fra1"
  acl    = "private"
  versioning { enabled = true }
}

resource "digitalocean_cdn" "assets" {
  origin         = digitalocean_spaces_bucket.assets.bucket_domain_name
  custom_domain  = "assets.${var.public_domain}"
  certificate_name = digitalocean_certificate.assets.name
  ttl            = 3600
}

resource "digitalocean_container_registry" "this" {
  name                   = var.org
  subscription_tier_slug = "basic"
  region                 = "fra1"
}

resource "digitalocean_monitor_alert" "cpu" {
  alerts { email = [var.oncall_email] }
  window      = "5m"
  type        = "v1/insights/droplet/cpu"
  compare     = "GreaterThan"
  value       = 85
  enabled     = true
  tags        = [local.tag_web]
  description = "CPU > 85% on ${local.tag_web}"
}
```

Docs: [spaces_bucket](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/spaces_bucket), [cdn](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/cdn), [container_registry](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/container_registry), [monitor_alert](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/monitor_alert), [uptime_check](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/uptime_check).

## Lint and scan

```bash
terraform fmt -check -recursive && terraform validate
tflint --recursive          # core rules: unused declarations, deprecated syntax, pinned versions
trivy config .              # misconfiguration checks; no HIGH/CRITICAL
```

There is no official tflint ruleset for DigitalOcean; the core rules still catch unpinned providers and unused variables ([tflint](https://github.com/terraform-linters/tflint)). `trivy config` has generic checks (open firewalls, public buckets) plus [DigitalOcean checks](https://github.com/aquasecurity/trivy-checks/tree/main/checks/cloud/digitalocean).

## Gotchas

- **Token precedence**: `DIGITALOCEAN_TOKEN` beats `DIGITALOCEAN_ACCESS_TOKEN`. Keep only one in the environment or `plan` and `doctl` use different identities.
- **Custom scopes and refresh**: `terraform plan` refreshes every resource, so the deploy token needs `read` scopes on everything in state, not only on what changes.
- **Droplet `image` changes force replacement**; `size` changes resize in place (with a reboot). Use `lifecycle { ignore_changes = [image] }` on long-lived Droplets you patch in place.
- **Region is per resource**, not on the provider; `var.region` on every regional resource and one Spaces region for buckets.
- **`vpc_uuid` cannot be changed** after creation on Droplets, databases and DOKS; a VPC move is a replacement.
- **Load balancers with `droplet_tag` and `droplet_ids` at once** conflict; pick tags.
- **`digitalocean_database_cluster` passwords and `kube_config`** are in state and in outputs; mark outputs `sensitive = true` and never print them in CI.
- **DOKS `version` drifts** when `auto_upgrade` is on; add `lifecycle { ignore_changes = [version] }` or set it from the `digitalocean_kubernetes_versions` data source ([data source](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/data-sources/kubernetes_versions)).
- **Let's Encrypt certificates** require the domain to be in DigitalOcean DNS; otherwise use `type = "custom"` with your own certificate ([certificate](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/certificate)).
- **Spaces backend and provider keys are different variables** (`AWS_*` vs `SPACES_*`); a root that manages buckets needs both sets.
