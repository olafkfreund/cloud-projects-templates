# AWS: CLI, session manager, aws-vault, CloudFormation lint, EKS.
# aws-vault integration needs your profile name, so enable it in the project's devenv.nix:
#   aws-vault = { enable = true; profile = "my-profile"; awscliWrapper.enable = true; terraformWrapper.enable = true; };
{ pkgs, ... }:
{
  packages = with pkgs; [
    awscli2
    python3
    ssm-session-manager-plugin
    aws-vault
    python3Packages.cfn-lint
    eksctl
  ];

  scripts.cloud-onboard-aws = {
    description = "Read-only AWS onboarding with local evidence-based reports";
    packages = [
      pkgs.awscli2
      pkgs.git
    ];
    exec = ''
      cd "$DEVENV_ROOT"
      exec ${pkgs.python3}/bin/python3 ${../../skills/cloud-onboarding/scripts/aws_report.py} "$@"
    '';
  };

  enterTest = ''
    aws --version
    cloud-onboard-aws --help
    aws-vault --version
    cfn-lint --version
    eksctl version
  '';
}
