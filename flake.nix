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
      providers = [
        "aws"
        "azure"
        "gcp"
        "oci"
        "kubernetes"
      ];
    in
    {
      templates =
        nixpkgs.lib.genAttrs providers (p: {
          path = ./templates/${p};
          description = "${p} cloud project: devenv, Terraform, agent skills, read-only MCP, agenix secrets";
          welcomeText = ''
            # ${p} project ready
            1. Add your public key to `recipients` in `secrets.nix`
            2. `direnv allow` (or `devenv shell`)
            3. Log in (see `AGENTS.md`), then start your agent: `secret-run -- claude`

            Add more providers: `nix run github:olafkfreund/cloud-projects-templates -- <provider>`
          '';
        })
        // {
          default = self.templates.aws;
        };

      checks = forAllSystems (pkgs: {
        # templates/<p> must equal what the init script generates
        templates-fresh = pkgs.runCommand "templates-fresh" { } ''
          for p in ${toString providers}; do
            ${
              nixpkgs.lib.getExe self.packages.${pkgs.stdenv.hostPlatform.system}.default
            } "$p" --into "$TMPDIR/$p" 2>/dev/null
            ${pkgs.diffutils}/bin/diff -r --no-dereference "$TMPDIR/$p" ${self}/templates/$p \
              || { echo "templates/$p is stale: run nix run . -- $p --into templates/$p"; exit 1; }
          done
          touch $out
        '';
        # Agent Skills spec: only name+description, name == dir, SKILL.md <= 500 lines, references <= 300
        skills = pkgs.runCommand "skills" { } ''
          fail() { echo "$1"; exit 1; }
          for d in ${self}/skills/*/; do
            n=$(basename "$d"); f="$d/SKILL.md"
            [ -f "$f" ] || fail "$n: missing SKILL.md"
            keys=$(awk 'NR==1&&/^---$/{fm=1;next} fm&&/^---$/{exit} fm&&/^[a-z_-]+:/{sub(/:.*/,"");print}' "$f" | sort | tr '\n' ' ')
            [ "$keys" = "description name " ] || fail "$n: frontmatter keys must be name+description, got: $keys"
            grep -qx "name: $n" "$f" || fail "$n: name must equal directory name"
            [ "$(wc -l <"$f")" -le 500 ] || fail "$n: SKILL.md over 500 lines"
            for r in "$d"/references/*.md; do
              [ -e "$r" ] || continue
              [ "$(wc -l <"$r")" -le 300 ] || fail "$n: $(basename "$r") over 300 lines"
            done
          done
          touch $out
        '';
      });

      formatter = forAllSystems (pkgs: pkgs.nixfmt);

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
