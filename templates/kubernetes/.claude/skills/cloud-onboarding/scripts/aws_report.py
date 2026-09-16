#!/usr/bin/env python3
"""A bounded AWS baseline. Standard library only; never persists raw API output."""

import argparse
import ipaddress
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"
RULESET = "1"
TAGS = ("owner", "environment", "project")
STATUSES = ("pass", "fail", "unknown", "not_applicable", "manual_review")
DOC = "https://docs.aws.amazon.com/"
RULES = {
    "root-mfa": (
        "high",
        "Root MFA enabled",
        "Review root MFA and centrally managed root access.",
        "IAM/latest/UserGuide/root-user-best-practices.html",
    ),
    "root-keys": (
        "high",
        "No root access keys",
        "Remove root access keys through a separately approved change.",
        "IAM/latest/UserGuide/root-user-best-practices.html",
    ),
    "admin-ingress": (
        "high",
        "No world-open administrative ingress",
        "Review TCP 22/3389 rules, routes and intended administration paths.",
        "vpc/latest/userguide/vpc-security-groups.html",
    ),
    "ebs-encryption": (
        "high",
        "EBS volume encrypted",
        "Plan migration of unencrypted volumes; do not modify them during discovery.",
        "ebs/latest/userguide/ebs-encryption.html",
    ),
    "rds-encryption": (
        "high",
        "RDS storage encrypted",
        "Review an encrypted database migration.",
        "AmazonRDS/latest/UserGuide/Overview.Encryption.html",
    ),
    "rds-private": (
        "high",
        "RDS public accessibility disabled",
        "Review public accessibility and actual network paths.",
        "AmazonRDS/latest/UserGuide/USER_VPC.WorkingWithRDSInstanceinaVPC.html",
    ),
    "rds-backup": (
        "medium",
        "RDS backup retention positive",
        "Confirm retention meets RPO and obtain restore-test evidence.",
        "AmazonRDS/latest/UserGuide/USER_WorkingWithAutomatedBackups.html",
    ),
    "s3-block": (
        "high",
        "All bucket public-access-block flags enabled",
        "Review bucket flags and inherited account/organization controls; this is not a public-access determination.",
        "AmazonS3/latest/userguide/access-control-block-public-access.html",
    ),
    "s3-versioning": (
        "medium",
        "S3 versioning enabled",
        "Review whether versioning and recovery controls fit the workload.",
        "AmazonS3/latest/userguide/Versioning.html",
    ),
    "trail-logging": (
        "high",
        "An observed trail is logging for the region",
        "Review trail coverage, organization trails, event selectors and delivery; selectors/delivery are not assessed.",
        "awscloudtrail/latest/userguide/cloudtrail-concepts.html",
    ),
    "ownership": (
        "low",
        "Required ownership tags present",
        "Assign nonempty owner, environment and project tags under the project convention.",
        "whitepapers/latest/tagging-best-practices/what-are-tags.html",
    ),
}
MANUAL = {
    "accountability": "Confirm accountable owners and operational contacts.",
    "least-privilege": "Review effective IAM permissions, federation and workload identities.",
    "recovery": "Agree RTO/RPO, retention and evidence of successful restoration.",
    "resilience": "Review availability requirements, dependencies and RDS Multi-AZ suitability.",
    "cost": "Review available native cost recommendations, budgets and workload demand.",
    "governance": "Review organization controls, policy exceptions and unassessed services.",
}
UNSUPPORTED = [
    "Services outside IAM root summary, EC2 instances/volumes/security groups, RDS DB instances, general-purpose S3 and CloudTrail trails",
    "Other accounts/regions, noncommercial partitions, S3 directory buckets and objects, RDS cluster-level controls",
    "Effective IAM/network access, inherited S3 controls, CloudTrail event selectors/delivery, restore tests and compliance certification",
    "Inventory may omit resources invisible to the caller; collection completeness is not account completeness",
]


def now():
    return datetime.now(timezone.utc).isoformat()


def typed(value, kind):
    return value if type(value) is kind else None


def text_id(value):
    return value if isinstance(value, str) and value and len(value) <= 2048 else None


def mapping(value):
    return value if isinstance(value, dict) else {}


