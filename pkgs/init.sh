# cloud-init: compose a devenv cloud project from $SRC (this flake's source).
# Never overwrites existing files; safe to re-run to add providers.
providers() { for d in "$SRC"/modules/*/; do d=${d%/}; d=${d##*/}; [ "$d" = common ] || printf '%s ' "$d"; done; }
usage() {
  echo "usage: nix run github:olafkfreund/cloud-projects-templates -- <provider>... [--into DIR]" >&2
  echo "providers: $(providers)" >&2
  exit 1
}

into=.
selected=()
while [ $# -gt 0 ]; do
  case $1 in
    --into) into=${2:?--into needs a directory}; shift 2 ;;
    -h | --help) usage ;;
    *)
      [ "$1" != common ] && [ -f "$SRC/modules/$1/devenv.nix" ] || { echo "unknown provider: $1" >&2; usage; }
      selected+=("$1"); shift ;;
  esac
done
[ ${#selected[@]} -gt 0 ] || usage

mkdir -p "$into"
cd "$into"
# devenv git hooks need a repository
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || git init -q

copy() { cp -rn --no-preserve=mode "$@"; } # never overwrite, make store copies writable

[ -f devenv.yaml ] || copy "$SRC/templates/base/." .

add_skill() {
  mkdir -p .claude/skills .agents/skills
  copy "$SRC/skills/$1" .claude/skills/
  [ -e ".agents/skills/$1" ] || [ -L ".agents/skills/$1" ] || ln -s "../../.claude/skills/$1" ".agents/skills/$1"
}

merge_mcp() { # existing entries win
  local new="$SRC/modules/$1/mcp.json"
  [ -f "$new" ] || return 0
  [ -f .mcp.json ] || echo '{}' >.mcp.json
  jq -s '.[0] * .[1]' "$new" .mcp.json >.mcp.json.tmp
  mv .mcp.json.tmp .mcp.json
}

add_skill secrets
add_skill terraform
merge_mcp common

for p in "${selected[@]}"; do
  grep -qx "  - cloud/modules/$p" devenv.yaml || printf '  - cloud/modules/%s\n' "$p" >>devenv.yaml
  add_skill "$p"
  merge_mcp "$p"
  for f in "$SRC/modules/$p"/*.json; do
    [ "${f##*/}" = mcp.json ] && continue
    mkdir -p .mcp && copy "$f" .mcp/
  done
  if [ -f "$SRC/modules/$p/agents.md" ] && ! grep -qF "<!-- provider:$p:start -->" AGENTS.md; then
    { printf '\n<!-- provider:%s:start -->\n' "$p"; cat "$SRC/modules/$p/agents.md"; printf '<!-- provider:%s:end -->\n' "$p"; } >>AGENTS.md
  fi
done

cat >&2 <<EOF
Project ready in $(pwd) with: ${selected[*]}

Next:
  1. Add your public key to secrets.nix recipients (cat ~/.ssh/id_ed25519.pub)
  2. direnv allow        (or: devenv shell)
  3. Log in to each provider (see AGENTS.md), then start your agent, e.g. secret-run -- claude
EOF
for p in "${selected[@]}"; do
  case $p in
    gcp) echo "WARNING: the gcloud MCP server has no read-only mode; run agents as a Viewer-only service account." >&2 ;;
    oci) echo "WARNING: the OCI MCP server has no read-only mode; set OCI_CLI_PROFILE to a read-only profile." >&2 ;;
  esac
done
