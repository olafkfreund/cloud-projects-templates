# Cloudflare: wrangler (Workers/Pages/R2/D1), cloudflared (Tunnels), flarectl (zones/DNS).
{ pkgs, ... }:
{
  packages = with pkgs; [
    wrangler
    cloudflared
    flarectl
  ];

  scripts.cloud-onboard-cloudflare = {
    description = "Read-only cloudflare onboarding with local evidence reports";
    exec = ''
      cd "$DEVENV_ROOT"
      exec ${
        import ../../pkgs/onboarding.nix {
          inherit pkgs;
          provider = "cloudflare";
        }
      }/bin/cloud-onboard-cloudflare "$@"
    '';
  };

  enterTest = ''
    cloud-onboard-cloudflare --help
    wrangler --version
    cloudflared --version
    flarectl --version
  '';
}
