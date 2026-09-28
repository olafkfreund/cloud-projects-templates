# agenix recipients. Add your public key (cat ~/.ssh/id_ed25519.pub) and teammates' keys,
# then run `secret-rekey`. Encrypted files in secrets/ are safe to commit.
let
  recipients = [
    # "ssh-ed25519 AAAA… you@host"
    # secret-user-add inserts recipients above this line
  ];
in
{
  # secret-add inserts entries above this line
}
