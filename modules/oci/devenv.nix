# Oracle Cloud Infrastructure: OCI CLI.
{ pkgs, ... }:
{
  packages = [ pkgs.oci-cli ];

  enterTest = ''
    oci --version
  '';
}
