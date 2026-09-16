# Accessing onboarding commands

All eight providers have `cloud-onboard-<provider>`. The command uses the remote
module revision inside `devenv shell` or direnv; a copied skill script can differ.
The explicit flake app uses the invoked flake revision and preserves your current
working directory. Run from a Git root; `--help` needs neither Git nor credentials.

```sh
just --list
just onboard aws --account-id 123456789012 --regions eu-west-1 --environment production --profile audit
nix run github:olafkfreund/cloud-projects-templates#onboard-aws -- --help
```

The just recipe requires the project environment. Arguments are forwarded
literally and exit codes are preserved. Provider tools are project-local, never
installed globally. A selected provider module makes its command available;
add missing providers through the generator and update the cloud input deliberately.

## Existing projects

Re-run the generator to add missing recipe files and skills. It never overwrites
custom `justfile`, `Justfile`, `.justfile`, symlinks or existing recipe files.
Review adding `import 'cloud-onboarding.just'` to your own task file, or use:

```sh
just --justfile cloud-onboarding.just onboard aws --help
```

`devenv update` refreshes modules, not copied skills/recipes. Generate a disposable
project to review updates to copied files. No generator command updates your lock
automatically. Existing credentials remain runtime-only; use `secret-run --only`
for agenix-backed API tokens. Direct flake apps do not decrypt secrets for you.

## First-run examples

Replace every example identifier and use an existing read-only credential.

### Azure

```sh
cloud-onboard-azure --tenant-id TENANT_UUID --subscription-id SUBSCRIPTION_UUID --environment production
```

See [Azure coverage](../../azure/references/onboarding.md).

### GCP

```sh
cloud-onboard-gcp --project-id my-project --expected-principal reader@example.com --environment production
```

See [GCP coverage](../../gcp/references/onboarding.md).

### OCI

```sh
cloud-onboard-oci --tenancy-id ocid1.tenancy.oc1..EXAMPLE --compartment-ids ocid1.compartment.oc1..EXAMPLE --regions eu-frankfurt-1 --profile audit --environment production
```

See [OCI coverage](../../oci/references/onboarding.md).

### Kubernetes

```sh
cloud-onboard-kubernetes --context production --expected-server https://api.example.com --expected-principal reader --namespaces app --environment production
```

See [Kubernetes coverage](../../kubernetes/references/onboarding.md).

### Cloudflare

```sh
secret-run --only CLOUDFLARE_READ_TOKEN -- cloud-onboard-cloudflare --account-id ACCOUNT_ID --zone-ids ZONE_ID --environment production
```

See [Cloudflare coverage](../../cloudflare/references/onboarding.md).

### Hetzner

```sh
secret-run --only HCLOUD_TOKEN -- cloud-onboard-hetzner --project-label production --acknowledge-project-token --environment production
```

See [Hetzner coverage](../../hetzner/references/onboarding.md).

### DigitalOcean

```sh
secret-run --only DIGITALOCEAN_READ_TOKEN -- cloud-onboard-digitalocean --account-uuid ACCOUNT_UUID --project-id PROJECT_UUID --environment production
```

See [DigitalOcean coverage](../../digitalocean/references/onboarding.md).

## Bounds and interpretation

Common options: `--environment`, `--max-items` (1000), `--command-timeout` (60
seconds), `--timeout` (900 seconds). New collectors additionally bound response
size and total requests/bytes. Reaching limits produces partial coverage.
Exit 0 means collection completed, not compliance; 2 means a partial report;
1 means invalid input, identity failure or output failure. Open the printed
report path and read coverage before prioritizing findings. Reports stay private,
Git-ignored and separate per run. Do not publish them automatically.
