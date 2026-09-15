# DigitalOcean: doctl CLI.
{ pkgs, ... }:
{
  packages = [ pkgs.doctl ];

  enterTest = ''
    doctl version
  '';
}
