# gcloud MCP server

Verified 2026-09-15. Sources:
[googleapis/gcloud-mcp](https://github.com/googleapis/gcloud-mcp),
[allow/deny list documentation](https://github.com/googleapis/gcloud-mcp/blob/main/doc/denylist.md),
[Google Cloud MCP overview](https://docs.cloud.google.com/mcp/overview).

## What this project configures

`.mcp.json` (merged from the template) defines one server:

```json
"gcloud": {
  "command": "npx",
  "args": ["-y", "@google-cloud/gcloud-mcp@0.5.3",
           "--config", "${DEVENV_ROOT}/.mcp/gcloud-allow.json"]
}
```

- Version pinned to `0.5.3`; bump deliberately, re-read the allow list
  semantics when you do.
- `--config` **must be an absolute path**, hence `${DEVENV_ROOT}`.
- Auth: the server runs `gcloud` with the **active gcloud account and
  config** of the shell that starts the agent. Whatever `gcloud auth list`
  shows as active is what the agent is.

## There is no read-only mode

gcloud-mcp has no `--read-only` flag. Control is a JSON file containing
**either** an `allow` list **or** a `deny` list, never both. A built-in
default deny list of destructive commands is always enforced on top.

The shipped `.mcp/gcloud-allow.json`:

```json
{
  "allow": [
    "config list",
    "auth list",
    "projects list",
    "projects describe",
    "compute instances list",
    "compute instances describe",
    "container clusters list",
    "run services list",
    "storage buckets list",
    "iam service-accounts list",
    "logging read"
  ]
}
```

Matching is by **command or command group prefix**, so an entry like
`compute instances` would allow `compute instances delete`. The shipped
list names full commands to stay narrow, but this is still a coarse
text filter: it does not understand flags, and an allowed `describe` can
still read metadata you might consider sensitive.

## The real boundary is identity

Because the allow list is coarse, do not rely on it as a security control.
Run agent sessions as a **Viewer-only service account** via impersonation
([Impersonation](https://docs.cloud.google.com/iam/docs/service-account-impersonation)):

```sh
# once, by an admin
gcloud iam service-accounts create sa-agent-ro --project=PROJECT_ID
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member=serviceAccount:sa-agent-ro@PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/viewer
gcloud iam service-accounts add-iam-policy-binding \
  sa-agent-ro@PROJECT_ID.iam.gserviceaccount.com \
  --member=user:you@example.com --role=roles/iam.serviceAccountTokenCreator

# in the shell that launches the agent
gcloud config configurations create agent
gcloud config set project PROJECT_ID
gcloud config set auth/impersonate_service_account sa-agent-ro@PROJECT_ID.iam.gserviceaccount.com
```

Now even a widened allow list cannot mutate anything: IAM rejects it.
`roles/viewer` is a basic role and is acceptable here only because it is
read-only; prefer a narrower custom role with just the `*.list` and
`*.get` permissions you need
([Custom roles](https://docs.cloud.google.com/iam/docs/understanding-custom-roles)).

Add a principal access boundary or deny policy for the agent SA if the org
wants it capped regardless of future grants
([Deny overview](https://docs.cloud.google.com/iam/docs/deny-overview)).

## Opt-in: letting the agent write

Widen the allow list in the project's own `.mcp/gcloud-allow.json`, for
example adding `"run deploy"` or `"compute instances create"`.

**Warning.** Combined with a non-read-only identity this gives the agent
the power to create, change and bill resources. Before you do it:

1. Switch the impersonated SA to one with exactly the extra roles needed
   (for example `roles/run.developer` on one project), not your user.
2. Keep entries as full commands, never a bare group like `compute`.
3. Remember the default deny list still blocks the most destructive
   commands; it is not configurable.
4. Review every mutating call in the session transcript.

Prefer having the agent write Terraform and letting CI apply it over
direct `gcloud` mutations; the plan is reviewable, the CLI call is not.

## Google-managed remote MCP servers

Google also hosts remote MCP servers for its APIs
([MCP overview](https://docs.cloud.google.com/mcp/overview)). Those go
through `mcp.googleapis.com`, which means IAM can enforce read-only
org-wide, independently of any client-side allow list: create an IAM
**deny policy** on the permission `mcp.googleapis.com/tools.call` with the
condition

```
api.getAttribute('mcp.googleapis.com/tool.isReadOnly', false) == false
```

so every tool not annotated read-only is refused
([Prevent read-write tool use](https://docs.cloud.google.com/mcp/prevent-read-write-tool-use)).
This does not cover the local `gcloud-mcp` server, which calls the regular
service APIs; for that, identity (above) is the control.

## Checklist before starting an agent session

- [ ] `gcloud config list` shows the agent configuration and the RO SA.
- [ ] `gcloud auth list` shows the expected account.
- [ ] `.mcp/gcloud-allow.json` has only an `allow` key and only full
      commands.
- [ ] `DEVENV_ROOT` is set (you are inside `devenv shell`).
- [ ] Secrets are not in the environment the agent inherits; use
      `secret-run --only NAME -- cmd` for the one command that needs them.
