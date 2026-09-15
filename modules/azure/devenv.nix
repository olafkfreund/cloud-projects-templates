# Azure: az CLI (+AKS preview), Bicep, kubelogin, Azure MCP server.
{ pkgs, ... }:
{
  packages = with pkgs; [
    # containerapp is omitted: its nixpkgs build currently fails (pins kubernetes==24.2.0).
    # Add azure-cli.extensions.containerapp here in your project once it builds again.
    (azure-cli.withExtensions [ azure-cli.extensions.aks-preview ])
    bicep
    kubelogin
    azure-mcp
  ];

  enterTest = ''
    az version
    bicep --version
    kubelogin --version
    command -v azure-mcp
  '';
}
