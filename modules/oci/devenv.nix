# Oracle Cloud Infrastructure: OCI CLI.
{ pkgs, ... }:
{
  packages = [ pkgs.oci-cli ];

  scripts.cloud-onboard-oci = {
    description = "Read-only oci onboarding with local evidence reports";
    exec = ''
      cd "$DEVENV_ROOT"
      exec ${
        import ../../pkgs/onboarding.nix {
          inherit pkgs;
          provider = "oci";
        }
      }/bin/cloud-onboard-oci "$@"
    '';
  };

  enterTest = ''
    cloud-onboard-oci --help
    oci --version
  '';
}
