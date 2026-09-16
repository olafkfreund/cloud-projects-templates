#!/usr/bin/env python3
"""Offline end-to-end checks: synthetic AWS executable, no SDK/network/accounts."""

import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
SCRIPT = SOURCE / "skills/cloud-onboarding/scripts/aws_report.py"
ACCOUNT = "123456789012"
REGION = "eu-west-1"
SENTINEL = "DO_NOT_PERSIST_SYNTHETIC_SECRET"
TAGLIST = [{"Key": key, "Value": SENTINEL} for key in ("owner", "environment", "project")]
BASE = {
    "sts:get-caller-identity": {"Account": ACCOUNT, "Arn": f"arn:aws:iam::{ACCOUNT}:role/audit"},
    "iam:get-account-summary": {
        "SummaryMap": {"AccountMFAEnabled": 1, "AccountAccessKeysPresent": 0}
    },
    "ec2:describe-instances": {
        "Reservations": [
            {
                "Instances": [
                    {
                        "InstanceId": "i-1",
                        "State": {"Name": "running"},
                        "Tags": TAGLIST,
                        "UserData": SENTINEL,
                    }
                ]
            }
        ]
    },
    "ec2:describe-volumes": {
        "Volumes": [{"VolumeId": "vol-1", "Encrypted": True, "Tags": TAGLIST}]
    },
    "ec2:describe-security-groups": {
        "SecurityGroups": [{"GroupId": "sg-1", "Tags": TAGLIST, "IpPermissions": []}]
    },
    "rds:describe-db-instances": {
        "DBInstances": [
            {
                "DBInstanceIdentifier": "db-1",
                "StorageEncrypted": True,
                "PubliclyAccessible": False,
                "BackupRetentionPeriod": 7,
                "MultiAZ": True,
                "TagList": TAGLIST,
                "Endpoint": {"Address": SENTINEL},
            }
        ]
    },
    "s3api:list-buckets": {"Buckets": [{"Name": "test-bucket", "BucketRegion": REGION}]},
    "s3api:get-public-access-block": {
        "PublicAccessBlockConfiguration": {
            k: True
            for k in (
                "BlockPublicAcls",
                "IgnorePublicAcls",
                "BlockPublicPolicy",
                "RestrictPublicBuckets",
            )
        }
    },
    "s3api:get-bucket-versioning": {"Status": "Enabled"},
    "cloudtrail:describe-trails": {
        "trailList": [
            {
                "TrailARN": f"arn:aws:cloudtrail:{REGION}:{ACCOUNT}:trail/audit",
                "HomeRegion": REGION,
                "IsMultiRegionTrail": True,
            }
        ]
    },
    "cloudtrail:get-trail-status": {"IsLogging": True},
}
FAKE = (
    """import json, os, sys, time
from pathlib import Path
args = sys.argv[1:]
if args == ['--version']:
    print('aws-cli/2.36.0 Python/3.14')
    raise SystemExit(0)
with open(os.environ['CALLS'], 'a') as out:
    out.write(json.dumps(args) + '\\n')
key = ':'.join(args[:2])
assert key in """
    + repr(list(BASE))
    + """
assert '--region' in args and '--no-cli-pager' in args and '--no-cli-auto-prompt' in args
assert os.environ['AWS_MAX_ATTEMPTS'] == '2'
assert os.environ['AWS_IGNORE_CONFIGURED_ENDPOINT_URLS'] == 'true'
assert '--no-paginate' not in args
paginated = key in ('ec2:describe-instances', 'ec2:describe-volumes', 'ec2:describe-security-groups', 'rds:describe-db-instances', 's3api:list-buckets')
assert ('--max-items' in args) == paginated
if key == 's3api:list-buckets':
    assert args[args.index('--bucket-region')+1] == args[args.index('--region')+1]
data = json.loads(Path(os.environ['RESPONSES']).read_text())[key]
if isinstance(data, dict) and '_sleep' in data:
    time.sleep(data['_sleep'])
if isinstance(data, dict) and '_error' in data:
    print('An error occurred (' + data['_error'] + ') when calling the operation: DO_NOT_PERSIST_SYNTHETIC_SECRET', file=sys.stderr)
    raise SystemExit(1)
if isinstance(data, dict) and '_raw' in data:
    print(data['_raw'])
else:
    print(json.dumps(data))
"""
)


def command(args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, check=False, **kwargs)