def tags(value):
    if not isinstance(value, list) or any(
        not isinstance(t, dict)
        or not isinstance(t.get("Key"), str)
        or not isinstance(t.get("Value"), str)
        for t in value
    ):
        return None
    return {key: any(t["Key"] == key and bool(t["Value"].strip()) for t in value) for key in TAGS}


def pick(obj, fields):
    return {key: typed(obj.get(key), kind) for key, kind in fields.items()}


def execute(args, timeout, env=None):
    # A separate group lets deadlines also terminate credential helper children.
    with subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        start_new_session=True,
    ) as child:
        try:
            out, err = child.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.communicate()
            raise
    return child.returncode, out, err


def git(*args):
    code, out, _ = execute(["git", *args], 15)
    if code:
        raise ValueError("Git project preflight failed")
    return out.decode().strip()


def private_dir(path):
    if path.is_symlink():
        raise ValueError("Report directory must not be a symlink")
    path.mkdir(mode=0o700, exist_ok=True)
    path.chmod(0o700)


def prepare_output(environment):
    root = Path(git("rev-parse", "--show-toplevel"))
    if root.resolve() != Path.cwd().resolve():
        raise ValueError("Run from the Git project root")
    if git("ls-files", "--", "reports"):
        raise ValueError(
            "Reports path is already tracked; remove it from tracking before collection"
        )
    reports = root / "reports"
    target = reports / environment
    # Validate before creating output or touching the ignore file.
    for path in (reports, target):
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValueError("Unsafe report directory")
    exclude = Path(git("rev-parse", "--git-path", "info/exclude"))
    if any(p.is_symlink() for p in (exclude, *exclude.parents)):
        raise ValueError("Git exclude path must not be a symlink")
    exclude.parent.mkdir(parents=True, exist_ok=True)
    current = exclude.read_text() if exclude.exists() else ""
    if "/reports/" not in current.splitlines():
        with exclude.open("a") as handle:
            handle.write("\n/reports/\n")
    if not git("check-ignore", "--", "reports/.cloud-onboarding-probe"):
        raise ValueError("Reports are not Git-ignored")
    private_dir(reports)
    private_dir(target)
    return target


