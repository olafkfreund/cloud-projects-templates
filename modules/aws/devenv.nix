# AWS: CLI, session manager, aws-vault, CloudFormation lint, EKS.
# aws-vault integration needs your profile name, so enable it in the project's devenv.nix:
#   aws-vault = { enable = true; profile = "my-profile"; awscliWrapper.enable = true; terraformWrapper.enable = true; };
{ pkgs, ... }:
{
  packages = with pkgs; [
    awscli2
    ssm-session-manager-plugin
    aws-vault
    python3Packages.cfn-lint
    eksctl
  ];

  enterTest = ''
    aws --version
    aws-vault --version
    cfn-lint --version
    eksctl version
  '';
}
