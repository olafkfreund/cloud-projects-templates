# Shared package construction; callers supply their own pinned pkgs.
{ pkgs, provider }:
let
  cli = {
    aws = [ pkgs.awscli2 ];
    azure = [ (pkgs.azure-cli.withExtensions [ pkgs.azure-cli.extensions.resource-graph ]) ];
    gcp = [ pkgs.google-cloud-sdk ];
    oci = [ pkgs.oci-cli ];
    kubernetes = [ pkgs.kubectl ];
    cloudflare = [ ];
    hetzner = [ ];
    digitalocean = [ ];
  };
in
pkgs.writeShellApplication {
  name = "cloud-onboard-${provider}";
  runtimeInputs = [ pkgs.git ] ++ cli.${provider};
  text = ''
    exec ${pkgs.python3}/bin/python3 ${../skills/cloud-onboarding/scripts}/${provider}_report.py "$@"
  '';
}
