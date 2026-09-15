# Cloudflare: wrangler (Workers/Pages/R2/D1), cloudflared (Tunnels), flarectl (zones/DNS).
{ pkgs, ... }:
{
  packages = with pkgs; [
    wrangler
    cloudflared
    flarectl
  ];

  enterTest = ''
    wrangler --version
    cloudflared --version
    flarectl --version
  '';
}
