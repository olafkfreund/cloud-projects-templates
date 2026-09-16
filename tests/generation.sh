#!/usr/bin/env bash
set -euo pipefail
init=${1:?initializer executable required}
regenerate=${2:?regenerator executable required}
src=${3:?source directory required}
shift 3
providers=("$@")
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT

"$init" aws --into "$work/project"
cd "$work/project"
printf '\n# Keep this setting after imports.\nallowUnfree: false\n' >>devenv.yaml
printf '\nuser skill edit\n' >>.claude/skills/aws/SKILL.md
cp .claude/skills/aws/SKILL.md "$work/skill"
jq '.mcpServers.aws.args = ["custom-aws"]' .mcp.json >"$work/mcp.json"
mv "$work/mcp.json" .mcp.json
yq -o=json 'del(.imports)' devenv.yaml >"$work/settings.json"

"$init" azure aws gcp --into .
yq -o=json '.imports' devenv.yaml | jq -e '. == ["cloud/modules/common", "cloud/modules/aws", "cloud/modules/azure", "cloud/modules/gcp"]'
yq -o=json 'del(.imports)' devenv.yaml >"$work/after.json"
cmp "$work/settings.json" "$work/after.json"
grep -q '# Keep this setting after imports.' devenv.yaml
cmp "$work/skill" .claude/skills/aws/SKILL.md
jq -e '.mcpServers.aws.args == ["custom-aws"] and has("mcpServers")' .mcp.json
cp -R . "$work/snapshot"
"$init" azure aws gcp --into .
diff -r --no-dereference "$work/snapshot" .

# Parsed equality must also recognize quoted imports in a flow sequence.
yq -i '.imports style="flow" | .imports[] style="double"' devenv.yaml
cp devenv.yaml "$work/quoted.yaml"
"$init" aws --into .
cmp devenv.yaml "$work/quoted.yaml"
"$init" hetzner --into .
yq -o=json '.imports' devenv.yaml | jq -e '.[-1] == "cloud/modules/hetzner" and length == 5'

# None of these rejected inputs may produce skills, MCP files, or a Git repo.
mkdir "$work/invalid"
for invalid in \
  'imports: [' \
  $'imports: []\n---\nimports: []' \
  '- not-a-mapping' \
  'imports: scalar' \
  'imports: {key: value}' \
  'imports: [42]' \
  'other: missing-imports'; do
  printf '%s\n' "$invalid" >"$work/invalid/devenv.yaml"
  cp -R "$work/invalid" "$work/before-invalid"
  if "$init" aws --into "$work/invalid"; then
    echo 'invalid YAML accepted' >&2
    exit 1
  fi
  diff -r --no-dereference "$work/before-invalid" "$work/invalid"
  rm -r "$work/before-invalid"
done

mkdir -p "$work/checkout/pkgs" "$work/checkout/templates"
cp "$src/flake.nix" "$work/checkout/"
cp "$src/pkgs/init.sh" "$work/checkout/pkgs/"
cp -R --no-preserve=mode "$src/templates/base" "$work/checkout/templates/"
cd "$work/checkout"
git init -q
"$regenerate"
cp -R templates "$work/fresh"
printf 'stale skill\n' >templates/aws/.claude/skills/aws/SKILL.md
rm templates/azure/devenv.nix
printf 'obsolete\n' >templates/gcp/obsolete
"$regenerate"
diff -r --no-dereference "$work/fresh" templates
"$regenerate"
diff -r --no-dereference "$work/fresh" templates
for p in "${providers[@]}"; do
  "$init" "$p" --into "$work/expected/$p"
  diff -r --no-dereference -x .git "$work/expected/$p" "templates/$p"
  test ! -e "templates/$p/.git"
done

reject_regeneration() {
  cp -R templates "$work/before-reject"
  if "$regenerate"; then
    echo 'unsafe regeneration accepted' >&2
    exit 1
  fi
  diff -r --no-dereference "$work/before-reject" templates
  rm -r "$work/before-reject"
}
mkdir templates/azure/nested
git init -q templates/azure/nested
reject_regeneration
rm -r templates/azure/nested
mv templates/aws "$work/saved-aws"
ln -s "$work/saved-aws" templates/aws
reject_regeneration
rm templates/aws
mv "$work/saved-aws" templates/aws
mv templates "$work/saved-templates"
ln -s "$work/saved-templates" templates
if "$regenerate"; then exit 1; fi
diff -r --no-dereference "$work/fresh" "$work/saved-templates"
rm templates
mv "$work/saved-templates" templates
if (cd pkgs && "$regenerate"); then exit 1; fi
diff -r --no-dereference "$work/fresh" templates

# Fail on a later provider, after earlier providers have generated successfully.
printf '#!%s\n' "$(command -v bash)" >"$work/fail-init"
cat >>"$work/fail-init" <<'EOF'
[ "$1" != azure ] || { touch "$TEST_FAILURE"; exit 1; }
exec "$TEST_INIT" "$@"
EOF
chmod +x "$work/fail-init"
if TEST_INIT="$init" TEST_FAILURE="$work/failed-on-azure" CLOUD_INIT="$work/fail-init" CLOUD_PROVIDERS="${providers[*]}" \
  bash -euo pipefail "$src/pkgs/regenerate-templates.sh"; then
  echo 'injected generation failure was ignored' >&2
  exit 1
fi
test -f "$work/failed-on-azure"
diff -r --no-dereference "$work/fresh" templates
test -z "$(find "$work" -maxdepth 1 -name '.cloud-templates.*' -print)"
echo 'generator regression checks passed'
