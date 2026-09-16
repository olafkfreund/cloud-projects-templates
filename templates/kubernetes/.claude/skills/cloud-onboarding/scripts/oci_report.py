"""OCI onboarding for explicitly selected compartments and regions."""

import configparser
import os
import re
import sys
from pathlib import Path
from report_common import Failure, parser, run, obj, items, selected

SOURCE = "https://docs.oracle.com/en-us/iaas/Content/Search/Concepts/queryoverview.htm"


def collect(r, a):
    ids = [a.tenancy_id, *a.compartment_ids]
    if any(not re.fullmatch(r"ocid1\.[a-z]+\.oc1\.[A-Za-z0-9_.-]+", x) for x in ids):
        raise Failure("invalid_scope")
    if any(not re.fullmatch(r"[a-z]+-[a-z]+-[0-9]+", x) for x in a.regions):
        raise Failure("invalid_scope")
    if r.env.get("OCI_CLI_ENDPOINT") or r.env.get("OCI_CLI_REGION") not in (
        None,
        "",
        *a.regions,
    ):
        raise Failure("unsafe_endpoint")
    config = configparser.ConfigParser(interpolation=None)
    config.read(
        Path(os.environ.get("OCI_CLI_CONFIG_FILE", "~/.oci/config")).expanduser()
    )
    profile = config[a.profile] if a.profile in config else {}
    if profile.get("tenancy") != a.tenancy_id or not profile.get("user"):
        raise Failure("identity_failure")
    if profile.get("endpoint"):
        raise Failure("unsafe_endpoint")

    def cli(region, *args):
        return r.cli(
            [
                "oci",
                *args,
                "--profile",
                a.profile,
                "--region",
                region,
                "--output",
                "json",
            ]
        )

    region = a.regions[0]
    data, eid = r.read(
        "iam.tenancy.get",
        a.tenancy_id,
        lambda: cli(
            region,
            "iam",
            "tenancy",
            "get",
            "--tenancy-id",
            a.tenancy_id,
            "--query",
            "data.{id:id}",
        ),
    )
    r.verify(
        data,
        eid,
        lambda d: d.get("id") == a.tenancy_id,
        lambda d: {"tenancy_id": d["id"], "principal": profile["user"]},
    )
    for compartment in a.compartment_ids:
        current, seen = compartment, set()
        while current != a.tenancy_id:
            if current in seen or len(seen) >= 100:
                raise Failure("identity_failure")
            seen.add(current)
            data, eid = r.read(
                "iam.compartment.get",
                current,
                lambda: cli(
                    region,
                    "iam",
                    "compartment",
                    "get",
                    "--compartment-id",
                    current,
                    "--query",
                    'data.{id:id,parent:"compartment-id"}',
                ),
            )
            if (
                not isinstance(data, dict)
                or data.get("id") != current
                or not data.get("parent")
            ):
                raise Failure("identity_failure")
            r.observe(eid, {"id": data["id"], "parent": data["parent"]})
            current = data["parent"]
    r.observed["compartment_ids"] = a.compartment_ids
    r.limitations.append(
        "OCI Search is indexed and permission-filtered; NotAuthorizedOrNotFound does not establish absence."
    )
    for region in a.regions:
        for compartment in a.compartment_ids:
            scope = compartment + "/" + region

            def listing(operation, command, projection):
                def fetch(token):
                    args = [*command, "--limit", "100", "--query", projection]
                    if token:
                        args += ["--page", str(token)]
                    return cli(region, *args)

                return r.listing(
                    operation,
                    scope,
                    fetch,
                    lambda d: d["data"],
                    lambda d: d.get("next") or None,
                )[0]

            search = [
                "search",
                "resource",
                "structured-search",
                "--tenant-id",
                a.tenancy_id,
                "--query-text",
                "query all resources where compartmentId = '" + compartment + "'",
            ]
            search_rows = listing(
                "search.resource",
                search,
                '{data:data.items[].{id:identifier,type:"resource-type"},next:"opc-next-page"}',
            )
            for x, eid in search_rows:
                r.resource(
                    x.get("id"), "search", scope, {"resource_type": x.get("type")}, eid
                )
            families = [
                (
                    "instance",
                    ["compute", "instance", "list"],
                    'data[].{id:id,state:"lifecycle-state",availability:"availability-domain"}',
                ),
                (
                    "volume",
                    ["bv", "volume", "list"],
                    'data[].{id:id,state:"lifecycle-state",availability:"availability-domain"}',
                ),
                (
                    "vcn",
                    ["network", "vcn", "list"],
                    'data[].{id:id,state:"lifecycle-state"}',
                ),
                (
                    "security-list",
                    ["network", "security-list", "list"],
                    'data[].{id:id,vcn:"vcn-id",rules:"ingress-security-rules"}',
                ),
                ("nsg", ["network", "nsg", "list"], 'data[].{id:id,vcn:"vcn-id"}'),
            ]
            for kind, cmd, fields in families:
                for x, eid in listing(
                    ".".join(cmd),
                    [*cmd, "--compartment-id", compartment],
                    "{data:" + fields + ',next:"opc-next-page"}',
                ):
                    rid = r.resource(
                        x.get("id"),
                        kind,
                        scope,
                        selected(
                            x,
                            {
                                "state": "state",
                                "vcn": "vcn",
                                "availability": "availability",
                            },
                        ),
                        eid,
                    )
                    raw = x.get("rules")
                    if kind == "nsg" and x.get("id"):
                        rows = listing(
                            "network.nsg.rules.list",
                            ["network", "nsg", "rules", "list", "--nsg-id", x["id"]],
                            '{data:data,next:"opc-next-page"}',
                        )
                        raw = (
                            [v for v, _ in rows]
                            if r.operations[-1]["status"] == "complete"
                            else None
                        )
                        if rows:
                            eid = rows[0][1]
                    if kind in ("nsg", "security-list"):
                        rules = None if not isinstance(raw, list) else []
                        for rule in items(raw):
                            rule = obj(rule)
                            if rule.get("direction", "INGRESS") != "INGRESS":
                                continue
                            port = obj(
                                obj(rule.get("tcp-options")).get(
                                    "destination-port-range"
                                )
                            )
                            rules.append(
                                {
                                    "active": True,
                                    "protocol": rule.get("protocol"),
                                    "sources": [rule["source"]]
                                    if "source" in rule
                                    else None,
                                    "ports": [
                                        str(port.get("min"))
                                        + "-"
                                        + str(port.get("max"))
                                    ]
                                    if port
                                    else [],
                                }
                            )
                        r.observe(eid, {"ingress": rules})
                        r.ingress(rid, rules, eid)
            ns, ne = r.read(
                "os.ns.get",
                scope,
                lambda: cli(
                    region,
                    "os",
                    "ns",
                    "get",
                    "--compartment-id",
                    a.tenancy_id,
                    "--query",
                    "data",
                ),
            )
            if not isinstance(ns, str):
                r.mark(
                    ne,
                    "malformed"
                    if ns is not None
                    else r.operations[int(ne[1:]) - 1]["status"],
                )
                _, missing = r.read("os.bucket.list", scope, lambda: None)
                r.mark(missing, "not_collected")
                continue
            for x, eid in listing(
                "os.bucket.list",
                [
                    "os",
                    "bucket",
                    "list",
                    "--compartment-id",
                    compartment,
                    "--namespace-name",
                    ns,
                ],
                '{data:data[].{name:name},next:"opc-next-page"}',
            ):
                name = x.get("name")
                if not isinstance(name, str):
                    r.mark(eid, "malformed")
                    continue
                data, de = r.read(
                    "os.bucket.get",
                    scope,
                    lambda: cli(
                        region,
                        "os",
                        "bucket",
                        "get",
                        "--namespace-name",
                        ns,
                        "--bucket-name",
                        name,
                        "--query",
                        'data.{access:"public-access-type",versioning:versioning}',
                    ),
                )
                attrs = selected(
                    obj(data), {"public_access": "access", "versioning": "versioning"}
                )
                rid = r.resource(name, "bucket", scope, attrs, de)
                access = attrs["public_access"]
                r.finding(
                    "bucket-public-access",
                    rid,
                    "pass"
                    if access == "NoPublicAccess"
                    else "fail"
                    if access in ("ObjectRead", "ObjectReadWithoutList")
                    else "unknown",
                    de,
                    "Bucket private-storage baseline.",
                    "Review public access and restrict it where required.",
                )
                v = attrs["versioning"]
                r.finding(
                    "bucket-versioning",
                    rid,
                    "pass"
                    if v == "Enabled"
                    else "manual_review"
                    if v in ("Disabled", "Suspended")
                    else "unknown",
                    de,
                    "Bucket versioning.",
                    "Review recovery requirements.",
                )
    r.observed["regions"] = [
        region
        for region in a.regions
        if any(
            op["status"] == "complete" and op["scope"].endswith("/" + region)
            for op in r.operations
        )
    ]


def main():
    p = parser("oci")
    p.add_argument("--tenancy-id", required=True)
    p.add_argument("--compartment-ids", nargs="+", required=True)
    p.add_argument("--regions", nargs="+", required=True)
    p.add_argument("--profile", required=True)
    return run(
        "oci",
        p,
        collect,
        SOURCE,
        [
            "Cloud Advisor, Cloud Guard and unlisted service configurations",
            "Effective network reachability and recovery testing",
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
