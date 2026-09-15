---
name: secrets
description: Handle API keys, personal access tokens (PAT), cloud tokens and passwords safely in this project with agenix-format secrets (age encryption). Use whenever a task needs a credential or token (GitHub PAT, Infracost API key, TFE_TOKEN, Cloudflare/Datadog/API keys), when adding, rotating, rekeying or removing a secret, when onboarding or removing a teammate's key, when passing a secret to terraform, a CLI or an MCP server, or when you are tempted to put a secret in a file, env file, tfvars, code, log or chat. Covers secret-add, secret-edit, secret-list, secret-run --only, secret-rekey, secrets.nix recipients and leak response.
---

# Secrets (agenix format)

Secrets live encrypted in `secrets/<NAME>.age`. The recipients for each file are listed in `secrets.nix`.
The `.age` files are safe to commit, even in a public repo. Plaintext never touches disk.
The format is standard [agenix](https://github.com/ryantm/agenix) (age-encrypted files plus `secrets.nix`), so `agenix -d` and NixOS `age.secrets` can read these files.

## Hard rules

1. **Never reveal a secret value.** Don't print, `echo`, `cat` or log it. Don't paste it into chat, code, commit messages, `*.tfvars`, `.env` files, `.mcp.json` or any other file. Encryption doesn't help once a value is on screen or in a transcript.
2. **Never decrypt a secret to a file.** Don't run `age -d … > file`. Values reach processes only through `secret-run`.
3. **Give a command only the secrets it needs.** Always prefer `secret-run --only NAME -- <cmd>` over a bare `secret-run`, so a compromised tool sees only what it needs.
4. **If a secret was exposed** (printed, committed in plaintext, or pasted), treat it as compromised. Revoke it at the provider, then store a new value. See [Leak response](#leak-response).
5. **Leave `secrets/` for encrypted files only.** The pre-commit hook rejects anything there except `*.age` and `.gitkeep`. Don't bypass it.

## Commands (available in `devenv shell`)

| Command | What it does |
|---|---|
| `secret-add NAME` | Encrypts a value read from stdin, or a hidden prompt, into `secrets/NAME.age`, and adds `NAME` to `secrets.nix`. `NAME` must match `^[A-Z][A-Z0-9_]*$` because it becomes an env var. |
| `secret-edit NAME` | Replaces the value (same as `secret-add`). |
| `secret-list` | Prints names only, never values. |
| `secret-run [--only A,B] -- CMD…` | Decrypts the selected secrets into env vars **for CMD only**, then runs it. Fails if an `--only` name doesn't exist. |
| `secret-rekey` | Re-encrypts every secret for the current `secrets.nix` recipients, in memory. |

The decryption identity is `$AGENIX_IDENTITY`, defaulting to `~/.ssh/id_ed25519`. An `age-keygen` key file also works.

## Recipes

```bash
# First time: add your public key, then add teammates' keys
cat ~/.ssh/id_ed25519.pub        # paste into `recipients` in secrets.nix

# Store values without them appearing in shell history
gh auth token | secret-add GITHUB_TOKEN
secret-add INFRACOST_API_KEY     # hidden prompt

# Use values
secret-run --only INFRACOST_API_KEY -- infracost breakdown --path .
secret-run --only GITHUB_TOKEN -- gh repo list
secret-run --only TF_VAR_db_password -- terraform plan -out=plan.tfplan   # TF_VAR_* maps to variables

# Start an agent whose MCP servers need tokens (.mcp.json uses ${TFE_TOKEN})
secret-run --only TFE_TOKEN -- claude
```

For Terraform, mark such variables `sensitive = true`. Prefer ephemeral or write-only arguments where the provider supports them, because values passed to normal arguments end up in state. See the `terraform` skill.

## Team changes

**Add a teammate:**
1. Add their public key to `recipients`.
2. Run `secret-rekey`.
3. Commit `secrets.nix` and `secrets/`.

**Remove a teammate:**
1. Delete their key from `recipients`.
2. Run `secret-rekey`.
3. Commit.
4. **Rotate every secret they could read.** They can still decrypt old ciphertext from git history, so rekeying alone doesn't remove their access.

**Per-secret recipients:** edit that secret's entry in `secrets.nix`, for example `"secrets/PROD_TOKEN.age".publicKeys = [ "ssh-ed25519 …ops" ];`, then run `secret-rekey`.

## Leak response

1. **Revoke or rotate** the credential at its provider (GitHub, cloud console, vendor dashboard) immediately.
2. **Store the new value:** `… | secret-add NAME`.
3. **If plaintext was committed,** rotating is the fix. Rewriting git history doesn't un-leak a pushed secret. Tell the user.
4. **Check** the provider's audit log for use of the old credential.

## Where secrets do not belong

- **Runtime secrets for deployed workloads** belong in the cloud secret store: AWS Secrets Manager or SSM SecureString, Azure Key Vault, GCP Secret Manager, or OCI Vault. They are provisioned by Terraform and read by the workload's identity. agenix is for **developer and CI credentials** used from this repo.
- **Kubernetes:** use External Secrets, Sealed Secrets, or the cloud CSI driver. Never commit plaintext `Secret` manifests.