class Collector:
    def __init__(self, args):
        self.args = args
        self.deadline = time.monotonic() + args.timeout
        self.env = dict(
            os.environ,
            AWS_PAGER="",
            AWS_CLI_AUTO_PROMPT="off",
            AWS_MAX_ATTEMPTS="2",
            AWS_RETRY_MODE="standard",
            AWS_IGNORE_CONFIGURED_ENDPOINT_URLS="true",
        )
        self.evidence = []
        self.operations = []
        self.resources = []
        self.findings = []
        self.trails = {}

    def call(self, service, operation, region, extra=(), paginated=False, absent=None):
        scope = f"{self.args.account_id}/{region}"
        eid = f"e{len(self.evidence) + 1}"
        ev = {
            "id": eid,
            "operation": f"{service}:{operation}",
            "scope": scope,
            "collected_at": now(),
            "status": "complete",
            "observations": {},
        }
        cov = {
            "evidence": eid,
            "operation": ev["operation"],
            "scope": scope,
            "status": "complete",
            "count": None,
        }
        self.evidence.append(ev)
        self.operations.append(cov)
        data = None
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            cov["status"] = "not_collected"
        else:
            command = [
                "aws",
                service,
                operation,
                "--region",
                region,
                "--output",
                "json",
                "--no-cli-pager",
                "--no-cli-auto-prompt",
                *extra,
            ]
            if self.args.profile:
                command += ["--profile", self.args.profile]
            if paginated:
                # API minimum page sizes differ; CLI max-items bounds the result.
                command += ["--max-items", str(self.args.max_items), "--page-size", "100"]
            try:
                code, out, err = execute(
                    command, min(remaining, self.args.command_timeout), self.env
                )
                if code:
                    error = err.decode(errors="replace")
                    # Recognize only the AWS error code, never persist its message.
                    match = re.search(r"An error occurred \(([^)]+)\)", error)
                    error_code = match.group(1) if match else ""
                    if absent and error_code == absent:
                        cov["status"], data = "absent", {}
                    elif error_code in (
                        "AccessDenied",
                        "AccessDeniedException",
                        "UnauthorizedOperation",
                        "Forbidden",
                    ):
                        cov["status"] = "access_denied"
                    elif error_code in (
                        "OptInRequired",
                        "SubscriptionRequiredException",
                        "InvalidClientTokenId",
                        "ExpiredToken",
                        "ExpiredTokenException",
                    ):
                        cov["status"] = "unavailable"
                    else:
                        cov["status"] = "command_failed"
                else:
                    data = json.loads(out)
                    if not isinstance(data, dict):
                        raise ValueError("Invalid response")
                    if any(
                        data.get(k)
                        for k in (
                            "NextToken",
                            "NextMarker",
                            "Marker",
                            "ContinuationToken",
                            "NextContinuationToken",
                            "IsTruncated",
                        )
                    ):
                        cov["status"] = "truncated"
            except subprocess.TimeoutExpired:
                cov["status"] = "timeout"
            except (ValueError, UnicodeError):
                data, cov["status"] = None, "malformed"
            except OSError:
                cov["status"] = "command_failed"
        ev["status"] = cov["status"]
        return data, ev, cov

    def malformed(self, ev, cov):
        if cov["status"] in ("complete", "absent"):
            ev["status"] = cov["status"] = "malformed"

    def listing(self, service, operation, region, key, extra=(), paginated=True):
        data, ev, cov = self.call(service, operation, region, extra, paginated)
        values = data.get(key) if isinstance(data, dict) else None
        if not isinstance(values, list):
            self.malformed(ev, cov)
            return [], ev, cov
        if any(not isinstance(v, dict) for v in values):
            self.malformed(ev, cov)
        items = [v for v in values if isinstance(v, dict)]
        cov["count"] = len(items)
        return items, ev, cov

    def resource(self, kind, native, region, attrs, ev, cov):
        if not text_id(native):
            self.malformed(ev, cov)
            return None
        rid = f"aws/{self.args.account_id}/{region}/{kind}/{native}"
        obj = {
            "id": rid,
            "type": kind,
            "scope": f"{self.args.account_id}/{region}",
            "attributes": attrs,
            "evidence": [ev["id"]],
        }
        self.resources.append(obj)
        ev["observations"][rid] = attrs
        return obj

    def finding(self, rule, obj, result, evidence, detail=None):
        severity, title, action, source = RULES[rule]
        status = (
            "unknown"
            if result is None
            else "pass"
            if result is True
            else "fail"
            if result is False
            else result
        )
        self.findings.append(
            {
                "id": f"{rule}:{obj['id']}",
                "rule_id": rule,
                "rule_version": RULESET,
                "resource": obj["id"],
                "scope": obj["scope"],
                "status": status,
                "severity": severity,
                "evidence": list(dict.fromkeys(evidence)),
                "explanation": detail or f"Check: {title}",
                "action": action,
                "source": DOC + source,
            }
        )

    def check(self, rule, obj, value, ev, cov):
        self.finding(rule, obj, value, [ev["id"]])
        if value is None:
            self.malformed(ev, cov)

    def empty(self, rules, kind, region, ev, cov):
        obj = {
            "id": f"aws/{self.args.account_id}/{region}/{kind}",
            "scope": f"{self.args.account_id}/{region}",
        }
        status = "not_applicable" if cov["status"] == "complete" else "unknown"
        for rule in rules:
            self.finding(
                rule,
                obj,
                status,
                [ev["id"]],
                "No applicable resources observed"
                if status == "not_applicable"
                else "Resource enumeration incomplete; absence cannot be established",
            )

    def ownership(self, obj, ev, cov):
        values = obj["attributes"]["tags"]
        self.check("ownership", obj, None if values is None else all(values.values()), ev, cov)

    def collect(self):
        region = self.args.regions[0]
        data, ev, cov = self.call(
            "sts", "get-caller-identity", region, ("--query", "{Account:Account,Arn:Arn}")
        )
        if cov["status"] != "complete" or mapping(data).get("Account") != self.args.account_id:
            raise ValueError("Identity failed or account mismatch; inventory not collected")
        arn = mapping(data).get("Arn")
        if not isinstance(arn, str) or not re.fullmatch(
            r"arn:aws:(?:iam|sts)::" + self.args.account_id + r":[^\r\n]+", arn
        ):
            raise ValueError("Invalid identity or unsupported AWS partition")
        ev["observations"] = {"account": self.args.account_id, "partition": "aws"}
        data, ev, cov = self.call(
            "iam",
            "get-account-summary",
            region,
            (
                "--query",
                "{SummaryMap:{AccountMFAEnabled:SummaryMap.AccountMFAEnabled,AccountAccessKeysPresent:SummaryMap.AccountAccessKeysPresent}}",
            ),
        )
        summary = mapping(mapping(data).get("SummaryMap"))
        attrs = pick(summary, {"AccountMFAEnabled": int, "AccountAccessKeysPresent": int})
        obj = self.resource("account", self.args.account_id, "global", attrs, ev, cov)
        mfa, keys = attrs.values()
        self.check("root-mfa", obj, None if mfa not in (0, 1) else mfa == 1, ev, cov)
        self.check("root-keys", obj, None if keys is None or keys < 0 else keys == 0, ev, cov)
        for region in self.args.regions:
            self.ec2(region)
            self.rds(region)
            self.s3(region)
            self.cloudtrail(region)
        for key, explanation in MANUAL.items():
            self.findings.append(
                {
                    "id": f"manual-{key}:{self.args.account_id}",
                    "rule_id": f"manual-{key}",
                    "rule_version": RULESET,
                    "resource": self.args.account_id,
                    "scope": self.args.account_id,
                    "status": "manual_review",
                    "severity": "info",
                    "evidence": [],
                    "explanation": explanation,
                    "action": explanation,
                    "source": DOC + "wellarchitected/latest/framework/the-review-process.html",
                }
            )

    def ec2(self, region):
        reservations, ev, cov = self.listing("ec2", "describe-instances", region, "Reservations")
        instances = []
        for reservation in reservations:
            items = reservation.get("Instances")
            if not isinstance(items, list) or any(not isinstance(i, dict) for i in items):
                self.malformed(ev, cov)
            else:
                instances.extend(items)
        cov["count"] = len(instances)
        for item in instances:
            attrs = pick(item, {"VpcId": str, "SubnetId": str})
            attrs.update(
                state=typed(mapping(item.get("State")).get("Name"), str),
                zone=typed(mapping(item.get("Placement")).get("AvailabilityZone"), str),
                tags=tags(item.get("Tags")),
            )
            attrs["groups"] = id_list(item.get("SecurityGroups"), "GroupId")
            devices = item.get("BlockDeviceMappings")
            attrs["volumes"] = (
                [
                    v
                    for d in devices
                    if isinstance(d, dict) and (v := text_id(mapping(d.get("Ebs")).get("VolumeId")))
                ]
                if isinstance(devices, list)
                else None
            )
            obj = self.resource("instance", item.get("InstanceId"), region, attrs, ev, cov)
            if obj:
                self.ownership(obj, ev, cov)
        if not instances:
            self.empty(["ownership"], "instance", region, ev, cov)
        for operation, key, kind, rules in (
            ("describe-volumes", "Volumes", "volume", ["ebs-encryption", "ownership"]),
            (
                "describe-security-groups",
                "SecurityGroups",
                "security-group",
                ["admin-ingress", "ownership"],
            ),
        ):
            items, ev, cov = self.listing("ec2", operation, region, key)
            for item in items:
                if kind == "volume":
                    attrs = pick(item, {"Encrypted": bool, "AvailabilityZone": str, "State": str})
                    attrs["instances"] = id_list(item.get("Attachments"), "InstanceId")
                    native = item.get("VolumeId")
                else:
                    attrs = pick(item, {"VpcId": str})
                    attrs["ingress"], ingress_ok = ingress(item.get("IpPermissions"))
                    native = item.get("GroupId")
                attrs["tags"] = tags(item.get("Tags"))
                obj = self.resource(kind, native, region, attrs, ev, cov)
                if obj:
                    self.ownership(obj, ev, cov)
                    self.check(
                        rules[0],
                        obj,
                        attrs["Encrypted"] if kind == "volume" else ingress_ok,
                        ev,
                        cov,
                    )
            if not items:
                self.empty(rules, kind, region, ev, cov)

    def rds(self, region):
        items, ev, cov = self.listing("rds", "describe-db-instances", region, "DBInstances")
        for item in items:
            attrs = pick(
                item,
                {
                    "Engine": str,
                    "StorageEncrypted": bool,
                    "PubliclyAccessible": bool,
                    "BackupRetentionPeriod": int,
                    "MultiAZ": bool,
                },
            )
            attrs["VpcId"] = typed(mapping(item.get("DBSubnetGroup")).get("VpcId"), str)
            attrs["groups"] = id_list(item.get("VpcSecurityGroups"), "VpcSecurityGroupId")
            attrs["tags"] = tags(item.get("TagList"))
            obj = self.resource(
                "database", item.get("DBInstanceIdentifier"), region, attrs, ev, cov
            )
            if obj:
                self.check("rds-encryption", obj, attrs["StorageEncrypted"], ev, cov)
                public, retention = attrs["PubliclyAccessible"], attrs["BackupRetentionPeriod"]
                self.check("rds-private", obj, None if public is None else not public, ev, cov)
                self.check(
                    "rds-backup",
                    obj,
                    None if retention is None or retention < 0 else retention > 0,
                    ev,
                    cov,
                )
                self.ownership(obj, ev, cov)
        if not items:
            self.empty(
                ["rds-encryption", "rds-private", "rds-backup", "ownership"],
                "database",
                region,
                ev,
                cov,
            )

    def s3(self, region):
        items, ev, cov = self.listing(
            "s3api", "list-buckets", region, "Buckets", ("--bucket-region", region)
        )
        for item in items:
            name = item.get("Name")
            if (
                not isinstance(name, str)
                or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", name)
                or item.get("BucketRegion", region) != region
            ):
                self.malformed(ev, cov)
                continue
            obj = self.resource("bucket", name, region, {"region": region}, ev, cov)
            data, bev, bcov = self.call(
                "s3api",
                "get-public-access-block",
                region,
                ("--bucket", name, "--expected-bucket-owner", self.args.account_id),
                absent="NoSuchPublicAccessBlockConfiguration",
            )
            flags = pick(
                mapping(mapping(data).get("PublicAccessBlockConfiguration")),
                {
                    "BlockPublicAcls": bool,
                    "IgnorePublicAcls": bool,
                    "BlockPublicPolicy": bool,
                    "RestrictPublicBuckets": bool,
                },
            )
            bev["observations"] = {obj["id"]: flags}
            value = (
                False
                if bcov["status"] == "absent"
                else None
                if any(v is None for v in flags.values())
                else all(flags.values())
            )
            self.check("s3-block", obj, value, bev, bcov)
            data, vev, vcov = self.call(
                "s3api",
                "get-bucket-versioning",
                region,
                ("--bucket", name, "--expected-bucket-owner", self.args.account_id),
            )
            status = mapping(data).get("Status")
            vev["observations"] = {
                obj["id"]: {"versioning": status if status in ("Enabled", "Suspended") else None}
            }
            value = None
            if vcov["status"] == "complete":
                if status == "Enabled":
                    value = True
                elif status == "Suspended" or "Status" not in data:
                    value = "manual_review"
            self.check("s3-versioning", obj, value, vev, vcov)
            obj["evidence"] += [bev["id"], vev["id"]]
        if not items:
            self.empty(["s3-block", "s3-versioning"], "bucket", region, ev, cov)

    def cloudtrail(self, region):
        items, ev, cov = self.listing(
            "cloudtrail",
            "describe-trails",
            region,
            "trailList",
            ("--include-shadow-trails",),
            paginated=False,
        )
        statuses, evidence = [], [ev["id"]]
        for item in items:
            arn, home = item.get("TrailARN"), item.get("HomeRegion")
            multi = typed(item.get("IsMultiRegionTrail"), bool)
            if (
                not isinstance(arn, str)
                or not re.fullmatch(r"arn:aws:cloudtrail:[a-z0-9-]+:[0-9]{12}:trail/.+", arn)
                or not isinstance(home, str)
                or multi is None
            ):
                self.malformed(ev, cov)
                statuses.append(None)
                continue
            if arn not in self.trails:
                obj = self.resource(
                    "trail", arn, home, {"home_region": home, "multi_region": multi}, ev, cov
                )
                if home in self.args.regions:
                    data, tev, tcov = self.call(
                        "cloudtrail", "get-trail-status", home, ("--name", arn)
                    )
                    logging = typed(mapping(data).get("IsLogging"), bool)
                    if logging is None:
                        self.malformed(tev, tcov)
                    tev["observations"] = {obj["id"]: {"logging": logging}}
                else:
                    logging = None
                    tev = {
                        "id": f"e{len(self.evidence) + 1}",
                        "operation": "cloudtrail:get-trail-status",
                        "scope": f"{self.args.account_id}/{home}",
                        "collected_at": now(),
                        "status": "not_collected",
                        "observations": {},
                    }
                    self.evidence.append(tev)
                    self.operations.append(
                        {
                            "evidence": tev["id"],
                            "operation": tev["operation"],
                            "scope": tev["scope"],
                            "status": "not_collected",
                            "count": None,
                        }
                    )
                obj["evidence"].append(tev["id"])
                self.trails[arn] = (logging, tev["id"])
            logging, eid = self.trails[arn]
            evidence.append(eid)
            statuses.append(logging if home == region or multi else False)
        result = (
            True
            if True in statuses
            else None
            if None in statuses or cov["status"] != "complete"
            else False
        )
        obj = {
            "id": f"aws/{self.args.account_id}/{region}/trail-coverage",
            "scope": f"{self.args.account_id}/{region}",
        }
        self.finding("trail-logging", obj, result, evidence)


