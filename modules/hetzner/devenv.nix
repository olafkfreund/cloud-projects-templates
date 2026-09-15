# Hetzner Cloud: hcloud CLI. No official MCP server exists.
{ pkgs, ... }:
{
  packages = [ pkgs.hcloud ];

  enterTest = ''
    hcloud version
  '';
}
