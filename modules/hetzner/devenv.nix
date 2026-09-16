# Hetzner Cloud: hcloud CLI. No official MCP server exists.
{ pkgs, ... }:
{
  packages = [ pkgs.hcloud ];

  scripts.cloud-onboard-hetzner = {
    description = "Read-only hetzner onboarding with local evidence reports";
    exec = ''
      cd "$DEVENV_ROOT"
      exec ${
        import ../../pkgs/onboarding.nix {
          inherit pkgs;
          provider = "hetzner";
        }
      }/bin/cloud-onboard-hetzner "$@"
    '';
  };

  enterTest = ''
    cloud-onboard-hetzner --help
    hcloud version
  '';
}
