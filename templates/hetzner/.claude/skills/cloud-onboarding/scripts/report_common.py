"""Bounded read-only collection and private v2 reports. Python standard library only."""

import argparse
from collections import Counter
from email.utils import parsedate_to_datetime
import ipaddress
import http.client
import json
import os
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from aws_report import markdown, now, prepare_output

MAX_RESPONSE = 16 * 1024 * 1024
MAX_TOTAL = 200 * 1024 * 1024
MANUAL = (
    "Ownership accountability",
    "Least-privilege IAM",
    "Restore evidence and RTO/RPO",
    "Workload resilience",
    "Cost and budgets",
    "Governance",
)


class Failure(Exception):
    def __init__(self, category, retry_after=0):
        self.category = category
        self.retry_after = retry_after


def positive(value):
    value = int(value)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, "Invalid arguments; use --help for required scope.\n")


def parser(provider):
    p = Parser(
        description=f"Read-only {provider} onboarding; local evidence and coverage reports"
    )
    p.add_argument("--environment", required=True)
    p.add_argument("--max-items", type=positive, default=1000)
    p.add_argument("--command-timeout", type=positive, default=60)
    p.add_argument("--timeout", type=positive, default=900)
    return p


def obj(value):
    return value if isinstance(value, dict) else {}


def items(value):
    return value if isinstance(value, list) else []


def field(data, path):
    for key in path.split("."):
        data = obj(data).get(key)
    return data


def selected(data, paths):
    # Callers specify exact fields, never retain arbitrary API dictionaries.
    return {name: field(data, path) for name, path in paths.items()}


def segment(value):
    if not isinstance(value, (str, int)) or not re.fullmatch(
        r"[A-Za-z0-9_.:-]{1,256}", str(value)
    ):
        raise Failure("malformed")
    if str(value) in (".", ".."):
        raise Failure("malformed")
    return urllib.parse.quote(str(value), safe="")


def valid_id(value):
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= 2048
        and all(c.isprintable() for c in value)
    )


def outcome(value, desired=True):
    return (
        "unknown"
        if type(value) is not bool
        else ("pass" if value == desired else "fail")
    )


def world(value):
    if value in ("*", "Internet", "all"):
        return True
    try:
        return ipaddress.ip_network(value, strict=False).prefixlen == 0
    except (ValueError, TypeError):
        return False


def admin_port(value):
    if value in (None, "*", "all", "", "1-65535", "0-65535"):
        return True
    try:
        parts = str(value).replace(":", "-").split("-")
        low, high = int(parts[0]), int(parts[-1])
        return any(low <= p <= high for p in (22, 3389))
    except ValueError:
        return None


def ingress_status(rules):
    """Normalized rules: protocol, sources, ports, active. Missing data is unknown."""
    if not isinstance(rules, list):
        return "unknown"
    unknown = False
    for r in rules:
        if not isinstance(r, dict):
            unknown = True
            continue
        if r.get("active") is False:
            continue
        if (
            r.get("active") is not True
            or r.get("protocol") is None
            or not isinstance(r.get("sources"), list)
        ):
            unknown = True
            continue
        proto = str(r["protocol"]).lower()
        if proto not in ("tcp", "6", "all", "*", "-1"):
            continue
        if not any(world(s) for s in r["sources"]):
            continue
        ports = r.get("ports")
        if proto in ("all", "*", "-1"):
            return "fail"
        if not isinstance(ports, list):
            unknown = True
            continue
        matches = [admin_port(p) for p in ports] or [True]
        if True in matches:
            return "fail"
        unknown |= None in matches
    return "unknown" if unknown else "pass"


