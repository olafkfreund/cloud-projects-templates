#!/usr/bin/env python3
"""Offline multi-provider report checks; no credentials or cloud network."""

import importlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE / "skills/cloud-onboarding/scripts"))
import report_common as c


def check_common():
    assert (
        c.ingress_status(
            [
                {
                    "active": True,
                    "protocol": "tcp",
                    "sources": ["::/0"],
                    "ports": ["20-25"],
                }
            ]
        )
        == "fail"
    )
    assert (
        c.ingress_status(
            [{"active": True, "protocol": "-1", "sources": ["0.0.0.0/0"], "ports": []}]
        )
        == "fail"
    )
    assert c.ingress_status([]) == "pass"
    assert c.ingress_status(None) == "unknown"
    assert (
        c.ingress_status(
            [
                {
                    "active": True,
                    "protocol": "tcp",
                    "sources": ["10.0.0.0/8"],
                    "ports": ["22"],
                }
            ]
        )
        == "pass"
    )
    assert c.selected(
        {"unexpected": {"secret": "DO_NOT_PERSIST"}}, {"safe": "unexpected"}
    ) == {"safe": None}
    assert (
        c.ingress_status(
            [
                {
                    "active": True,
                    "protocol": {"secret": "DO_NOT_PERSIST"},
                    "sources": ["0.0.0.0/0"],
                    "ports": ["22"],
                }
            ]
        )
        == "unknown"
    )
    args = c.parser("test").parse_args(["--environment", "test", "--max-items", "2"])
    report = c.Report("test", args, {}, "https://example.invalid", [])
    pages = {
        None: {"items": [{"id": 1}], "next": "two"},
        "two": {"items": [{"id": 2}], "next": None},
    }
    rows, complete = report.listing(
        "list",
        "scope",
        lambda token: pages[token],
        lambda d: d["items"],
        lambda d: d["next"],
    )
    assert complete and len(rows) == 2
    report = c.Report("test", args, {}, "https://example.invalid", [])
    rows, complete = report.listing(
        "list", "scope", lambda _: [{"id": 1}, {"id": 2}, {"id": 3}]
    )
    assert not complete and report.operations[0]["status"] == "truncated"
    with patch.object(c, "MAX_RESPONSE", 32):
        try:
            c.bounded_process(
                [sys.executable, "-c", 'print("x"*1000)'], 5, dict(os.environ)
            )
        except c.Failure as e:
            assert e.category == "response_limit"
        else:
            raise AssertionError("unbounded output")
    try:
        c.bounded_process(
            [sys.executable, "-c", "import time;time.sleep(10)"], 0.05, dict(os.environ)
        )
    except c.Failure as e:
        assert e.category == "timeout"
    else:
        raise AssertionError("unbounded runtime")
    with tempfile.TemporaryDirectory() as temp:
        old = Path.cwd()
        try:
            os.chdir(temp)
            subprocess.run(["git", "init", "-q"], check=True)
            target = c.prepare_output("test")
            report.identity = {"status": "attested", "method": "test", "evidence": []}
            assert report.publish(target) == 2
            folder = next(target.iterdir())
            for name in ("inventory.json", "findings.json", "coverage.json"):
                data = json.loads((folder / name).read_text())
                assert data["schema_version"] == 2
                assert (folder / name).stat().st_mode & 0o777 == 0o600
        finally:
            os.chdir(old)


