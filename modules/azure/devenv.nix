# Azure: az CLI (+AKS preview), Bicep, kubelogin, Azure MCP server.
{ pkgs, ... }:
{
  packages = with pkgs; [
    # containerapp is omitted: its nixpkgs build currently fails (pins kubernetes==24.2.0).
    # Add azure-cli.extensions.containerapp here in your project once it builds again.
    (azure-cli.withExtensions [
      azure-cli.extensions.aks-preview
      azure-cli.extensions.resource-graph
    ])
    bicep
    kubelogin
    azure-mcp
  ];

  scripts.cloud-onboard-azure = {
    description = "Read-only azure onboarding with local evidence reports";
    exec = ''
      cd "$DEVENV_ROOT"
      exec ${
        import ../../pkgs/onboarding.nix {
          inherit pkgs;
          provider = "azure";
        }
      }/bin/cloud-onboard-azure "$@"
    '';
  };

  enterTest = ''
    cloud-onboard-azure --help
    az version
    az graph query --help >/dev/null
    bicep --version
    kubelogin --version
    command -v azure-mcp
  '';
}
