# Azure MCP server

Verified 2026-09-15. Sources: [Azure MCP Server overview](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/overview),
[get started](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/get-started),
[tools reference](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/tools/),
[server README](https://github.com/microsoft/mcp/blob/main/servers/Azure.Mcp.Server/README.md),
[command reference](https://github.com/microsoft/mcp/blob/main/servers/Azure.Mcp.Server/docs/azmcp-commands.md).

## What the project ships

`modules/azure/mcp.json` registers one server, merged into the project's
`.mcp.json` by `init`:

```json
{
  "mcpServers": {
    "azure": {
      "command": "azure-mcp",
      "args": ["server", "start", "--read-only", "--mode", "namespace"]
    }
  }
}
```

- `azure-mcp` is the nixpkgs binary (package `azure-mcp`, version
  **3.0.0-beta.33**, upstream [microsoft/mcp](https://github.com/microsoft/mcp)).
  The npm package `@azure/mcp` is newer, but the project uses the nixpkgs build
  so every developer and CI runner gets the same version without a network
  fetch at start-up.
- `--read-only` exposes only tools that read; create, update and delete tools
  are not registered at all, so the agent cannot be talked into a mutation.
- `--mode namespace` collapses tools into one per Azure service (`storage`,
  `keyvault`, `aks`, ...) which keeps the tool list short enough for the model to
  reason about. `--mode all` exposes every tool individually; `--mode single`
  exposes one dispatcher tool.

## Authentication

The server uses the Azure Identity SDK credential chain
(`DefaultAzureCredential`), which falls through to `AzureCliCredential`
([credential chains](https://learn.microsoft.com/en-us/dotnet/azure/sdk/authentication/credential-chains),
[DefaultAzureCredential](https://learn.microsoft.com/en-us/dotnet/api/azure.identity.defaultazurecredential),
[AzureCliCredential](https://learn.microsoft.com/en-us/dotnet/api/azure.identity.azureclicredential)).
In practice:

1. `az login` before starting the agent. No secrets are configured in `.mcp.json`.
2. Pick the subscription with `az account set --subscription <id>`, or export
   `AZURE_SUBSCRIPTION_ID`; every tool's `--subscription` parameter defaults to
   that variable.
3. Confirm with `az account show` that the agent is pointed at the intended
   subscription before you ask it anything.

The server acts with exactly the RBAC of the logged-in identity. Recommend an
identity holding **Reader** on the target subscription for agent sessions (see
[iam.md](iam.md)); read-only mode plus a Reader role means neither a prompt
injection nor a server bug can change anything.

## Elicitation

Tools that return sensitive data (secrets, keys, connection strings) ask the
MCP client for confirmation first. Never pass
`--dangerously-disable-elicitation`; it removes that prompt and is meant only
for fully automated pipelines in trusted environments. If a value is needed,
fetch it with `az keyvault secret show ... | secret-add NAME` instead of through
the agent.

## Opt-in write access

Write access is a per-project decision, never a template default. To enable it,
edit the project's own `.mcp.json` (not the template) and remove `--read-only`:

```json
"args": ["server", "start", "--mode", "namespace"]
```

Then:

- Use an identity with `Contributor` on one resource group, not the subscription.
- Keep `--mode namespace` so the agent still sees a bounded tool set.
- Keep elicitation on.
- Review every mutation the agent proposes; prefer that it writes Terraform or
  Bicep you apply yourself over calling create tools directly.

## Narrowing the tool surface

Restrict the server to the services a project uses with one or more
`--namespace` flags, or to individual tools with `--tool` (the two cannot be
combined; `--tool` implies `--mode all`):

```json
"args": ["server", "start", "--read-only", "--mode", "namespace", "--namespace", "storage", "--namespace", "keyvault"]
```

List available namespaces and tools with `azure-mcp tools list`. Fewer tools
means less context per turn and less scope for a wrong call.

## Troubleshooting

- `az login` expired: the server returns authentication errors; re-run `az login`
  and restart the agent session.
- Wrong tenant: `az login --tenant <id>`; `DefaultAzureCredential` uses whatever
  `az account show` reports.
- Sovereign cloud: start with `--cloud AzureUSGovernment` or `AzureChinaCloud`
  after `az cloud set`.
- Version check: `azure-mcp --version` (also run by `devenv test`).
