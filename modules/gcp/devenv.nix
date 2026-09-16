# Google Cloud: gcloud with the GKE auth plugin.
{ pkgs, ... }:
{
  packages = [
    (pkgs.google-cloud-sdk.withExtraComponents [
      pkgs.google-cloud-sdk.components.gke-gcloud-auth-plugin
    ])
  ];

  scripts.cloud-onboard-gcp = {
    description = "Read-only gcp onboarding with local evidence reports";
    exec = ''
      cd "$DEVENV_ROOT"
      exec ${
        import ../../pkgs/onboarding.nix {
          inherit pkgs;
          provider = "gcp";
        }
      }/bin/cloud-onboard-gcp "$@"
    '';
  };

  enterTest = ''
    cloud-onboard-gcp --help
    gcloud version
    gke-gcloud-auth-plugin --version
  '';
}
