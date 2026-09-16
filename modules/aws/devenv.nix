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
    description = "Read-only aws onboarding with local evidence reports";
    exec = ''
      cd "$DEVENV_ROOT"
      exec ${
        import ../../pkgs/onboarding.nix {
          inherit pkgs;
          provider = "aws";
        }
      }/bin/cloud-onboard-aws "$@"
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
