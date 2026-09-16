# Shared by every project: Terraform, lint/security tooling, git hooks and agenix-format secrets.
{ pkgs, ... }:
let
  # Recipients for secrets/<NAME>.age as declared in secrets.nix (agenix format).
  recipients = ''
    recipient_args() {
      local r
      args=()
      while read -r r; do [ -n "$r" ] && args+=(-r "$r"); done < <(
        nix-instantiate --eval --strict --json \
          --argstr secretFile "$DEVENV_ROOT/secrets.nix" --argstr name "$1" \
          -E '{ secretFile, name }: (builtins.getAttr ("secrets/" + name + ".age") (import secretFile)).publicKeys' | jq -r '.[]'
      )
      [ ''${#args[@]} -gt 0 ] || { echo "no recipients for secrets/$1.age in secrets.nix" >&2; exit 1; }
    }
  '';
  identity = "id=\${AGENIX_IDENTITY:-$HOME/.ssh/id_ed25519}";
  secretPkgs = [
    pkgs.age
    pkgs.jq
    pkgs.gnused
  ];
in
{
  packages = with pkgs; [
    terraform
    tflint
    trivy
    terraform-docs
    infracost
    jq
    yq-go
    age
    uv # runs uvx MCP servers
    nodejs # runs npx MCP servers
    terraform-mcp-server
  ];

  git-hooks.hooks = {
    terraform-format.enable = true;
    tflint.enable = true;
    detect-private-keys.enable = true;
    shellcheck.enable = true;
    secrets-age-only = {
      enable = true;
      name = "secrets/ holds only *.age";
      entry = "${pkgs.writeShellScript "secrets-age-only" ''
        echo "plaintext file(s) in secrets/ — encrypt with secret-add: $*" >&2
        exit 1
      ''}";
      files = "^secrets/";
      excludes = [
        "\\.age$"
        "\\.gitkeep$"
      ];
    };
  };

  scripts = {
    secret-add = {
      description = "Encrypt a secret: printf %s VALUE | secret-add NAME (or prompt)";
      packages = secretPkgs;
      exec = ''
        set -euo pipefail
        ${recipients}
        name=''${1:?usage: secret-add NAME   (value from stdin, or prompted)}
        [[ $name =~ ^[A-Z][A-Z0-9_]*$ ]] || { echo "NAME must match ^[A-Z][A-Z0-9_]*$" >&2; exit 1; }
        cd "$DEVENV_ROOT"
        entry="\"secrets/$name.age\".publicKeys = recipients;"
        if ! grep -qF "$entry" secrets.nix; then
          sed -i "/# secret-add inserts entries above this line/i\\  $entry" secrets.nix
          trap '[ -f "secrets/$name.age" ] || sed -i "\|$entry|d" secrets.nix' EXIT # undo on failure
        fi
        recipient_args "$name"
        if [ -t 0 ]; then read -rsp "$name: " value; echo >&2; else value=$(cat); fi
        [ -n "$value" ] || { echo "empty value, nothing written" >&2; exit 1; }
        printf %s "$value" | age "''${args[@]}" -o "secrets/$name.age.tmp"
        mv "secrets/$name.age.tmp" "secrets/$name.age"
        echo "wrote secrets/$name.age" >&2
      '';
    };
    secret-edit = {
      description = "Replace a secret's value (same as secret-add)";
      exec = ''exec secret-add "$@"'';
    };
    secret-list = {
      description = "List secret names (never values)";
      exec = ''
        for f in "$DEVENV_ROOT"/secrets/*.age; do [ -e "$f" ] && basename "$f" .age; done; true
      '';
    };
    secret-rekey = {
      description = "Re-encrypt all secrets for the recipients in secrets.nix";
      packages = secretPkgs;
      exec = ''
        set -euo pipefail
        ${recipients}
        ${identity}
        for f in "$DEVENV_ROOT"/secrets/*.age; do
          [ -e "$f" ] || continue
          name=$(basename "$f" .age)
          recipient_args "$name"
          if age -d -i "$id" "$f" | age "''${args[@]}" -o "$f.tmp"; then
            mv "$f.tmp" "$f"; echo "rekeyed $name" >&2
          else
            rm -f "$f.tmp"; echo "failed to rekey $name" >&2; exit 1
          fi
        done
      '';
    };
    secret-run = {
      description = "Run a command with decrypted secrets in its env: secret-run [--only A,B] -- CMD";
      packages = secretPkgs;
      exec = ''
        set -euo pipefail
        ${identity}
        only=""
        if [ "''${1:-}" = --only ]; then only=",''${2:?--only needs NAMES},"; shift 2; fi
        [ "''${1:-}" = -- ] && shift
        [ $# -gt 0 ] || { echo "usage: secret-run [--only A,B] -- CMD..." >&2; exit 1; }
        found=","
        for f in "$DEVENV_ROOT"/secrets/*.age; do
          [ -e "$f" ] || continue
          name=$(basename "$f" .age)
          [ -z "$only" ] || [[ $only == *",$name,"* ]] || continue
          value=$(age -d -i "$id" "$f")
          export "$name=$value"
          found="$found$name,"
        done
        for n in ''${only//,/ }; do
          [[ $found == *",$n,"* ]] || { echo "secret $n not found in secrets/" >&2; exit 1; }
        done
        exec "$@"
      '';
    };
  };

  # Nix python packages (awscli2, cfn-lint, oci-cli, …) export PYTHONPATH with their
  # python3.14 site-packages. uvx MCP servers run their own python and crash importing
  # those (pydantic_core). The nix CLIs are wrapped and don't need it.
  enterShell = ''
    unset PYTHONPATH
  '';

  enterTest = ''
    [ -z "''${PYTHONPATH:-}" ] || { echo "PYTHONPATH leaks into the shell and breaks uvx MCP servers" >&2; exit 1; }
    terraform version
    tflint --version
    trivy --version
    terraform-docs --version
    infracost --version
    age --version
    terraform-mcp-server --version
  '';
}
