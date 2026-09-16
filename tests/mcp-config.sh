#!/usr/bin/env bash
set -euo pipefail
init=${1:?initializer executable required}
shift
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
for p in "$@"; do
  "$init" "$p" --into "$work/$p"
  config="$work/$p/.mcp.json"
  jq -e '
    .mcpServers | type == "object" and length > 0 and all(.[];
      type == "object" and
      ((.env // {}) | type == "object" and all(.[]; type == "string")) and
      if .type == "http" then (.url | type == "string" and startswith("https://"))
      else
        (.command | type == "string" and length > 0) and
        (.args | type == "array" and all(.[]; type == "string")) and
        (if .command == "uvx" then
          (.args[0] | test("^[A-Za-z0-9_.-]+==[0-9]+\\.[0-9]+\\.[0-9]+$"))
        elif .command == "npx" then
          .args[0] == "-y" and
          (.args[1] | test("^(@[A-Za-z0-9._-]+/)?[A-Za-z0-9._-]+@[0-9]+\\.[0-9]+\\.[0-9]+$"))
        else true end)
      end
    )
  ' "$config" >/dev/null
  jq -e '.mcpServers.terraform |
    .command == "terraform-mcp-server" and .args == ["stdio", "--toolsets", "registry,registry-private"] and
    .env.TFE_TOKEN == "${TFE_TOKEN:-}"' "$config" >/dev/null
  case "$p" in
    aws)
      jq -e '.mcpServers | has("aws-docs") and (.aws.env | .READ_OPERATIONS_ONLY == "true" and .REQUIRE_MUTATION_CONSENT == "true")' "$config" >/dev/null ;;
    azure)
      jq -e '.mcpServers.azure | .command == "azure-mcp" and .args == ["server", "start", "--read-only", "--mode", "namespace"]' "$config" >/dev/null ;;
    kubernetes)
      jq -e '.mcpServers.kubernetes.args | index("--read-only") != null and index("--disable-multi-cluster") != null' "$config" >/dev/null ;;
    gcp)
      jq -e '.mcpServers.gcloud.args[2:] == ["--config", "${DEVENV_ROOT}/.mcp/gcloud-allow.json"]' "$config" >/dev/null
      jq -e '. == {allow: ["config list", "auth list", "projects list", "projects describe", "compute instances list", "compute instances describe", "container clusters list", "run services list", "storage buckets list", "iam service-accounts list", "logging read"]}' "$work/$p/.mcp/gcloud-allow.json" >/dev/null ;;
    oci)
      jq -e '.mcpServers.oci.env | .OCI_CONFIG_PROFILE == "${OCI_CLI_PROFILE:-DEFAULT}" and .OCI_MCP_AUTH_TYPE == "auto"' "$config" >/dev/null ;;
    cloudflare)
      jq -e '.mcpServers | has("cloudflare-docs") and (.["cloudflare-api"] |
        .env.CF_MCP_AUTH == "Bearer ${CLOUDFLARE_READ_TOKEN}" and
        .args[2:] == ["https://mcp.cloudflare.com/mcp", "--header", "Authorization:${CF_MCP_AUTH}"])' "$config" >/dev/null ;;
    digitalocean)
      jq -e '.mcpServers | has("digitalocean-docs") and .digitalocean.env.DIGITALOCEAN_API_TOKEN == "${DIGITALOCEAN_READ_TOKEN}"' "$config" >/dev/null ;;
    hetzner)
      jq -e '.mcpServers | keys == ["terraform"]' "$config" >/dev/null ;;
    *) echo "missing MCP assertions for $p" >&2; exit 1 ;;
  esac
done
echo 'MCP configuration checks passed (no cloud authorization tested)'
