# Google Cloud: gcloud with the GKE auth plugin.
{ pkgs, ... }:
{
  packages = [
    (pkgs.google-cloud-sdk.withExtraComponents [
      pkgs.google-cloud-sdk.components.gke-gcloud-auth-plugin
    ])
  ];

  enterTest = ''
    gcloud version
    gke-gcloud-auth-plugin --version
  '';
}