def check_failures():
    args = c.parser("test").parse_args(["--environment", "test"])
    r = c.Report("test", args, {}, "https://example.invalid", [])
    with patch.object(c.time, "sleep") as sleep:
        calls = []

        def transient():
            calls.append(1)
            if len(calls) < 3:
                raise c.Failure("rate_limited", retry_after=4)
            return {"ok": True}

        value, eid = r.read("retry", "scope", transient)
        assert value == {"ok": True} and len(calls) == 3
        assert all(call.args == (4,) for call in sleep.call_args_list)
    r = c.Report("test", args, {}, "https://example.invalid", [])
    rows, complete = r.listing(
        "repeat",
        "scope",
        lambda _: {"items": [{"id": 1}], "next": "same"},
        lambda d: d["items"],
        lambda d: d["next"],
    )
    assert not complete and r.operations[-1]["status"] == "malformed"
    r = c.Report("test", args, {}, "https://example.invalid", [])
    r.requests = 1000
    value, eid = r.read("budget", "scope", lambda: r.cli(["never-run"]))
    assert value is None and r.operations[-1]["status"] == "not_collected"
    try:
        c.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.invalid")
    except c.Failure as error:
        assert error.category == "unsafe_redirect"
    else:
        raise AssertionError("redirect allowed")
    with patch.object(c, "MAX_RESPONSE", 4):
        try:
            r.decode(b'{"x":123}')
        except c.Failure as error:
            assert error.category == "response_limit"
        else:
            raise AssertionError("oversize accepted")
    for value in (None, {}, [1], "not-a-list"):
        r = c.Report("test", args, {}, "https://example.invalid", [])
        rows, complete = r.listing("malformed", "scope", lambda _: value)
        assert not complete and r.operations[-1]["status"] != "complete"
    import io
    from contextlib import closing
    from unittest.mock import Mock

    r = c.Report("test", args, {}, "https://example.invalid", [])
    opener = Mock()
    opener.open.return_value = closing(io.BytesIO(b'{"selected":true}'))
    with patch.object(c.urllib.request, "build_opener", return_value=opener):
        assert r.http("https://api.hetzner.cloud", "/v1/servers", "TEST_TOKEN") == {
            "selected": True
        }
    request = opener.open.call_args.args[0]
    assert request.full_url == "https://api.hetzner.cloud/v1/servers"
    assert request.get_header("Authorization") == "Bearer TEST_TOKEN"
    assert r.requests == 1 and r.bytes > 0
    assert "TEST_TOKEN" not in json.dumps(r.evidence)
    print(
        "PASS: retries, request/byte limits, repeated pages, malformed lists and redirects"
    )