def id_list(values, key):
    if not isinstance(values, list) or any(
        not isinstance(v, dict) or not text_id(v.get(key)) for v in values
    ):
        return None
    return [v[key] for v in values]


def ingress(values):
    if not isinstance(values, list):
        return None, None
    selected, unknown, exposed = [], False, False
    for rule in values:
        if not isinstance(rule, dict):
            unknown = True
            continue
        protocol = typed(rule.get("IpProtocol"), str)
        low, high = typed(rule.get("FromPort"), int), typed(rule.get("ToPort"), int)
        ranges = []
        for field, key in (("IpRanges", "CidrIp"), ("Ipv6Ranges", "CidrIpv6")):
            entries = rule.get(field)
            if not isinstance(entries, list):
                unknown = True
                continue
            for entry in entries:
                cidr = typed(mapping(entry).get(key), str)
                if cidr is None:
                    unknown = True
                else:
                    try:
                        network = ipaddress.ip_network(cidr, strict=False)
                        if network.version != (4 if key == "CidrIp" else 6):
                            raise ValueError("CIDR family mismatch")
                        ranges.append(str(network))
                    except ValueError:
                        unknown = True
        selected.append({"protocol": protocol, "from_port": low, "to_port": high, "cidrs": ranges})
        if protocol not in ("-1", "tcp", "udp", "icmp", "icmpv6") and not (
            isinstance(protocol, str) and protocol.isdecimal() and 0 <= int(protocol) <= 255
        ):
            unknown = True
        world = any(cidr in ("0.0.0.0/0", "::/0") for cidr in ranges)
        if world and protocol == "-1":
            exposed = True
        elif world and protocol in ("tcp", "6"):
            if low is None or high is None or not (0 <= low <= high <= 65535):
                unknown = True
            elif any(low <= port <= high for port in (22, 3389)):
                exposed = True
    return selected, False if exposed else None if unknown else True


