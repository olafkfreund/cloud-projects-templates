#!/usr/bin/env bash
# Run only inside a freshly generated disposable project.
# shellcheck disable=SC2016 # Secret variables expand only inside the child shell.
set +x
set -euo pipefail
cd "${DEVENV_ROOT:?run inside the generated devenv shell}"
[[ $DEVENV_ROOT == *' '* ]] || { echo 'test requires a project path containing spaces' >&2; exit 1; }
test "$(secret-list)" = ''
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
age-keygen -o "$scratch/key" 2>/dev/null
pub=$(age-keygen -y "$scratch/key")
sed -i "s|# \"ssh-ed25519 AAAA… you@host\"|\"$pub\"|" secrets.nix
export AGENIX_IDENTITY="$scratch/key"
export SECRET_TEST_VALUE=cloud-template-smoke-value
printf %s "$SECRET_TEST_VALUE" | secret-add T
secret-run --only T -- bash -c 'test "$T" = "$SECRET_TEST_VALUE"'
test "$(secret-list)" = T
secret-rekey
secret-run --only T -- bash -c 'test "$T" = "$SECRET_TEST_VALUE"'

cp secrets.nix "$scratch/secrets.nix"
cp secrets/T.age "$scratch/T.age"
printf '{}\n' >secrets.nix
if printf %s "$SECRET_TEST_VALUE" | secret-add T; then
  echo 'secret-add accepted missing recipients' >&2; exit 1
fi
cmp secrets/T.age "$scratch/T.age"
if secret-rekey; then
  echo 'secret-rekey accepted missing recipients' >&2; exit 1
fi
cmp secrets/T.age "$scratch/T.age"
cp "$scratch/secrets.nix" secrets.nix
secret-run --only T -- bash -c 'test "$T" = "$SECRET_TEST_VALUE"'
if grep -rqF --exclude-dir=.devenv --exclude-dir=.git -- "$SECRET_TEST_VALUE" .; then
  echo 'plaintext test value found in project' >&2; exit 1
fi

# Commit the valid fixture first so an unrelated hook failure cannot mask this check.
git add -A
git -c user.email=ci@ci -c user.name=ci -c commit.gpgsign=false commit -qm 'test: encrypted secret'
printf x >secrets/plain
git add secrets/plain
if git -c user.email=ci@ci -c user.name=ci -c commit.gpgsign=false commit -qm plaintext >"$scratch/commit.log" 2>&1; then
  echo 'plaintext secret was committed' >&2; exit 1
fi
grep -q 'plaintext file(s) in secrets/' "$scratch/commit.log"
echo 'secrets regression checks passed'