def check_providers():
    from types import SimpleNamespace

    base = dict(
        environment="test",
        max_items=10,
        command_timeout=5,
        timeout=30,
        include_recommendations=False,
    )
    cases = {
        "azure": dict(tenant_id="tenant", subscription_id="sub"),
        "gcp": dict(
            project_id="proj",
            expected_principal="reader@example.test",
            impersonate_service_account=None,
        ),
        "kubernetes": dict(
            context="test",
            expected_server="https://cluster.test",
            expected_principal="reader",
            namespaces=["ns"],
        ),
        "cloudflare": dict(account_id="account", zone_ids=["zone"]),
        "hetzner": dict(
            project_label="test",
            acknowledge_project_token=True,
            expected_server_id=None,
        ),
        "digitalocean": dict(account_uuid="uuid", project_id="project"),
    }
    calls = []

    def cli(argv):
        calls.append(argv)
        if argv[:3] == ["az", "cloud", "show"]:
            return {"name": "AzureCloud"}
        if argv[:3] == ["az", "account", "show"]:
            return {"id": "sub", "tenantId": "tenant", "state": "Enabled"}
        if argv[:3] == ["az", "graph", "query"]:
            return {
                "data": [
                    {
                        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/storage",
                        "type": "Microsoft.Storage/storageAccounts",
                    }
                ]
            }
        if argv[:4] == ["az", "storage", "account", "show"]:
            return {
                "enableHttpsTrafficOnly": False,
                "minimumTlsVersion": "TLS1_0",
                "allowBlobPublicAccess": True,
            }
        if argv[:3] == ["gcloud", "config", "list"]:
            return {"core": {"account": "reader@example.test"}}
        if argv[:3] == ["gcloud", "projects", "describe"]:
            return {"projectId": "proj", "projectNumber": "123"}
        if argv[:3] == ["gcloud", "storage", "buckets"]:
            return [
                {
                    "name": "bucket",
                    "public_access_prevention": "enforced",
                    "uniform_bucket_level_access": True,
                    "versioning_enabled": False,
                }
            ]
        if argv[0] == "gcloud":
            return []
        if argv[0] == "kubectl":
            if "config" in argv:
                return {"server": "https://cluster.test"}
            if "whoami" in argv:
                return {"status": {"userInfo": {"username": "reader"}}}
            if "namespace" in argv:
                return "ns-uid"
            if "pods" in argv:
                return {
                    "items": [
                        {
                            "metadata": {"uid": "pod"},
                            "spec": {
                                "hostPID": True,
                                "containers": [
                                    {"securityContext": {"privileged": True}}
                                ],
                            },
                        }
                    ]
                }
            return {"items": []}
        raise AssertionError(argv)

    def http(origin, path, token):
        calls.append((origin, path))
        if origin == "https://api.cloudflare.com":
            if path.endswith("/accounts/account"):
                return {"success": True, "result": {"id": "account"}}
            if path.endswith("/zones/zone"):
                return {
                    "success": True,
                    "result": {"id": "zone", "account": {"id": "account"}},
                }
            if "/dns_records?" in path:
                return {
                    "success": True,
                    "result": [],
                    "result_info": {"page": 1, "total_pages": 1},
                }
            return {
                "success": True,
                "result": {
                    "value": "off"
                    if path.endswith("/ssl")
                    else "1.0"
                    if path.endswith("/min_tls_version")
                    else "off"
                },
            }
        if origin == "https://api.hetzner.cloud":
            kind = path.split("/")[2].split("?")[0]
            return {
                kind: [
                    {"id": 1, "backup_window": None, "protection": {"delete": False}}
                ]
                if kind == "servers"
                else [],
                "meta": {"pagination": {"next_page": None}},
            }
        if path == "/v2/account":
            return {"account": {"uuid": "uuid"}}
        if path == "/v2/projects/project":
            return {"project": {"id": "project"}}
        if "/resources?" in path:
            return {"resources": [{"urn": "do:droplet:1"}], "links": {}}
        if "/firewalls?" in path:
            return {
                "firewalls": [
                    {
                        "id": "fw",
                        "inbound_rules": [
                            {
                                "protocol": "tcp",
                                "ports": "22",
                                "sources": {"addresses": ["0.0.0.0/0"]},
                            }
                        ],
                    }
                ],
                "links": {},
            }
        if path == "/v2/droplets/1":
            return {"droplet": {"features": []}}
        raise AssertionError((origin, path))

    env = {
        "CLOUDFLARE_READ_TOKEN": "SYNTHETIC_SECRET",
        "HCLOUD_TOKEN": "SYNTHETIC_SECRET",
        "DIGITALOCEAN_READ_TOKEN": "SYNTHETIC_SECRET",
    }
    for provider, scope in cases.items():
        module = importlib.import_module(provider + "_report")
        args = SimpleNamespace(**base, **scope)
        report = c.Report(provider, args, scope, module.SOURCE, [])
        with (
            patch.object(report, "cli", side_effect=cli),
            patch.object(report, "http", side_effect=http),
            patch.dict(os.environ, env),
        ):
            module.collect(report, args)
        assert report.identity["status"] in ("verified", "attested"), provider
        assert report.operations and report.findings, provider
        assert "SYNTHETIC_SECRET" not in json.dumps(
            [report.evidence, report.resources, report.findings]
        ), provider
        if provider in ("azure", "cloudflare", "kubernetes", "digitalocean"):
            assert any(f["status"] == "fail" for f in report.findings), provider
        if provider not in ("hetzner",):
            report = c.Report(provider, args, scope, module.SOURCE, [])
            with (
                patch.object(report, "cli", return_value={}),
                patch.object(report, "http", return_value={}),
                patch.dict(os.environ, env),
            ):
                try:
                    module.collect(report, args)
                except c.Failure as error:
                    assert error.category == "identity_failure", provider
                else:
                    raise AssertionError("identity mismatch accepted: " + provider)
    import oci_report

    with tempfile.TemporaryDirectory() as temp:
        config = Path(temp) / "config"
        tenancy = "ocid1.tenancy.oc1..test"
        config.write_text(
            "[audit]\ntenancy=" + tenancy + "\nuser=ocid1.user.oc1..reader\n"
        )
        args = SimpleNamespace(
            **base,
            tenancy_id=tenancy,
            compartment_ids=[tenancy],
            regions=["eu-frankfurt-1"],
            profile="audit",
        )
        report = c.Report("oci", args, {}, oci_report.SOURCE, [])

        def oci(argv):
            if argv[1:4] == ["iam", "tenancy", "get"]:
                return {"id": tenancy}
            if argv[1:4] == ["os", "ns", "get"]:
                return "namespace"
            if argv[1:4] == ["network", "security-list", "list"]:
                return {
                    "data": [
                        {
                            "id": "ocid1.securitylist.oc1..fw",
                            "rules": [
                                {
                                    "protocol": "6",
                                    "source": "0.0.0.0/0",
                                    "tcp-options": {
                                        "destination-port-range": {"min": 22, "max": 22}
                                    },
                                }
                            ],
                        }
                    ]
                }
            return {"data": []}

        with (
            patch.dict(os.environ, {"OCI_CLI_CONFIG_FILE": str(config)}),
            patch.object(report, "cli", side_effect=oci),
        ):
            oci_report.collect(report, args)
        assert any(f["status"] == "fail" for f in report.findings)
    # A denied OCI regional read must not become observed regional coverage.
    with tempfile.TemporaryDirectory() as temp:
        config = Path(temp) / "config"
        tenancy = "ocid1.tenancy.oc1..test"
        config.write_text(
            "[audit]\ntenancy=" + tenancy + "\nuser=ocid1.user.oc1..reader\n"
        )
        args = SimpleNamespace(
            **base,
            tenancy_id=tenancy,
            compartment_ids=[tenancy],
            regions=["eu-frankfurt-1"],
            profile="audit",
        )
        report = c.Report("oci", args, {}, oci_report.SOURCE, [])

        def denied_oci(argv):
            if argv[1:4] == ["iam", "tenancy", "get"]:
                return {"id": tenancy}
            raise c.Failure("access_denied")

        with (
            patch.dict(os.environ, {"OCI_CLI_CONFIG_FILE": str(config)}),
            patch.object(report, "cli", side_effect=denied_oci),
        ):
            oci_report.collect(report, args)
        assert report.observed["regions"] == []
    import hetzner_report

    args = SimpleNamespace(**base, **cases["hetzner"])
    report = c.Report("hetzner", args, {}, hetzner_report.SOURCE, [])

    def malformed_backup(origin, path, token):
        data = http(origin, path, token)
        if "servers" in data:
            data["servers"][0]["backup_window"] = {"secret": "DO_NOT_PERSIST"}
        return data

    with (
        patch.dict(os.environ, env),
        patch.object(report, "http", side_effect=malformed_backup),
    ):
        hetzner_report.collect(report, args)
    assert (
        next(f for f in report.findings if f["rule_id"] == "hetzner.backup_present")[
            "status"
        ]
        == "unknown"
    )
    assert "DO_NOT_PERSIST" not in json.dumps(report.evidence)
    # Every collector emits coverage for denied post-identity reads.
    for provider, scope in cases.items():
        module = importlib.import_module(provider + "_report")
        args = SimpleNamespace(**base, **scope)
        report = c.Report(provider, args, scope, module.SOURCE, [])

        def denied_cli(argv):
            if (
                (argv[0] == "az" and argv[1] in ("cloud", "account"))
                or (argv[0] == "gcloud" and argv[1] in ("config", "projects"))
                or (argv[0] == "kubectl" and ("config" in argv or "whoami" in argv))
            ):
                return cli(argv)
            raise c.Failure("access_denied")

        def denied_http(origin, path, token):
            if path in (
                "/client/v4/accounts/account",
                "/client/v4/zones/zone",
                "/v2/account",
                "/v2/projects/project",
            ):
                return http(origin, path, token)
            raise c.Failure("access_denied")

        with (
            patch.object(report, "cli", side_effect=denied_cli),
            patch.object(report, "http", side_effect=denied_http),
            patch.dict(os.environ, env),
        ):
            try:
                module.collect(report, args)
            except c.Failure as e:
                assert provider == "hetzner" and e.category == "identity_failure"
        assert any(o["status"] == "access_denied" for o in report.operations), provider
        assert not any(f["status"] == "pass" for f in report.findings), provider
    print(
        "PASS: seven provider fixture flows, configuration findings, identity mismatch and secret exclusion"
    )


