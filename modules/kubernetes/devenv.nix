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

  enterTest = ''
    kubectl version --client
    helm version
    k9s version --short
    kustomize version
    stern --version
  '';
}
