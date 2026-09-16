# Kubernetes: kubectl, Helm, k9s, Kustomize, kubectx/kubens, stern.
{ pkgs, ... }:
{
  packages = with pkgs; [
    kubectl
    kubernetes-helm
    k9s
    kustomize
    kubectx
    stern
  ];

  scripts.cloud-onboard-kubernetes = {
    description = "Read-only kubernetes onboarding with local evidence reports";
    exec = ''
      cd "$DEVENV_ROOT"
      exec ${
        import ../../pkgs/onboarding.nix {
          inherit pkgs;
          provider = "kubernetes";
        }
      }/bin/cloud-onboard-kubernetes "$@"
    '';
  };

  enterTest = ''
    cloud-onboard-kubernetes --help
    kubectl version --client
    helm version
    k9s version --short
    kustomize version
    stern --version
  '';
}
