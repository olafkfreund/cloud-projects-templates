# Requires the project's devenv shell or direnv environment.
[doc('Read-only cloud assessment: onboard PROVIDER --help')]
[positional-arguments]
[script("bash")]
onboard provider *args:
    case "$1" in aws|azure|gcp|oci|kubernetes|cloudflare|hetzner|digitalocean) ;; *) echo 'Unknown cloud provider' >&2; exit 1;; esac; command="cloud-onboard-$1"; shift; command -v "$command" >/dev/null || { echo 'Provider command unavailable; enter the project shell and add its provider module.' >&2; exit 1; }; exec "$command" "$@"
