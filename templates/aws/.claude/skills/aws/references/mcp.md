# AWS MCP servers

Two servers are configured in the generated project's `.mcp.json` (merged from `modules/aws/mcp.json`). Both are pinned and read-only by default. Neither embeds credentials.

## Configuration (as shipped)

```json
{
  "mcpServers": {
    "aws": {
      "command": "uvx",
      "args": ["awslabs.aws-api-mcp-server==1.5.5"],
      "env": {
        "READ_OPERATIONS_ONLY": "true",
        "REQUIRE_MUTATION_CONSENT": "true",
        "AWS_API_MCP_PROFILE_NAME": "${AWS_PROFILE:-default}",
        "AWS_REGION": "${AWS_REGION:-eu-west-1}",
        "AWS_API_MCP_SUPPRESS_DEPRECATION_WARNING": "true"
      }
    },
    "aws-docs": {
      "command": "uvx",
      "args": ["awslabs.aws-documentation-mcp-server==1.2.1"]
    }
  }
}
```

### `aws` — AWS API MCP Server

Source: [awslabs.aws-api-mcp-server README](https://github.com/awslabs/mcp/blob/main/src/aws-api-mcp-server/README.md), [PyPI 1.5.5](https://pypi.org/project/awslabs.aws-api-mcp-server/1.5.5/). Exposes `call_aws` (run an AWS CLI command) and `suggest_aws_commands`.

| Env var | Value | Effect |
|---|---|---|
| `READ_OPERATIONS_ONLY` | `true` | Each CLI command is checked against the [Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/reference_policies_actions-resources-contextkeys.html); only operations whose access level is not `Write` run. |
| `REQUIRE_MUTATION_CONSENT` | `true` | Any non-read operation triggers an explicit consent prompt (MCP elicitation) before it runs. Redundant while `READ_OPERATIONS_ONLY` is on; it is the safety net once that is removed. |
| `AWS_API_MCP_PROFILE_NAME` | `${AWS_PROFILE:-default}` | Which `~/.aws/config` profile the server uses. Falls back to the boto3 chain if unset. |
| `AWS_REGION` | `${AWS_REGION:-eu-west-1}` | Default Region for commands that do not pass `--region`. |
| `AWS_API_MCP_SUPPRESS_DEPRECATION_WARNING` | `true` | Hides the startup notice that this server is superseded (see below). |

Why the per-operation gate and not only IAM: the README states IAM remains the primary control and `READ_OPERATIONS_ONLY` is an additional layer. Use both. Note that some read-only APIs still return sensitive data (for example `get-secret-value` is classified as Read); the read-only IAM role below is what limits that.

Local file access is confined to `AWS_API_MCP_WORKING_DIR` (default mode `workdir`), so `aws s3 cp` to arbitrary paths is refused.

### `aws-docs` — AWS Documentation MCP Server

Source: [awslabs.aws-documentation-mcp-server](https://github.com/awslabs/mcp/tree/main/src/aws-documentation-mcp-server), [PyPI 1.2.1](https://pypi.org/project/awslabs.aws-documentation-mcp-server/1.2.1/). Searches and reads docs.aws.amazon.com. No AWS credentials, no auth. Use it to verify API parameters, quotas and best-practice pages before writing IaC instead of relying on memory.

## Upstream status: superseded

The README marks the AWS API MCP Server as superseded by the managed [AWS MCP Server](https://docs.aws.amazon.com/agent-toolkit/latest/userguide/mcp-server.html) ([user guide](https://docs.aws.amazon.com/aws-mcp/latest/userguide/what-is-aws-mcp.html)), reached through the local proxy [`mcp-proxy-for-aws`](https://github.com/aws/mcp-proxy-for-aws) ([PyPI](https://pypi.org/project/mcp-proxy-for-aws/)). The [migration guide](https://github.com/awslabs/mcp/blob/main/src/aws-api-mcp-server/MIGRATION.md) maps `READ_OPERATIONS_ONLY` to either IAM condition keys or the proxy's `--read-only` flag.

We stay on the local server for now because the proxy's `--read-only` disables every tool not annotated `readOnlyHint=true`, which hides the API tool entirely rather than filtering individual operations. The per-operation gate keeps read access useful for agents. Migration is tracked as a follow-up issue; when the managed server offers an equivalent per-operation read-only mode, switch and drop the deprecation suppression.

## Authentication

The server uses the standard [boto3 credential chain](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html): environment variables, then the named profile, then SSO cache, then instance/container roles. Nothing is stored in `.mcp.json`.

Start the agent with credentials already resolved, one of:

```bash
aws sso login --profile dev-ro
aws-vault exec dev-ro -- claude          # short-lived creds injected into the agent and its MCP children
# or
AWS_PROFILE=dev-ro claude                # server resolves the SSO profile itself
```

`aws-vault exec` is preferred: credentials expire with the session and never touch disk in plain text ([aws-vault](https://github.com/99designs/aws-vault)). Confirm with `aws-vault exec dev-ro -- aws sts get-caller-identity` before starting.

### Use a read-only role for agent sessions

Give agents a dedicated Identity Center permission set or role with [`ReadOnlyAccess`](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/ReadOnlyAccess.html) or the narrower [`ViewOnlyAccess`](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/ViewOnlyAccess.html). Why: `READ_OPERATIONS_ONLY` is a client-side check in a Python process; IAM is enforced by AWS. `ViewOnlyAccess` also excludes most `Get*` calls that return data contents (secrets, parameters), which is the right default for an agent reading architecture. Add explicit `Deny` statements for `secretsmanager:GetSecretValue`, `ssm:GetParameter*` with decryption and `kms:Decrypt` if you use `ReadOnlyAccess`.

Never start an agent under an admin profile "just to look". Check `AWS_PROFILE` in the shell prompt before launching.

## Opting in to writes (per project)

Only when a project needs the agent to change AWS resources, and only in that project's own `.mcp.json`:

1. Remove `READ_OPERATIONS_ONLY` from `mcpServers.aws.env`.
2. Keep `REQUIRE_MUTATION_CONSENT=true`. Every mutating call then asks for confirmation in the client. Verify your MCP client supports elicitation; if it does not, mutations fail closed.
3. Start the agent with a profile whose IAM permissions are the smallest set the task needs (a scoped deploy role, never `AdministratorAccess`) and ideally in a non-production account.
4. Record the change in the PR that introduces it, with the reason.

Risks you accept: the agent can now create, modify and delete anything its IAM role allows, including state buckets, IAM policies and data; consent prompts depend on the human reading them; mistakes in a prod account are not reversible by `git revert`. Prefer the alternative: let the agent produce Terraform and run `terraform plan` through the normal review path, keeping the MCP server read-only.

## Verification

```bash
claude mcp list                                  # both servers connected
# in the agent: "list my S3 buckets"             → succeeds (read)
# in the agent: "create an S3 bucket named x"    → refused by READ_OPERATIONS_ONLY
```

## Troubleshooting

- **`Unable to locate credentials`**: the agent was started without `aws-vault exec` and `AWS_PROFILE` is unset or points to a profile without a valid SSO session; run `aws sso login --profile <p>`.
- **`ExpiredToken`**: SSO session expired; log in again and restart the agent (MCP children inherit the environment at start).
- **Command refused as write**: expected under `READ_OPERATIONS_ONLY`; produce Terraform instead.
- **Deprecation notice in tool descriptions**: `AWS_API_MCP_SUPPRESS_DEPRECATION_WARNING` missing from the project's `.mcp.json`; re-run the init or add it.
- **`uvx` download every start**: `uvx` caches by version; the pinned `==1.5.5` avoids re-resolution. Do not change to `@latest` (supply-chain risk, and the pin is what CI validated).
