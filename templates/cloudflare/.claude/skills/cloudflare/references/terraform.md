# Terraform on Cloudflare

Cloudflare-specific conventions. Generic module layout, versioning, review and lint rules live in the [terraform skill](../../terraform/SKILL.md).

## Provider: v5 only

```hcl
terraform {
  required_version = ">= 1.9"
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }
}

provider "cloudflare" {}   # reads CLOUDFLARE_API_TOKEN; never set api_token in code
```

The provider reads `CLOUDFLARE_API_TOKEN` from the environment ([provider docs](https://github.com/cloudflare/terraform-provider-cloudflare/blob/main/docs/index.md), [registry](https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs)). Run every Terraform command under `secret-run --only CLOUDFLARE_API_TOKEN,… -- …` so the token exists only for that process. Current release line at the time of writing: v5.25 ([releases](https://github.com/cloudflare/terraform-provider-cloudflare/releases)).

**v5 is a rewrite, not an upgrade.** Resources were renamed and regrouped, blocks became nested objects (`rules { }` becomes `rules = [{ }]`), and some resources were removed ([v5 upgrade guide](https://github.com/cloudflare/terraform-provider-cloudflare/blob/main/docs/guides/version-5-upgrade.md)). Any snippet you find online that uses `cloudflare_record`, `cloudflare_access_application`, `cloudflare_tunnel`, `cloudflare_zone_settings_override` or block syntax is v4 and must not be copied. Verify names against the provider's `docs/resources/` before use.

| v4 (do not use) | v5 |
|---|---|
| `cloudflare_record` | `cloudflare_dns_record` |
| `cloudflare_zone_settings_override` | one `cloudflare_zone_setting` per setting |
| `cloudflare_access_application` / `_policy` | `cloudflare_zero_trust_access_application` / `_policy` |
| `cloudflare_tunnel` / `_config` | `cloudflare_zero_trust_tunnel_cloudflared` / `_config` |
| `cloudflare_worker_script`, `cloudflare_worker_secret` | `cloudflare_workers_script` (secrets are bindings; or `wrangler secret put`) |
| `zone = "example.com"` on `cloudflare_zone` | `name = "example.com"`, `account = { id = … }` |

Migrating an existing v4 codebase: use Cloudflare's `tf-migrate`, which rewrites resources, attributes and generates `moved {}`/`import {}` blocks (linked from the upgrade guide). Application-scoped Access policies still need manual work.

## Remote state in R2

R2 is S3-compatible, so the standard `s3` backend works with these settings ([R2 remote backend](https://developers.cloudflare.com/terraform/advanced-topics/remote-backend/)):

```hcl
terraform {
  backend "s3" {
    bucket = "tfstate-<project>"
    key    = "<project>/<env>/terraform.tfstate"
    region = "auto"
    endpoints = { s3 = "https://<ACCOUNT_ID>.r2.cloudflarestorage.com" }
    use_path_style              = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
  }
}
```

Cloudflare's page shows `access_key`/`secret_key` inline; **we do not**. The backend reads `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, so create an R2 API token with `Object Read & Write` on the state bucket ([R2 tokens](https://developers.cloudflare.com/r2/api/tokens/)), store both halves with `secret-add R2_ACCESS_KEY_ID` and `secret-add R2_SECRET_ACCESS_KEY`, and map them inside the command:

```bash
secret-run --only CLOUDFLARE_API_TOKEN,R2_ACCESS_KEY_ID,R2_SECRET_ACCESS_KEY -- bash -c \
  'AWS_ACCESS_KEY_ID=$R2_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY=$R2_SECRET_ACCESS_KEY terraform init'
```

Notes:

- The `skip_*` flags stop the backend calling AWS-only endpoints (STS, IMDS, region lists, checksum trailers) that R2 does not implement. All of them are required.
- Cloudflare's backend page does not cover `use_lockfile` state locking on R2; treat locking as unverified, keep one apply path (CI) per state key and do not rely on a lock.
- The state bucket is created once, by hand or from a separate bootstrap root with `cloudflare_r2_bucket`; never from the root whose state it stores.

## Resource patterns (v5)

Zone and DNS ([zone](https://github.com/cloudflare/terraform-provider-cloudflare/blob/main/docs/resources/zone.md), [dns_record](https://github.com/cloudflare/terraform-provider-cloudflare/blob/main/docs/resources/dns_record.md), [zone_dnssec](https://github.com/cloudflare/terraform-provider-cloudflare/blob/main/docs/resources/zone_dnssec.md), [zone data source](https://github.com/cloudflare/terraform-provider-cloudflare/blob/main/docs/data-sources/zone.md)):

```hcl
data "cloudflare_zone" "main" {
  filter = { name = "example.com" }
}

resource "cloudflare_dns_record" "www" {
  zone_id = data.cloudflare_zone.main.id
  name    = "www"
  type    = "A"
  content = "203.0.113.10"
  ttl     = 1          # 1 = automatic; required for proxied records
  proxied = true
  comment = "managed by terraform"
}

resource "cloudflare_zone_dnssec" "main" {
  zone_id = data.cloudflare_zone.main.id
  status  = "active"
}
```

Zone settings, one resource per setting ([zone_setting](https://github.com/cloudflare/terraform-provider-cloudflare/blob/main/docs/resources/zone_setting.md)):

```hcl
locals {
  zone_settings = {
    ssl              = "strict"
    min_tls_version  = "1.2"
    always_use_https = "on"
  }
}

resource "cloudflare_zone_setting" "this" {
  for_each   = local.zone_settings
  zone_id    = data.cloudflare_zone.main.id
  setting_id = each.key
  value      = each.value
}
```

WAF managed ruleset and a rate limit ([ruleset](https://github.com/cloudflare/terraform-provider-cloudflare/blob/main/docs/resources/ruleset.md), managed ruleset ID from [Cloudflare Managed Ruleset](https://developers.cloudflare.com/waf/managed-rules/reference/cloudflare-managed-ruleset/)):

```hcl
resource "cloudflare_ruleset" "managed_waf" {
  zone_id = data.cloudflare_zone.main.id
  name    = "managed waf"
  kind    = "zone"
  phase   = "http_request_firewall_managed"
  rules = [{
    ref               = "cloudflare_managed"
    expression        = "true"
    action            = "execute"
    action_parameters = { id = "efb7b8c949ac4650a09736fc376e9aee" }
  }]
}

resource "cloudflare_ruleset" "rate_limit" {
  zone_id = data.cloudflare_zone.main.id
  name    = "rate limits"
  kind    = "zone"
  phase   = "http_ratelimit"
  rules = [{
    ref        = "login"
    expression = "http.request.uri.path eq \"/login\""
    action     = "block"
    ratelimit = {
      characteristics     = ["cf.colo.id", "ip.src"]
      period              = 60
      requests_per_period = 20
      mitigation_timeout  = 600
    }
  }]
}
```

Tunnel, ingress and Access ([tunnel](https://github.com/cloudflare/terraform-provider-cloudflare/blob/main/docs/resources/zero_trust_tunnel_cloudflared.md), [tunnel config](https://github.com/cloudflare/terraform-provider-cloudflare/blob/main/docs/resources/zero_trust_tunnel_cloudflared_config.md), [access application](https://github.com/cloudflare/terraform-provider-cloudflare/blob/main/docs/resources/zero_trust_access_application.md), [access policy](https://github.com/cloudflare/terraform-provider-cloudflare/blob/main/docs/resources/zero_trust_access_policy.md)):

```hcl
resource "cloudflare_zero_trust_tunnel_cloudflared" "app" {
  account_id = var.account_id
  name       = "app-${var.env}"
  config_src = "cloudflare"     # remotely managed; ingress lives in the _config resource
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "app" {
  account_id = var.account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.app.id
  config = {
    ingress = [
      { hostname = "app.example.com", service = "http://localhost:8080" },
      { service = "http_status:404" },
    ]
  }
}

resource "cloudflare_dns_record" "app" {
  zone_id = data.cloudflare_zone.main.id
  name    = "app"
  type    = "CNAME"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.app.id}.cfargotunnel.com"
  ttl     = 1
  proxied = true
}

resource "cloudflare_zero_trust_access_policy" "staff" {
  account_id = var.account_id
  name       = "staff"
  decision   = "allow"
  include    = [{ email_domain = { domain = "example.com" } }]
}

resource "cloudflare_zero_trust_access_application" "app" {
  account_id = var.account_id
  name       = "app"
  domain     = "app.example.com"
  type       = "self_hosted"
  policies   = [{ id = cloudflare_zero_trust_access_policy.staff.id, precedence = 1 }]
}
```

Storage and Workers ([r2_bucket](https://github.com/cloudflare/terraform-provider-cloudflare/blob/main/docs/resources/r2_bucket.md), [workers_script](https://github.com/cloudflare/terraform-provider-cloudflare/blob/main/docs/resources/workers_script.md), [Workers IaC](https://developers.cloudflare.com/workers/platform/infrastructure-as-code/)):

```hcl
resource "cloudflare_r2_bucket" "assets" {
  account_id = var.account_id
  name       = "assets-${var.env}"
  location   = "weur"   # honoured only at creation
}
```

Terraform owns buckets, namespaces, databases, routes and custom domains; `wrangler deploy` owns the script bundle. Cloudflare's IaC page says you can manage only the resources you want in Terraform and use Wrangler for versions and deployments. If you do put the script in `cloudflare_workers_script`, copy every binding from `wrangler.toml` into it, because whichever tool deploys last wins.

Tokens for other systems ([api_token](https://github.com/cloudflare/terraform-provider-cloudflare/blob/main/docs/resources/api_token.md)): `cloudflare_api_token` with `policies[].permission_groups`, `condition.request_ip.in` and `expires_on`. The resulting `value` lands in state, so this root's state bucket must be as protected as the token itself.

## Importing existing resources

Terraform expects to own what it manages; anything created in the dashboard must be imported or it will be recreated ([import](https://developers.cloudflare.com/terraform/advanced-topics/import-cloudflare-resources/)). `cf-terraforming generate --resource-type cloudflare_dns_record --zone <id>` writes HCL, `cf-terraforming import` prints the `terraform import` commands. Run both under `secret-run --only CLOUDFLARE_READ_TOKEN` (generation only reads), then `terraform plan` must show no changes.

## Cloudflare's own best practices

From [Terraform best practices](https://developers.cloudflare.com/terraform/advanced-topics/best-practices/):

- Let Terraform own the whole lifecycle of a resource; no dashboard edits on managed resources.
- Directory per account, then zone, then product, so ownership and blast radius are scoped.
- Keep modules and `dynamic` blocks to a minimum; they make plans harder to reproduce.
- Separate Cloudflare accounts and domains per environment.
- Credentials from a secret store, never plaintext (agenix here).

## Gotchas

- `ttl` must be `1` (automatic) on proxied records; another value makes the API reject the record.
- Rule IDs inside rulesets change when rules are reordered; use `ref` on every rule to keep them stable ([rule ID changes](https://developers.cloudflare.com/terraform/troubleshooting/rule-id-changes/)).
- A DNS authentication error on `cloudflare_dns_record` usually means the token lacks `Zone: DNS: Edit` on that zone or is a user token on a product that needs an account token ([troubleshooting](https://developers.cloudflare.com/terraform/troubleshooting/authentication-error-dns-records/)).
- `cloudflare_zone_setting` for `ssl` only sets the mode; it does not issue the origin certificate. Full (strict) with a missing origin cert is a 526 for every visitor.
- `location` on `cloudflare_r2_bucket` is best effort and only read at creation; a recreated bucket with the same name keeps the old location.
- Data source `cloudflare_zone` filters by name; resource IDs are hex zone IDs, so pass `data.cloudflare_zone.main.id` not the name.