def markdown(value):
    # Entity-encode markup punctuation too: identifiers cannot inject links/headings.
    return "".join(
        c if c.isalnum() or c in " /:.-" else f"&#{ord(c)};" for c in str(value) if c.isprintable()
    )


def render(run, findings, operations, complete):
    counts = Counter(f["status"] for f in findings)
    lines = [
        "# AWS onboarding",
        "",
        f"Account: {run['observed_account']}",
        f"Regions: {', '.join(run['regions'])}",
        f"Environment: {markdown(run['environment'])}",
        f"Collected: {run['started_at']} to {run['ended_at']}",
        "",
        "Collection: "
        + ("complete for supported checks" if complete else "PARTIAL — review coverage.json"),
        "",
        "## Status counts",
        "",
    ]
    lines += [f"- {status}: {counts[status]}" for status in STATUSES]
    lines += ["", "## Findings and next actions", ""]
    rank = {"fail": 0, "unknown": 1, "manual_review": 2, "pass": 3, "not_applicable": 4}
    severity = {"high": 0, "medium": 1, "low": 2, "info": 3}
    for f in sorted(findings, key=lambda f: (rank[f["status"]], severity[f["severity"]], f["id"])):
        lines += [
            (
                f"- **{f['status']} / {f['severity']}** {markdown(f['resource'])}: {markdown(f['explanation'])} "
                f"{markdown(f['action'])} Evidence: {', '.join(f['evidence']) or 'manual review'}. "
                f"[Reference]({f['source']})"
            )
        ]
    lines += ["", "## Coverage gaps", ""]
    gaps = [op for op in operations if op["status"] not in ("complete", "absent")]
    lines += [
        f"- {markdown(op['operation'])} ({markdown(op['scope'])}): {op['status']} ({op['evidence']})"
        for op in gaps
    ] or ["- No collection errors for supported operations."]
    lines += ["", "## Limitations", ""] + [f"- {item}" for item in UNSUPPORTED]
    lines += [
        "- Environment is a report label, not a resource filter. Configured backups do not prove recoverability.",
        "- Local reports contain infrastructure metadata. Do not publish automatically.",
    ]
    return "\n".join(lines) + "\n"