def bounded_process(argv, timeout, env):
    with subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        env=env,
    ) as child:
        buffers = {child.stdout: bytearray(), child.stderr: bytearray()}
        deadline = time.monotonic() + timeout
        try:
            with selectors.DefaultSelector() as poll:
                for pipe in buffers:
                    os.set_blocking(pipe.fileno(), False)
                    poll.register(pipe, selectors.EVENT_READ)
                while poll.get_map():
                    left = deadline - time.monotonic()
                    if left <= 0:
                        raise Failure("timeout")
                    for key, _ in poll.select(min(left, 0.2)):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            poll.unregister(key.fileobj)
                        else:
                            buffers[key.fileobj].extend(chunk)
                            if len(buffers[key.fileobj]) > MAX_RESPONSE:
                                raise Failure("response_limit")
            child.wait(timeout=max(0.001, deadline - time.monotonic()))
            return (
                child.returncode,
                bytes(buffers[child.stdout]),
                bytes(buffers[child.stderr]),
            )
        except BaseException:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
            raise


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Failure("unsafe_redirect")


class Report:
    def __init__(self, provider, args, scope, source, unsupported):
        self.provider, self.args, self.source = provider, args, source
        self.deadline = time.monotonic() + args.timeout
        self.requests = self.bytes = 0
        self.resources, self.evidence, self.operations, self.findings = [], [], [], []
        self.resource_ids = set()
        self.unsupported = list(unsupported)
        self.limitations = []
        self.identity = {"status": "unverified", "method": "", "evidence": []}
        self.scope, self.observed = scope, {}
        self.started = now()
        self.tool_versions = {"python": sys.version.split()[0]}
        self.env = dict(
            os.environ,
            PAGER="cat",
            CLOUDSDK_CORE_DISABLE_PROMPTS="1",
            AZURE_EXTENSION_USE_DYNAMIC_INSTALL="no",
            OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING="True",
        )

    def budget(self):
        left = self.deadline - time.monotonic()
        if left <= 0 or self.requests >= 1000 or self.bytes >= MAX_TOTAL:
            raise Failure("not_collected")
        self.requests += 1
        return min(self.args.command_timeout, left)

    def decode(self, raw):
        self.bytes += len(raw)
        if len(raw) > MAX_RESPONSE or self.bytes > MAX_TOTAL:
            raise Failure("response_limit")
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError, RecursionError):
            raise Failure("malformed") from None

    def cli(self, argv):
        timeout = self.budget()
        try:
            code, out, err = bounded_process(argv, timeout, self.env)
        except (OSError, subprocess.SubprocessError):
            raise Failure("command_failed") from None
        self.bytes += len(err)
        if code:
            self.bytes += len(out)
            if self.bytes > MAX_TOTAL:
                raise Failure("response_limit")
            message = err.decode(errors="replace").lower()
            if any(
                k in message
                for k in (
                    "denied",
                    "forbidden",
                    "notauthorized",
                    "authorizationfailed",
                    "permission",
                )
            ):
                raise Failure("access_denied")
            raise Failure("command_failed")
        return self.decode(out)

    def http(self, origin, path, token):
        if not path.startswith("/") or path.startswith("//") or "#" in path:
            raise Failure("malformed")
        request = urllib.request.Request(
            origin + path,
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        )
        try:
            with urllib.request.build_opener(NoRedirect()).open(
                request, timeout=self.budget()
            ) as response:
                chunks = bytearray()
                while True:
                    if time.monotonic() >= self.deadline:
                        raise Failure("timeout")
                    chunk = response.read1(min(65536, MAX_RESPONSE + 1 - len(chunks)))
                    if not chunk:
                        break
                    chunks.extend(chunk)
                    if len(chunks) > MAX_RESPONSE:
                        raise Failure("response_limit")
                return self.decode(bytes(chunks))
        except urllib.error.HTTPError as e:
            retry_after = 0
            header = e.headers.get("Retry-After", "") if e.headers else ""
            try:
                retry_after = (
                    float(header)
                    if header.isdigit()
                    else max(0, parsedate_to_datetime(header).timestamp() - time.time())
                )
            except (ValueError, TypeError, OverflowError):
                pass
            raise Failure(
                "access_denied"
                if e.code in (401, 403)
                else "rate_limited"
                if e.code == 429
                else "transient"
                if e.code >= 500
                else "unavailable",
                retry_after=retry_after,
            ) from None
        except http.client.HTTPException:
            raise Failure("malformed") from None
        except (urllib.error.URLError, OSError):
            raise Failure("timeout") from None

    def read(self, operation, scope, callback):
        eid = f"e{len(self.evidence) + 1}"
        ev = {
            "id": eid,
            "operation": operation,
            "scope": scope,
            "collected_at": now(),
            "status": "complete",
            "observations": {},
        }
        cov = {
            "evidence": eid,
            "operation": operation,
            "scope": scope,
            "status": "complete",
            "count": None,
            "observed_at": ev["collected_at"],
            "freshness": "unknown",
        }
        self.evidence.append(ev)
        self.operations.append(cov)
        for attempt in range(3):
            try:
                data = callback()
                if data is None:
                    raise Failure("malformed")
                return data, eid
            except Failure as error:
                delay = max(2**attempt, error.retry_after)
                if (
                    error.category in ("timeout", "transient", "rate_limited")
                    and attempt < 2
                    and self.deadline - time.monotonic() > delay
                ):
                    time.sleep(delay)
                    continue
                ev["status"] = cov["status"] = error.category
                return None, eid
            except (KeyError, TypeError, ValueError, IndexError):
                ev["status"] = cov["status"] = "malformed"
                return None, eid

    def mark(self, eid, status):
        index = int(eid[1:]) - 1
        self.evidence[index]["status"] = self.operations[index]["status"] = status

    def observe(self, eid, value):
        self.evidence[int(eid[1:]) - 1]["observations"].setdefault(
            "details", []
        ).append(value)

    def verify(self, data, eid, predicate, observed, method="API scope identity"):
        if not isinstance(data, dict) or not predicate(data):
            raise Failure("identity_failure")
        self.identity = {
            "status": "verified",
            "method": method,
            "evidence": self.identity["evidence"] + [eid],
        }
        self.observed.update(observed(data))
        self.observe(eid, observed(data))

    def listing(
        self, operation, scope, fetch, extract=lambda d: d, continuation=lambda d: None
    ):
        records, token, seen = [], None, set()
        while True:
            data, eid = self.read(operation, scope, lambda: fetch(token))
            if data is None:
                return records, False
            try:
                page = extract(data)
                next_token = continuation(data)
                if not isinstance(page, list) or any(
                    not isinstance(v, dict) for v in page
                ):
                    raise ValueError()
                self.operations[int(eid[1:]) - 1]["count"] = len(page)
                room = self.args.max_items - len(records)
                records.extend((v, eid) for v in page[:room])
                if len(page) > room or (
                    next_token is not None and len(records) >= self.args.max_items
                ):
                    self.mark(eid, "truncated")
                    return records, False
                if next_token is None:
                    if not records:
                        self.finding(
                            "empty-" + operation,
                            scope,
                            "not_applicable",
                            eid,
                            "No resources returned by this completed supported list.",
                            "Review documented visibility limits.",
                            "info",
                        )
                    return records, True
                key = json.dumps(next_token, sort_keys=True)
                if key in seen:
                    raise ValueError()
                seen.add(key)
                token = next_token
            except (KeyError, TypeError, ValueError, Failure):
                self.mark(eid, "malformed")
                return records, False

    def resource(self, native_id, kind, scope, attributes, eid):
        if not valid_id(str(native_id)) or native_id is None:
            self.mark(eid, "malformed")
            return None
        rid = f"{self.provider}/{scope}/{kind}/{native_id}"
        if rid not in self.resource_ids:
            self.resource_ids.add(rid)
            self.resources.append(
                {
                    "id": rid,
                    "type": kind,
                    "scope": scope,
                    "attributes": attributes,
                    "evidence": [eid],
                }
            )
        # Only whitelist-normalized resource attributes become persisted evidence.
        ev = self.evidence[int(eid[1:]) - 1]["observations"]
        ev.setdefault("resources", []).append({"id": rid, "attributes": attributes})
        return rid

    def finding(
        self, rule, resource, status, eid, explanation, action, severity="medium"
    ):
        if resource is None:
            return
        self.findings.append(
            {
                "id": f"{self.provider}.{rule}:{resource}",
                "rule_id": f"{self.provider}.{rule}",
                "rule_version": 1,
                "resource": resource,
                "scope": self.scope,
                "status": status,
                "severity": severity,
                "evidence": [eid] if eid else [],
                "explanation": explanation,
                "action": action,
                "source": self.source,
            }
        )

    def boolean(self, rule, rid, value, eid, desired=True):
        self.finding(
            rule,
            rid,
            outcome(value, desired),
            eid,
            rule.replace("-", " "),
            "Review evidence and propose the required configuration change.",
        )

    def ingress(self, rid, rules, eid):
        self.finding(
            "administrative-ingress",
            rid,
            ingress_status(rules),
            eid,
            "World-open TCP SSH/RDP rule baseline; this does not prove effective reachability.",
            "Restrict administrative sources after reviewing workload access.",
            "high",
        )

    def publish(self, target):
        for name in MANUAL:
            self.finding(
                "manual-" + name.lower().replace(" ", "-"),
                self.provider,
                "manual_review",
                None,
                name,
                "Supply workload requirements and operational evidence.",
                "info",
            )
        for op in self.operations:
            if op["status"] != "complete":
                self.finding(
                    "collection-" + op["operation"],
                    op["scope"],
                    "unknown",
                    op["evidence"],
                    "Collection incomplete: " + op["status"],
                    "Resolve the evidence gap before judging this scope.",
                )
        complete = all(o["status"] == "complete" for o in self.operations)
        run = {
            "id": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            + "-"
            + uuid.uuid4().hex[:12],
            "started_at": self.started,
            "ended_at": now(),
            "provider": self.provider,
            "environment": self.args.environment,
            "collector_version": "1.0.0",
            "ruleset_version": 1,
            "tool_versions": self.tool_versions,
            "requested_scope": self.scope,
            "observed_scope": self.observed,
            "identity": self.identity,
        }
        envelope = {"schema_version": 2, "run": run}
        payloads = {
            "inventory.json": dict(
                envelope, resources=self.resources, evidence=self.evidence
            ),
            "findings.json": dict(envelope, findings=self.findings),
            "coverage.json": dict(
                envelope,
                complete=complete,
                operations=self.operations,
                unsupported=self.unsupported,
                visibility_limitations=self.limitations,
            ),
        }
        lines = [
            f"# {self.provider} onboarding",
            "",
            "Collection: "
            + ("complete for supported checks" if complete else "PARTIAL"),
            "Identity: " + self.identity["status"],
            "Scope: " + markdown(json.dumps(self.scope)),
            "",
            "## Findings",
        ]
        counts = Counter(f["status"] for f in self.findings)
        lines += [
            "",
            "Status totals: "
            + ", ".join(
                f"{key}={counts[key]}"
                for key in (
                    "pass",
                    "fail",
                    "unknown",
                    "not_applicable",
                    "manual_review",
                )
            ),
            "",
        ]
        rank = {
            "fail": 0,
            "unknown": 1,
            "manual_review": 2,
            "pass": 3,
            "not_applicable": 4,
        }
        for f in sorted(self.findings, key=lambda f: (rank[f["status"]], f["id"])):
            lines.append(
                f"- **{f['status']} / {f['severity']}** {markdown(f['resource'])}: {markdown(f['explanation'])} {markdown(f['action'])} Evidence: {', '.join(f['evidence']) or 'manual review'}. [Reference]({f['source']})"
            )
        lines += ["", "## Coverage", "| Operation | Scope | Status |", "|---|---|---|"]
        lines += [
            f"| {markdown(o['operation'])} | {markdown(o['scope'])} | {o['status']} |"
            for o in self.operations
        ]
        lines += ["", "## Limitations"] + [
            "- " + markdown(s) for s in self.unsupported + self.limitations
        ]
        scratch = Path(tempfile.mkdtemp(prefix=".pending-", dir=target))
        dest = target / run["id"]
        try:
            for name, data in payloads.items():
                with open(
                    scratch / name, "x", opener=lambda p, f: os.open(p, f, 0o600)
                ) as handle:
                    json.dump(data, handle, indent=2, sort_keys=True)
                    handle.write("\n")
            with open(
                scratch / "report.md", "x", opener=lambda p, f: os.open(p, f, 0o600)
            ) as handle:
                handle.write("\n".join(lines) + "\n")
            if dest.exists() or dest.is_symlink():
                raise Failure("output_collision")
            scratch.rename(dest)
        finally:
            if scratch.exists():
                shutil.rmtree(scratch)
        print(
            f"Report: {dest} ({'complete for supported checks' if complete else 'partial'})"
        )
        return 0 if complete else 2


