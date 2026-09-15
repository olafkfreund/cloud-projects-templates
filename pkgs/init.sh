# cloud-init: compose a devenv cloud project from $SRC (this flake's source).
providers() { for d in "$SRC"/modules/*/; do d=${d%/}; d=${d##*/}; [ "$d" = common ] || printf '%s ' "$d"; done; }
usage() {
  echo "usage: nix run github:olafkfreund/cloud-projects-templates -- <provider>... [--into DIR]" >&2
  echo "providers: $(providers)" >&2
  exit 1
}
[ $# -gt 0 ] || usage