def publish(target, run, collector):
    complete = all(op["status"] in ("complete", "absent") for op in collector.operations)
    destination = target / run["id"]
    if destination.exists() or destination.is_symlink():
        raise ValueError("Report run already exists")
    envelope = {"schema_version": 1, "run": run}
    payloads = {
        "inventory.json": dict(
            envelope, resources=collector.resources, evidence=collector.evidence
        ),
        "findings.json": dict(envelope, findings=collector.findings),
        "coverage.json": dict(
            envelope, complete=complete, operations=collector.operations, unsupported=UNSUPPORTED
        ),
    }
    scratch = Path(tempfile.mkdtemp(prefix=".pending-", dir=target))
    try:
        for name, payload in payloads.items():
            path = scratch / name
            with open(path, "x", opener=lambda p, flags: os.open(p, flags, 0o600)) as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
        with open(
            scratch / "report.md", "x", opener=lambda p, flags: os.open(p, flags, 0o600)
        ) as handle:
            handle.write(render(run, collector.findings, collector.operations, complete))
        if destination.exists() or destination.is_symlink():
            raise ValueError("Report run already exists")
        scratch.rename(destination)
    finally:
        if scratch.exists():
            shutil.rmtree(scratch)
    print(f"Report: {destination} ({'complete for supported checks' if complete else 'partial'})")
    return 0 if complete else 2


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's usual error exit is 2; 2 here means a written partial report.
        self.print_usage(sys.stderr)
        self.exit(1, "Invalid arguments; use --help for the command contract.\n")


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main():
    parser = Parser(description=__doc__)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--regions", nargs="+", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--profile")
    parser.add_argument("--max-items", type=positive, default=1000)
    parser.add_argument("--command-timeout", type=positive, default=60)
    parser.add_argument("--timeout", type=positive, default=900)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]{12}", args.account_id) or not re.fullmatch(
        r"[a-z0-9][a-z0-9_-]{0,63}", args.environment
    ):
        parser.error("invalid scope")
    if any(
        not re.fullmatch(r"(?:af|ap|ca|eu|il|me|mx|sa|us)-(?:[a-z]+-)?[a-z]+-[0-9]+", r)
        or r.startswith(("us-gov-", "us-iso"))
        for r in args.regions
    ):
        parser.error("invalid or noncommercial region")
    args.regions = list(dict.fromkeys(args.regions))
    try:
        target = prepare_output(args.environment)
        collector = Collector(args)
        run = {
            "id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12],
            "started_at": now(),
            "provider": "aws",
            "expected_account": args.account_id,
            "observed_account": args.account_id,
            "regions": args.regions,
            "environment": args.environment,
            "collector_version": VERSION,
            "ruleset_version": RULESET,
            "cli_version": "unknown",
        }
        collector.collect()
        remaining = collector.deadline - time.monotonic()
        if remaining > 0:
            try:
                code, out, _ = execute(
                    ["aws", "--version"], min(remaining, args.command_timeout), collector.env
                )
                match = re.search(rb"aws-cli/[0-9.]+", out)
                if code == 0 and match:
                    run["cli_version"] = match.group().decode()
            except (OSError, subprocess.TimeoutExpired):
                pass
        run["ended_at"] = now()
        return publish(target, run, collector)
    except ValueError as error:
        print(str(error), file=sys.stderr)
    except (OSError, subprocess.SubprocessError):
        print(
            "Collection or local report operation failed; no raw error output retained.",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
