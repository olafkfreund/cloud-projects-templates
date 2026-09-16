# DigitalOcean: doctl CLI.
{ pkgs, ... }:
{
  packages = [ pkgs.doctl ];

  scripts.cloud-onboard-digitalocean = {
    description = "Read-only digitalocean onboarding with local evidence reports";
    exec = ''
      cd "$DEVENV_ROOT"
      exec ${
        import ../../pkgs/onboarding.nix {
          inherit pkgs;
          provider = "digitalocean";
        }
      }/bin/cloud-onboard-digitalocean "$@"
    '';
  };

  enterTest = ''
    cloud-onboard-digitalocean --help
    doctl version
  '';
}
