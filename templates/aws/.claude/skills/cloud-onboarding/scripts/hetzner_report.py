"""Hetzner Cloud project-token onboarding with explicit identity attestation."""

import os
import sys
from urllib.parse import urlencode
from report_common import Failure, parser, run, obj, items, selected, segment, positive

SOURCE = "https://docs.hetzner.cloud/reference/cloud"
ORIGIN = "https://api.hetzner.cloud"


def collect(r, a):
    token = os.environ.get("HCLOUD_TOKEN")
    if not token:
        raise Failure("missing_credential")
    if not a.acknowledge_project_token:
        raise Failure("identity_attestation_required")

    def get(path):
        return r.http(ORIGIN, "/v1" + path, token)

    r.identity = {
        "status": "attested",
        "method": "User-confirmed project Read token; no API project identity",
        "evidence": [],
    }
    r.observed = {"project_label": a.project_label, "project_identity": "user_attested"}
    r.limitations.append(
        "Project token association is user-attested, not verified by an API project identity. Scope may be empty."
    )
    if a.expected_server_id:
        data, eid = r.read(
            "server.sentinel",
            a.project_label,
            lambda: get("/servers/" + segment(a.expected_server_id)),
        )
        if obj(obj(data).get("server")).get("id") != a.expected_server_id:
            raise Failure("identity_failure")
        r.identity = {
            "status": "corroborated",
            "method": "User attestation plus known server access",
            "evidence": [eid],
        }
        r.observe(eid, {"server_id": a.expected_server_id})

    def next_page(d):
        pagination = obj(obj(d.get("meta")).get("pagination"))
        if "next_page" not in pagination:
            raise Failure("malformed")
        n = pagination["next_page"]
        if n is not None and (type(n) is not int or n < 1):
            raise Failure("malformed")
        return n

    for kind in ("servers", "volumes", "networks", "firewalls", "load_balancers"):
        rows, _ = r.listing(
            kind + ".list",
            a.project_label,
            lambda page: get(
                "/" + kind + "?" + urlencode({"page": page or 1, "per_page": 100})
            ),
            lambda d: d[kind],
            next_page,
        )
        for x, eid in rows:
            attrs = selected(
                x,
                {
                    "status": "status",
                    "location": "datacenter.location.name"
                    if kind == "servers"
                    else "location.name",
                },
            )
            if kind == "servers":
                attrs.update(
                    {
                        "backup_present": bool(x["backup_window"])
                        if isinstance(x.get("backup_window"), str)
                        else False
                        if "backup_window" in x and x["backup_window"] is None
                        else None,
                        "delete_protection": obj(x.get("protection")).get("delete"),
                        "firewall_ids": [
                            obj(f).get("id")
                            for f in items(obj(x.get("public_net")).get("firewalls"))
                        ],
                    }
                )
            if kind == "volumes":
                attrs["server"] = x.get("server")
            rid = r.resource(x.get("id"), kind, a.project_label, attrs, eid)
            if kind == "firewalls":
                rules = (
                    None
                    if not isinstance(x.get("rules"), list)
                    else [
                        {
                            "active": v.get("direction") == "in"
                            if v.get("direction")
                            else None,
                            "protocol": v.get("protocol"),
                            "sources": v.get("source_ips"),
                            "ports": [v.get("port")],
                        }
                        for v in x["rules"]
                        if isinstance(v, dict)
                    ]
                )
                r.observe(eid, {"ingress": rules})
                r.ingress(rid, rules, eid)
                if any(
                    obj(t).get("type") == "label_selector"
                    for t in items(x.get("applied_to"))
                ):
                    r.finding(
                        "firewall-selector",
                        rid,
                        "unknown",
                        eid,
                        "Label-selector attachment not expanded in persisted evidence.",
                        "Verify selector membership using scoped metadata.",
                    )
            elif kind == "servers":
                for k in ("backup_present", "delete_protection"):
                    value = attrs[k]
                    r.finding(
                        k,
                        rid,
                        "pass"
                        if value is True
                        else "manual_review"
                        if value is False
                        else "unknown",
                        eid,
                        k.replace("_", " ") + ".",
                        "Review recovery and replacement requirements.",
                    )
            elif kind == "load_balancers":
                health = [
                    obj(h).get("status")
                    for t in items(x.get("targets"))
                    for h in items(obj(t).get("health_status"))
                ]
                r.observe(eid, {"target_health": health})
                if "unhealthy" in health:
                    r.finding(
                        "target-health",
                        rid,
                        "manual_review",
                        eid,
                        "Unhealthy target observed.",
                        "Investigate target readiness and traffic requirements.",
                    )
    if r.operations and all(o["status"] == "access_denied" for o in r.operations):
        raise Failure("identity_failure")


def main():
    p = parser("hetzner")
    p.add_argument("--project-label", required=True)
    p.add_argument("--acknowledge-project-token", action="store_true")
    p.add_argument("--expected-server-id", type=positive)
    return run(
        "hetzner",
        p,
        collect,
        SOURCE,
        [
            "Object Storage, Robot, Storage Boxes, account audit/token policy",
            "Effective host firewalls and workload recovery",
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
