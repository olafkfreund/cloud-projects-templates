#!/usr/bin/env python3
"""Exercise literal recipe arguments and exit codes with disposable fake commands."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="onboarding project ") as temp:
    root = Path(temp)
    shutil.copy(SOURCE / "templates/base/cloud-onboarding.just", root)
    shutil.copy(SOURCE / "templates/base/justfile", root)
    bindir = root / "bin"
    bindir.mkdir()
    for (
        provider
    ) in "aws azure gcp oci kubernetes cloudflare hetzner digitalocean".split():
        command = bindir / ("cloud-onboard-" + provider)
        command.write_text(
            "#!"
            + sys.executable
            + '\nimport json,os,sys\nprint(json.dumps(sys.argv[1:]))\nsys.exit(int(os.environ.get("TEST_EXIT","0")))\n'
        )
        command.chmod(0o700)
    env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ["PATH"])
    literal = [
        "--environment",
        "a b",
        "single'quote",
        'double"quote',
        "$(touch SHOULD_NOT_EXIST)",
        "`touch ALSO_NOT`",
        "$HOME",
        ";exit 9",
    ]
    for (
        provider
    ) in "aws azure gcp oci kubernetes cloudflare hetzner digitalocean".split():
        for code in (0, 1, 2):
            result = subprocess.run(
                ["just", "onboard", provider, *literal],
                cwd=root,
                env=dict(env, TEST_EXIT=str(code)),
                capture_output=True,
                text=True,
            )
            assert result.returncode == code, (result.returncode, result.stderr)
            assert json.loads(result.stdout) == literal, result.stdout
    assert not (root / "SHOULD_NOT_EXIST").exists()
    assert not (root / "ALSO_NOT").exists()
    assert (
        subprocess.run(
            ["just", "onboard", "unknown"], cwd=root, env=env, capture_output=True
        ).returncode
        == 1
    )
    assert (
        subprocess.run(
            ["just", "--list"], cwd=root, env=env, capture_output=True
        ).returncode
        == 0
    )
print("PASS: eight just entry points preserve literal argv and exit codes")
