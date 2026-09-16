"""GCP project onboarding through scoped gcloud reads."""

import sys
from report_common import Failure, parser, run, obj, items, selected

SOURCE = "https://cloud.google.com/asset-inventory/docs/search-resources"


def collect(r, a):
    scope = a.project_id
    config, eid = r.read(
        "config.identity",
        scope,
        lambda: r.cli(
            [
                "gcloud",
                "config",
                "list",
                "--format=json(core.account,auth.impersonate_service_account,api_endpoint_overrides)",
            ]
        ),
    )
    config = obj(config)
    ambient = obj(config.get("auth")).get("impersonate_service_account")
    principal = a.impersonate_service_account or obj(config.get("core")).get("account")
    if (
        config.get("api_endpoint_overrides")
        or (ambient and ambient != a.impersonate_service_account)
        or principal != a.expected_principal
    ):
        raise Failure("identity_failure")
    if any(
        k.startswith("CLOUDSDK_API_ENDPOINT_OVERRIDES_") and v for k, v in r.env.items()
    ):
        raise Failure("unsafe_endpoint")

    def gc(*args):
        command = ["gcloud", *args, "--project", scope, "--quiet"]
        if a.impersonate_service_account:
            command += ["--impersonate-service-account", a.impersonate_service_account]
        else:
            command += ["--account", a.expected_principal]
        return r.cli(command)

    data, eid = r.read(
        "projects.describe",
        scope,
        lambda: gc(
            "projects", "describe", scope, "--format=json(projectId,projectNumber)"
        ),
    )
    r.verify(
        data,
        eid,
        lambda d: d.get("projectId") == scope and bool(d.get("projectNumber")),
        lambda d: {
            "project_id": d["projectId"],
            "project_number": d["projectNumber"],
            "principal": principal,
        },
    )
    r.limitations.append(
        "Asset search covers supported indexed types; inherited policies and effective firewall reachability are not assessed."
    )
    commands = [
        (
            "asset",
            [
                "asset",
                "search-all-resources",
                "--scope=projects/" + scope,
                "--read-mask=name,assetType,location",
            ],
            "name,assetType,location",
        ),
        (
            "instance",
            ["compute", "instances", "list"],
            "id,name,zone,disks.deviceName,disks.source,networkInterfaces.accessConfigs.type",
        ),
        ("disk", ["compute", "disks", "list"], "id,name,zone,region,users"),
        (
            "firewall",
            ["compute", "firewall-rules", "list"],
            "id,name,direction,disabled,allowed,sourceRanges",
        ),
        (
            "bucket",
            ["storage", "buckets", "list"],
            "name,location,public_access_prevention,uniform_bucket_level_access,versioning_enabled",
        ),
    ]
    for kind, command, fields in commands:
        rows, _ = r.listing(
            ".".join(command[:3]),
            scope,
            lambda _, cmd=command, fs=fields: gc(
                *cmd, "--limit=" + str(a.max_items + 1), "--format=json(" + fs + ")"
            ),
        )
        for x, eid in rows:
            name = x.get("name")
            attrs = {"location": x.get("location") or x.get("zone") or x.get("region")}
            if kind == "asset":
                attrs["asset_type"] = (
                    x.get("assetType") if isinstance(x.get("assetType"), str) else None
                )
            if kind == "instance":
                attrs["disks"] = [
                    d.get("source")
                    for d in items(x.get("disks"))
                    if isinstance(d, dict)
                ]
                attrs["external_ip_present"] = any(
                    items(obj(n).get("accessConfigs"))
                    for n in items(x.get("networkInterfaces"))
                )
            elif kind == "disk":
                attrs["users"] = (
                    x.get("users") if isinstance(x.get("users"), list) else None
                )
            elif kind == "bucket":
                attrs.update(
                    selected(
                        x,
                        {
                            "public_access_prevention": "public_access_prevention",
                            "uniform_access": "uniform_bucket_level_access",
                            "versioning": "versioning_enabled",
                        },
                    )
                )
            native_id = (
                x.get("id") if kind in ("instance", "disk", "firewall") else name
            )
            if kind in ("instance", "disk", "firewall"):
                attrs["name"] = name if isinstance(name, str) else None
            rid = r.resource(native_id, kind, scope, attrs, eid)
            if kind == "firewall":
                rules = None
                if isinstance(x.get("allowed"), list):
                    rules = [
                        {
                            "active": x.get("direction") == "INGRESS"
                            and x.get("disabled") is False
                            if x.get("direction") and type(x.get("disabled")) is bool
                            else None,
                            "protocol": obj(rule).get("IPProtocol"),
                            "sources": x.get("sourceRanges"),
                            "ports": obj(rule).get("ports", []),
                        }
                        for rule in x["allowed"]
                    ]
                r.observe(eid, {"ingress": rules})
                r.ingress(rid, rules, eid)
            elif kind == "bucket":
                if (
                    any(v is None for k, v in attrs.items() if k != "location")
                    and isinstance(name, str)
                    and "/" not in name
                ):
                    detail, de = r.read(
                        "storage.buckets.describe",
                        name,
                        lambda: gc(
                            "storage",
                            "buckets",
                            "describe",
                            "gs://" + name,
                            "--format=json(public_access_prevention,uniform_bucket_level_access,versioning_enabled)",
                        ),
                    )
                    attrs.update(
                        selected(
                            obj(detail),
                            {
                                "public_access_prevention": "public_access_prevention",
                                "uniform_access": "uniform_bucket_level_access",
                                "versioning": "versioning_enabled",
                            },
                        )
                    )
                    for resource in r.resources:
                        if resource["id"] == rid:
                            resource["evidence"].append(de)
                            break
                    eid = de
                r.observe(eid, attrs)
                r.boolean("uniform-bucket-access", rid, attrs["uniform_access"], eid)
                pap = attrs["public_access_prevention"]
                r.finding(
                    "public-access-prevention",
                    rid,
                    "pass"
                    if pap == "enforced"
                    else "manual_review"
                    if pap == "inherited"
                    else "unknown",
                    eid,
                    "Bucket public-access prevention; inherited policy is not evaluated.",
                    "Review organization policy and enforce public-access prevention as appropriate.",
                )
                value = attrs["versioning"]
                r.finding(
                    "bucket-versioning",
                    rid,
                    "pass"
                    if value is True
                    else "manual_review"
                    if value is False
                    else "unknown",
                    eid,
                    "Bucket versioning configuration.",
                    "Review workload recovery requirements.",
                )


def main():
    p = parser("gcp")
    p.add_argument("--project-id", required=True)
    p.add_argument("--expected-principal", required=True)
    p.add_argument("--impersonate-service-account")
    return run(
        "gcp",
        p,
        collect,
        SOURCE,
        [
            "Organization traversal, IAM policy, SCC and Recommender",
            "Unlisted services and effective inherited controls",
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
