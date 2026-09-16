# Maintainer operation: replaces generated templates, never user projects.
[ "$#" -eq 0 ] || { echo 'usage: nix run .#regenerate-templates (from the repository root)' >&2; exit 1; }
fail() { echo "$*" >&2; exit 1; }
root=$(git rev-parse --show-toplevel) || fail 'run from a Git checkout'
[ "$(pwd -P)" = "$(realpath "$root")" ] || fail 'run from the Git worktree root'
[ -f flake.nix ] && [ -f pkgs/init.sh ] && [ -d templates/base ] || fail 'not a cloud-projects-templates checkout'
[ ! -L templates ] && [ ! -L templates/base ] || fail 'refusing symlinked template root/base'
read -r -a providers <<<"${CLOUD_PROVIDERS:?provider list required}"
for p in "${providers[@]}"; do
  [ ! -L "templates/$p" ] || fail "refusing symlink: templates/$p"
  if [ -e "templates/$p" ]; then
    [ -d "templates/$p" ] || fail "not a directory: templates/$p"
    [ -z "$(find "templates/$p" -name .git -print -quit)" ] || fail "nested Git repository in templates/$p"
  fi
done

stage=$(mktemp -d ../.cloud-templates.XXXXXX)
trap 'rm -rf -- "$stage"' EXIT
echo 'Regenerating: all generated templates/<provider> directories will be replaced.' >&2
for p in "${providers[@]}"; do
  "${CLOUD_INIT:?initializer required}" "$p" --into "$stage/$p"
  rm -rf -- "$stage/$p/.git"
done
# All generation succeeded. Only these fixed provider directories are replaced.
for p in "${providers[@]}"; do
  rm -rf -- "templates/$p"
  mv -- "$stage/$p" "templates/$p"
done
echo 'Templates regenerated. Inspect git diff before committing.' >&2