def run(provider, p, collect, source, unsupported):
    args = p.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", args.environment):
        p.error("environment")
    for key, value in vars(args).items():
        if key in (
            "account_id",
            "tenant_id",
            "subscription_id",
            "account_uuid",
            "project_id",
            "zone_ids",
            "namespaces",
            "profile",
            "project_label",
            "context",
            "expected_principal",
            "impersonate_service_account",
        ):
            for item in value if isinstance(value, list) else [value]:
                if item is not None and (
                    not valid_id(item)
                    or item.startswith("-")
                    or any(c in item for c in ("\n", "\r", "\x00"))
                ):
                    p.error("scope")
        if isinstance(value, list):
            setattr(args, key, list(dict.fromkeys(value)))
    if hasattr(args, "expected_server"):
        try:
            endpoint = urllib.parse.urlsplit(args.expected_server)
        except ValueError:
            p.error("invalid expected server")
        if (
            endpoint.scheme != "https"
            or not endpoint.hostname
            or endpoint.username
            or endpoint.password
            or endpoint.query
            or endpoint.fragment
        ):
            p.error("expected server must be a credential-free HTTPS endpoint")
    try:
        target = prepare_output(args.environment)
        scope = {
            k: v
            for k, v in vars(args).items()
            if k
            not in (
                "environment",
                "max_items",
                "command_timeout",
                "timeout",
                "include_recommendations",
            )
            and v is not None
        }
        report = Report(provider, args, scope, source, unsupported)
        version_commands = {
            "azure": ["az", "version"],
            "gcp": ["gcloud", "version", "--format=json"],
            "oci": ["oci", "--version"],
            "kubernetes": ["kubectl", "version", "--client", "-o", "json"],
        }
        if provider in version_commands:
            report.tool_versions[provider] = "unknown"
            try:
                code, out, _ = bounded_process(
                    version_commands[provider], min(10, report.budget()), report.env
                )
                version_text = out
                if code == 0 and provider != "oci":
                    try:
                        version_data = json.loads(out)
                        value = (
                            version_data.get("azure-cli")
                            if provider == "azure"
                            else version_data.get("Google Cloud SDK")
                            if provider == "gcp"
                            else obj(version_data.get("clientVersion")).get(
                                "gitVersion"
                            )
                        )
                        version_text = str(value).encode()
                    except (ValueError, AttributeError):
                        version_text = b""
                match = re.search(rb"[0-9]+\.[0-9]+(?:\.[0-9]+)?", version_text)
                if code == 0 and match:
                    report.tool_versions[provider] = match.group().decode()
            except (Failure, OSError, subprocess.SubprocessError):
                pass
        collect(report, args)
        if report.identity["status"] == "unverified":
            raise Failure("identity_failure")
        return report.publish(target)
    except (Failure, OSError, ValueError, TypeError, KeyError, IndexError) as e:
        category = (
            e.category
            if isinstance(e, Failure)
            else "local_preflight_or_output_failure"
        )
        print(
            "Onboarding failed: " + category + "; no raw error retained.",
            file=sys.stderr,
        )
        return 1