def check_kube_render():
    import shutil
    from types import SimpleNamespace
    import kubernetes_report as k

    if not shutil.which("kubectl"):
        print("SKIP: kubectl rendering (covered by Nix check)")
        return
    args = SimpleNamespace(
        context="test",
        expected_server="https://cluster.invalid",
        expected_principal="reader",
        namespaces=["test"],
        timeout=30,
        command_timeout=5,
        max_items=10,
        environment="test",
    )
    r = c.Report("kubernetes", args, {}, k.SOURCE, [])
    commands = []

    def fake(argv):
        commands.append(argv)
        if "config" in argv:
            return {"server": args.expected_server}
        if "whoami" in argv:
            return {"status": {"userInfo": {"username": "reader"}}}
        if "namespace" in argv:
            return "uid"
        return {"items": []}

    with patch.object(r, "cli", side_effect=fake):
        k.collect(r, args)
    template = next(
        a
        for command in commands
        for a in command
        if a.startswith('go-template={"items"')
    )
    # Render a locally generated Deployment as the only list item.
    template = template.replace(
        "{{range $i,$x := .items}}{{if $i}},{{end}}", "{{$x := .}}"
    )
    assert template.endswith("{{end}}]}")
    template = template[: -len("{{end}}]}")] + "]}"
    template = template.replace("$x.metadata.uid", "$x.metadata.name")
    result = subprocess.run(
        [
            "kubectl",
            "--kubeconfig=/dev/null",
            "create",
            "deployment",
            "test",
            "--image=example.invalid/test",
            "--dry-run=client",
            "-o",
            template,
        ],
        capture_output=True,
        text=True,
    )
    assert not result.stderr, result.stderr
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert "items" in out
    print("PASS: pinned kubectl renders selected fields without contacting a cluster")


if __name__ == "__main__":
    check_common()
    check_failures()
    check_providers()
    check_kube_render()
    print("PASS: bounded execution, paging, rules and private v2 publication")
