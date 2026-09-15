{
  description = "Multi-provider cloud dev environments with devenv, agent skills, read-only MCP servers and agenix secrets";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      formatter = forAllSystems (pkgs: pkgs.nixfmt-rfc-style);

      packages = forAllSystems (pkgs: {
        default = pkgs.writeShellApplication {
          name = "cloud-init";
          runtimeInputs = with pkgs; [
            coreutils
            jq
            gnused
            gnugrep
          ];
          runtimeEnv.SRC = "${self}";
          text = builtins.readFile ./pkgs/init.sh;
        };
      });

      apps = forAllSystems (pkgs: {
        default = {
          type = "app";
          program = nixpkgs.lib.getExe self.packages.${pkgs.stdenv.hostPlatform.system}.default;
        };
      });
    };
}