def findings(report, rule):
    return [f for f in report["findings"]["findings"] if f["rule_id"] == rule]


def status(report, rule, expected):
    actual = {f["status"] for f in findings(report, rule)}
    assert actual == {expected}, (rule, expected, actual)


def main():
    with tempfile.TemporaryDirectory(prefix="onboarding test ") as scratch:
        root = Path(scratch)
        binary = root / "bin"
        binary.mkdir()
        fake = binary / "aws"
        fake.write_text(f"#!{sys.executable}\n" + FAKE)
        fake.chmod(0o755)
        count = 0

        def run(data=None, expected=0, extra=(), setup=None, project=None):
            nonlocal count
            count += 1
            project = project or root / f"project {count}"
            project.mkdir(exist_ok=True)
            assert command(["git", "init", "-q", str(project)]).returncode == 0
            if setup:
                setup(project)
            responses, calls = root / f"responses-{count}.json", root / f"calls-{count}.jsonl"
            responses.write_text(json.dumps(BASE if data is None else data))
            env = dict(
                os.environ,
                PATH=str(binary) + os.pathsep + os.environ["PATH"],
                RESPONSES=str(responses),
                CALLS=str(calls),
                PYTHONDONTWRITEBYTECODE="1",
            )
            result = command(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--account-id",
                    ACCOUNT,
                    "--regions",
                    REGION,
                    "--environment",
                    "test",
                    *extra,
                ],
                cwd=project,
                env=env,
                timeout=30,
            )
            assert result.returncode == expected, (
                count,
                result.returncode,
                expected,
                result.stdout,
                result.stderr,
            )
            assert SENTINEL not in result.stdout + result.stderr
            invocations = (
                [json.loads(line) for line in calls.read_text().splitlines()]
                if calls.exists()
                else []
            )
            assert all(a[a.index("--region") + 1] in (REGION, "eu-west-2") for a in invocations)
            reports = (
                sorted((project / "reports/test").glob("*/inventory.json"))
                if (project / "reports/test").exists()
                else []
            )
            if expected == 1:
                assert not reports
                return None, invocations, project
            assert reports
            path = max(reports, key=lambda p: p.stat().st_mtime_ns).parent
            report = {
                name: json.loads((path / f"{name}.json").read_text())
                for name in ("inventory", "findings", "coverage")
            }
            report["markdown"] = (path / "report.md").read_text()
            assert len(list(path.iterdir())) == 4
            for file in path.iterdir():
                assert file.stat().st_mode & 0o777 == 0o600
                assert SENTINEL not in file.read_text()
            for directory in (path, path.parent, path.parent.parent):
                assert directory.stat().st_mode & 0o777 == 0o700
            assert not list(path.parent.glob(".pending-*"))
            assert (
                command(["git", "check-ignore", str(path / "report.md")], cwd=project).returncode
                == 0
            )
            metadata = report["inventory"]["run"]
            assert all(report[n]["run"] == metadata for n in ("findings", "coverage"))
            assert metadata["expected_account"] == metadata["observed_account"] == ACCOUNT
            assert report["coverage"]["complete"] == (expected == 0)
            evidence = {e["id"] for e in report["inventory"]["evidence"]}
            for finding in report["findings"]["findings"]:
                assert set(finding["evidence"]) <= evidence
                assert finding["source"].startswith("https://docs.aws.amazon.com/")
            for state in ("pass", "fail", "unknown", "not_applicable", "manual_review"):
                n = sum(f["status"] == state for f in report["findings"]["findings"])
                assert f"- {state}: {n}\n" in report["markdown"]
            assert len(findings(report, "manual-recovery")) == 1
            return report, invocations, project

        report, calls, project = run()
        for rule in (
            "root-mfa",
            "root-keys",
            "admin-ingress",
            "ebs-encryption",
            "rds-encryption",
            "rds-private",
            "rds-backup",
            "s3-block",
            "s3-versioning",
            "trail-logging",
            "ownership",
        ):
            status(report, rule, "pass")
        previous = {str(p): p.read_bytes() for p in (project / "reports").rglob("*.json")}
        again, _, _ = run(project=project)
        assert [f["id"] for f in report["findings"]["findings"]] == [
            f["id"] for f in again["findings"]["findings"]
        ]
        assert all(Path(p).read_bytes() == value for p, value in previous.items())

        data = copy.deepcopy(BASE)
        data["iam:get-account-summary"]["SummaryMap"] = {
            "AccountMFAEnabled": 0,
            "AccountAccessKeysPresent": 1,
        }
        data["ec2:describe-volumes"]["Volumes"][0]["Encrypted"] = False
        data["ec2:describe-volumes"]["Volumes"][0]["Tags"] = []
        db = data["rds:describe-db-instances"]["DBInstances"][0]
        db.update(StorageEncrypted=False, PubliclyAccessible=True, BackupRetentionPeriod=0)
        data["s3api:get-public-access-block"] = {"_error": "NoSuchPublicAccessBlockConfiguration"}
        data["s3api:get-bucket-versioning"] = {}
        data["cloudtrail:get-trail-status"]["IsLogging"] = False
        failed, _, _ = run(data)
        for rule in (
            "root-mfa",
            "root-keys",
            "ebs-encryption",
            "rds-encryption",
            "rds-private",
            "rds-backup",
            "s3-block",
            "trail-logging",
        ):
            status(failed, rule, "fail")
        status(failed, "s3-versioning", "manual_review")
        assert "fail" in {f["status"] for f in findings(failed, "ownership")}
        for protocol, lo, hi, cidr_key, cidr in [
            ("tcp", 20, 30, "CidrIp", "0.0.0.0/0"),
            ("6", 3000, 4000, "CidrIpv6", "::/0"),
            ("-1", None, None, "CidrIp", "0.0.0.0/0"),
        ]:
            data = copy.deepcopy(BASE)
            data["ec2:describe-security-groups"]["SecurityGroups"][0]["IpPermissions"] = [
                {
                    "IpProtocol": protocol,
                    "FromPort": lo,
                    "ToPort": hi,
                    "IpRanges" if cidr_key == "CidrIp" else "Ipv6Ranges": [
                        {cidr_key: cidr, "Description": SENTINEL}
                    ],
                }
            ]
            report, _, _ = run(data)
            status(report, "admin-ingress", "fail")
        data = copy.deepcopy(BASE)
        data["s3api:get-bucket-versioning"] = {"Status": "Suspended"}
        report, _, _ = run(data)
        status(report, "s3-versioning", "manual_review")

        for ingress in (
            [{"IpProtocol": "tcp"}],
            [{"IpProtocol": "nonsense", "IpRanges": [], "Ipv6Ranges": []}],
            [{"IpProtocol": "tcp", "IpRanges": [{"CidrIp": "invalid"}], "Ipv6Ranges": []}],
        ):
            data = copy.deepcopy(BASE)
            data["ec2:describe-security-groups"]["SecurityGroups"][0]["IpPermissions"] = ingress
            report, _, _ = run(data, expected=2)
            status(report, "admin-ingress", "unknown")

        for replacement in (
            {"_error": "AccessDenied"},
            {"_raw": "{broken"},
            [],
            {"PublicAccessBlockConfiguration": {"BlockPublicAcls": "true"}},
        ):
            data = copy.deepcopy(BASE)
            data["s3api:get-public-access-block"] = replacement
            report, _, _ = run(data, expected=2)
            status(report, "s3-block", "unknown")
        data = copy.deepcopy(BASE)
        del data["rds:describe-db-instances"]["DBInstances"][0]["StorageEncrypted"]
        report, _, _ = run(data, expected=2)
        status(report, "rds-encryption", "unknown")
        data = copy.deepcopy(BASE)
        data["ec2:describe-volumes"] = {"_error": "UnauthorizedOperation"}
        report, _, _ = run(data, expected=2)
        status(report, "ebs-encryption", "unknown")
        data = copy.deepcopy(BASE)
        data["ec2:describe-volumes"]["NextToken"] = SENTINEL
        report, _, _ = run(data, expected=2, extra=("--max-items", "1"))
        status(report, "ebs-encryption", "pass")
        assert any(o["status"] == "truncated" for o in report["coverage"]["operations"])
        data = copy.deepcopy(BASE)
        for operation, key in [
            ("ec2:describe-instances", "Reservations"),
            ("ec2:describe-volumes", "Volumes"),
            ("ec2:describe-security-groups", "SecurityGroups"),
            ("rds:describe-db-instances", "DBInstances"),
            ("s3api:list-buckets", "Buckets"),
            ("cloudtrail:describe-trails", "trailList"),
        ]:
            data[operation] = {key: []}
        report, _, _ = run(data)
        status(report, "ebs-encryption", "not_applicable")
        status(report, "trail-logging", "fail")
        data["ec2:describe-volumes"]["NextToken"] = SENTINEL
        report, _, _ = run(data, expected=2)
        status(report, "ebs-encryption", "unknown")

        for timeout_args in (("--command-timeout", "1"), ("--timeout", "1")):
            data = copy.deepcopy(BASE)
            data["ec2:describe-volumes"] = {"_sleep": 3}
            report, _, _ = run(data, expected=2, extra=timeout_args)
            status(report, "ebs-encryption", "unknown")
            if timeout_args[0] == "--timeout":
                assert any(o["status"] == "not_collected" for o in report["coverage"]["operations"])
        for identity in (
            {"Account": "999999999999", "Arn": f"arn:aws:iam::{ACCOUNT}:role/audit"},
            {"Account": ACCOUNT, "Arn": "arn:aws:broken"},
            {"Account": ACCOUNT, "Arn": f"arn:aws-us-gov:iam::{ACCOUNT}:role/audit"},
            {"_error": "ExpiredToken"},
        ):
            data = copy.deepcopy(BASE)
            data["sts:get-caller-identity"] = identity
            _, calls, _ = run(data, expected=1)
            assert len(calls) == 1
        for extra in (
            ("--environment", "../escape"),
            ("--regions", "us-gov-west-1"),
            ("--timeout", "0"),
        ):
            _, calls, _ = run(expected=1, extra=extra)
            assert not calls

        data = copy.deepcopy(BASE)
        data["cloudtrail:describe-trails"]["trailList"][0]["HomeRegion"] = "eu-west-2"
        data["cloudtrail:describe-trails"]["trailList"][0]["TrailARN"] = (
            f"arn:aws:cloudtrail:eu-west-2:{ACCOUNT}:trail/audit"
        )
        report, calls, _ = run(data, expected=2)
        status(report, "trail-logging", "unknown")
        assert not any(a[:2] == ["cloudtrail", "get-trail-status"] for a in calls)
        data = copy.deepcopy(BASE)
        data["s3api:list-buckets"] = {"Buckets": []}
        report, calls, _ = run(data, extra=("--regions", REGION, "eu-west-2"))
        assert sum(a[:2] == ["cloudtrail", "get-trail-status"] for a in calls) == 1
        assert len([r for r in report["inventory"]["resources"] if r["type"] == "trail"]) == 1

        data = copy.deepcopy(BASE)
        data["rds:describe-db-instances"]["DBInstances"][0]["DBInstanceIdentifier"] = (
            "<script>\n[click](https://invalid.test)"
        )
        report, _, _ = run(data)
        assert "<script>" not in report["markdown"] and "[click]" not in report["markdown"]

        def symlink(project):
            (project / "reports").symlink_to(root, target_is_directory=True)

        _, calls, _ = run(expected=1, setup=symlink)
        assert not calls

        def nested_symlink(project):
            (project / "reports").mkdir()
            (project / "reports/test").symlink_to(root, target_is_directory=True)

        _, calls, _ = run(expected=1, setup=nested_symlink)
        assert not calls

        def old_ignore(project):
            (project / ".gitignore").write_text("local-custom-rule\n")

        _, _, old = run(setup=old_ignore)
        assert (old / ".gitignore").read_text() == "local-custom-rule\n"

        def tracked(project):
            (project / "reports").mkdir()
            (project / "reports/old").write_text("preserve")
            assert command(["git", "add", "reports/old"], cwd=project).returncode == 0

        _, calls, _ = run(expected=1, setup=tracked)
        assert not calls

        # Exercise collision and handled publication failure deterministically.
        sys.dont_write_bytecode = True
        spec = importlib.util.spec_from_file_location("aws_report", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        from types import SimpleNamespace

        collector = SimpleNamespace(operations=[], resources=[], evidence=[], findings=[])
        target = root / "publication"
        target.mkdir()
        (target / "existing").mkdir()
        try:
            module.publish(target, {"id": "existing"}, collector)
            raise AssertionError("collision accepted")
        except ValueError:
            pass
        with patch.object(module, "render", side_effect=OSError("synthetic failure")):
            try:
                module.publish(target, {"id": "new"}, collector)
                raise AssertionError("write failure ignored")
            except OSError:
                pass
        assert sorted(p.name for p in target.iterdir()) == ["existing"]
        print(
            f"PASS: {count} offline report scenarios; identity, rules, coverage, privacy and publication checks"
        )


if __name__ == "__main__":
    main()
