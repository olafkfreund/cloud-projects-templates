# OCI MCP server for agents

Verified 2026-09-15 against [github.com/oracle/mcp](https://github.com/oracle/mcp) and [PyPI oracle.oci-cloud-mcp-server](https://pypi.org/project/oracle.oci-cloud-mcp-server/) (latest 2.2.3, released 2026-08-25).

## Configuration used by this template

`.mcp.json` entry (merged by the generator):

```json
{
  "mcpServers": {
    "oci": {
      "command": "uvx",
      "args": ["oracle.oci-cloud-mcp-server==2.2.3"],
      "env": {
        "OCI_CONFIG_PROFILE": "${OCI_CLI_PROFILE:-DEFAULT}",
        "OCI_MCP_AUTH_TYPE": "auto",
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    }
  }
}
```

- `uvx oracle.oci-cloud-mcp-server==2.2.3`: pinned version; `uv` is in the devenv shell. Bump deliberately after reading the release notes.
- `OCI_CONFIG_PROFILE=${OCI_CLI_PROFILE:-DEFAULT}`: the server reads the same `~/.oci/config` profile the shell uses, so `export OCI_CLI_PROFILE=ro-agent` before launching the agent selects the read-only identity. (`OCI_CONFIG_FILE` overrides the file path if needed.)
- `OCI_MCP_AUTH_TYPE=auto`: uses a security token when the selected profile declares `security_token_file`, otherwise falls back to the profile's API key. Other values: `api_key`, `security_token`, `instance_principal`, `resource_principal`, `instance_principal_delegation`, `resource_principal_delegation`, `identity_domain_upst`, `oke_workload_identity`. Source: [PyPI README](https://pypi.org/project/oracle.oci-cloud-mcp-server/).

## Why oci-cloud-mcp-server, not oci-api-mcp-server

Oracle ships two general servers in [oracle/mcp](https://github.com/oracle/mcp):

| Server | How it works | Verdict |
|--------|--------------|---------|
| `oracle.oci-cloud-mcp-server` (`src/oci-cloud-mcp-server/`) | Calls the OCI Python SDK directly, typed tools (`invoke_oci_api`, `describe_oci_operation`, ...). Oracle names it the suggested general-purpose entry point. | **Use this.** |
| `oracle.oci-api-mcp-server` (`src/oci-api-mcp-server/`) | Wraps arbitrary `oci` CLI commands in a subprocess. | Avoid: it can run any CLI command the profile allows, giving the agent the CLI's full blast radius plus shell-level side effects. |

## There is no read-only mode. IAM is the boundary.

Neither server documents a read-only flag, a deny-list, or a tool allow-list (checked in the repo README and the PyPI README on 2026-09-15). Every tool call is executed with whatever the configured profile is allowed to do. Therefore:

1. **Run agent sessions with the dedicated read-only profile**:
   ```
   oci session authenticate --profile-name ro-agent --region <region> --no-browser   # once per day
   export OCI_CLI_PROFILE=ro-agent
   claude   # or any MCP client; the .mcp.json env picks up the profile
   ```
   The `ro-agent` profile belongs to a user in group `ro-agents` whose only policy is `Allow group ro-agents to read all-resources in tenancy`. Setup and verification steps are in [iam.md](iam.md).
2. **Verify before trusting**: ask the agent to list compartments (should work) and to create a tag namespace (must fail with `NotAuthorizedOrNotFound`).
3. **Security token, not API key.** With `auto` and a token-backed profile the credential expires in 1 hour (refreshable to 24 h), which caps the exposure window if the agent context leaks it. Do not store an API key PEM for the agent user unless there is no interactive path; if you must, keep it in agenix and inject with `secret-run --only oci-agent-key -- claude`.
4. **Never point the agent at `DEFAULT`** on a machine where `DEFAULT` is an admin identity. The `${OCI_CLI_PROFILE:-DEFAULT}` fallback exists for convenience; the `init` output reminds you to set `OCI_CLI_PROFILE=ro-agent`.

## Write access is opt-in (and dangerous)

Enabling writes means nothing in the MCP config changes; you simply launch with a profile whose group has `use`/`manage` policies:

```
export OCI_CLI_PROFILE=dev-admin     # a token profile with manage in compartment dev
```

Warning: with a write-capable profile every agent tool call can create, modify or delete resources, including IAM policies, in whatever scope that profile has. Before doing this:

- [ ] Scope the profile's group to one non-production compartment (`manage all-resources in compartment dev`), never `in tenancy`.
- [ ] Require MFA on that group's policies (`where request.user.mfaTotpVerified='true'`) so a token issued without MFA cannot mutate.
- [ ] Use a security token (1 h) and end the session with `unset OCI_CLI_PROFILE` or by letting the token expire.
- [ ] Prefer having the agent write Terraform and you run `terraform apply`; the MCP write path is for exploration, not deployment.
- [ ] Keep Cloud Guard activity detectors and Audit export on so agent-initiated changes are attributable to the `agent-bot` user.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Server starts but every call returns `NotAuthenticated` | Token expired or profile missing `security_token_file` with `auto` falling back to a non-existent key | `oci session refresh --profile ro-agent` or re-authenticate |
| `NotAuthorizedOrNotFound` on reads | Policy lacks `read` for that resource family or compartment | Extend the `ro-agents` policy at `read`, not `use` |
| Server uses the wrong tenancy | `OCI_CLI_PROFILE` not exported in the shell that launched the client | Export it before starting the agent; check `oci session validate` |
| Version drift | Someone changed `==2.2.3` to `@latest` | Keep the pin; upgrade via a PR after reading [oracle/mcp releases](https://github.com/oracle/mcp) |

## Related

- [iam.md](iam.md): `ro-agents` group, policy, and profile creation.
- [cli-cheatsheet.md](cli-cheatsheet.md): the read-only commands the agent is expected to use.
- Oracle MCP repo: [github.com/oracle/mcp](https://github.com/oracle/mcp).
