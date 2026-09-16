"""Azure subscription onboarding using existing read-only CLI credentials."""

import sys
from report_common import Failure, parser, run, obj, items, selected

SOURCE = "https://learn.microsoft.com/en-us/azure/governance/resource-graph/overview"


def collect(r, a):
    if not a.include_recommendations:
        r.unsupported.append("Azure Advisor not requested (--include-recommendations)")
    scope = a.subscription_id

    def az(*args):
        return r.cli(
            [
                "az",
                *args,
                "--subscription",
                scope,
                "--output",
                "json",
                "--only-show-errors",
            ]
        )

    cloud, eid = r.read(
        "cloud.show",
        scope,
        lambda: r.cli(["az", "cloud", "show", "--query", "{name:name}", "-o", "json"]),
    )
    if obj(cloud).get("name") != "AzureCloud":
        raise Failure("identity_failure")
    data, eid = r.read(
        "account.show",
        scope,
        lambda: az(
            "account", "show", "--query", "{id:id,tenantId:tenantId,state:state}"
        ),
    )
    r.verify(
        data,
        eid,
        lambda d: (
            d.get("id") == scope
            and d.get("tenantId") == a.tenant_id
            and d.get("state") == "Enabled"
        ),
        lambda d: {"subscription_id": d["id"], "tenant_id": d["tenantId"]},
    )
    query = "Resources | project id, type, location, resourceGroup, ownerPresent=isnotempty(tags.owner), environmentPresent=isnotempty(tags.environment), projectPresent=isnotempty(tags.project) | order by id asc"

    def graph(token):
        argv = [
            "az",
            "graph",
            "query",
            "--subscriptions",
            scope,
            "--first",
            "1000",
            "-q",
            query,
            "-o",
            "json",
        ]
        if token:
            argv += ["--skip-token", token]
        data = r.cli(argv)
        if isinstance(data, dict) and not (
            data.get("skipToken") or data.get("skip_token") or data.get("$skipToken")
        ):
            if str(
                data.get("resultTruncated", data.get("result_truncated", "false"))
            ).lower() == "true" or (
                token is None
                and type(data.get("totalRecords", data.get("total_records"))) is int
                and isinstance(data.get("data"), list)
                and data.get("totalRecords", data.get("total_records"))
                > len(data["data"])
            ):
                raise Failure("truncated")
        return data

    rows, _ = r.listing(
        "graph.query",
        scope,
        graph,
        lambda d: d["data"],
        lambda d: (
            d.get("skipToken") or d.get("skip_token") or d.get("$skipToken") or None
        ),
    )
    r.limitations.append(
        "Resource Graph is indexed and permission-filtered; complete queries do not prove subscription-wide visibility."
    )
    for x, eid in rows:
        kind, native = x.get("type"), x.get("id")
        if not isinstance(native, str) or not native.lower().startswith(
            "/subscriptions/" + scope.lower() + "/"
        ):
            r.mark(eid, "malformed")
            continue
        rid = r.resource(
            native,
            str(kind),
            scope,
            selected(
                x,
                {
                    "location": "location",
                    "resource_group": "resourceGroup",
                    "owner_present": "ownerPresent",
                    "environment_present": "environmentPresent",
                    "project_present": "projectPresent",
                },
            ),
            eid,
        )
        commands = {
            "microsoft.compute/virtualmachines": ("vm", "show"),
            "microsoft.network/networksecuritygroups": ("network", "nsg", "show"),
            "microsoft.storage/storageaccounts": ("storage", "account", "show"),
        }
        key = str(kind).lower()
        if key not in commands:
            continue
        projection = {
            "microsoft.compute/virtualmachines": "{osDisk:storageProfile.osDisk.managedDisk.id,dataDisks:storageProfile.dataDisks[].managedDisk.id}",
            "microsoft.network/networksecuritygroups": "{securityRules:securityRules[].{direction:direction,access:access,protocol:protocol,sourceAddressPrefix:sourceAddressPrefix,sourceAddressPrefixes:sourceAddressPrefixes,destinationPortRange:destinationPortRange,destinationPortRanges:destinationPortRanges}}",
            "microsoft.storage/storageaccounts": "{enableHttpsTrafficOnly:enableHttpsTrafficOnly,minimumTlsVersion:minimumTlsVersion,allowBlobPublicAccess:allowBlobPublicAccess}",
        }[key]
        detail, de = r.read(
            ".".join(commands[key]),
            native,
            lambda: az(*commands[key], "--ids", native, "--query", projection),
        )
        detail = obj(detail)
        if key.endswith("storageaccounts"):
            attrs = selected(
                detail,
                {
                    "https_only": "enableHttpsTrafficOnly",
                    "minimum_tls": "minimumTlsVersion",
                    "public_blob_access": "allowBlobPublicAccess",
                },
            )
            r.observe(de, attrs)
            r.boolean("storage-https", rid, attrs["https_only"], de)
            r.boolean(
                "storage-public-blob", rid, attrs["public_blob_access"], de, False
            )
            tls = attrs["minimum_tls"]
            r.finding(
                "storage-tls",
                rid,
                "pass"
                if tls in ("TLS1_2", "TLS1_3")
                else "fail"
                if tls in ("TLS1_0", "TLS1_1")
                else "unknown",
                de,
                "Storage minimum TLS baseline is 1.2.",
                "Require TLS 1.2 or newer.",
            )
        elif key.endswith("networksecuritygroups"):
            rules = None if not isinstance(detail.get("securityRules"), list) else []
            for rule in items(detail.get("securityRules")):
                rule = obj(rule)
                rules.append(
                    {
                        "active": rule.get("direction") == "Inbound"
                        and rule.get("access") == "Allow"
                        if rule.get("direction") and rule.get("access")
                        else None,
                        "protocol": rule.get("protocol"),
                        "sources": rule.get("sourceAddressPrefixes")
                        or (
                            [rule["sourceAddressPrefix"]]
                            if "sourceAddressPrefix" in rule
                            else None
                        ),
                        "ports": rule.get("destinationPortRanges")
                        or (
                            [rule["destinationPortRange"]]
                            if "destinationPortRange" in rule
                            else None
                        ),
                    }
                )
            r.observe(de, {"ingress": rules})
            r.ingress(rid, rules, de)
        else:
            r.observe(
                de, selected(detail, {"os_disk": "osDisk", "data_disks": "dataDisks"})
            )
    if a.include_recommendations:
        recs, _ = r.listing(
            "advisor.recommendation.list",
            scope,
            lambda _: az(
                "advisor",
                "recommendation",
                "list",
                "--query",
                "[].{id:id,category:category,impact:impact}",
            ),
        )
        for rec, eid in recs:
            attrs = selected(rec, {"category": "category", "impact": "impact"})
            rid = r.resource(rec.get("id"), "advisor", scope, attrs, eid)
            r.finding(
                "native-advisor",
                rid,
                "manual_review",
                eid,
                "Existing Azure Advisor recommendation.",
                "Review in Azure Advisor against workload requirements.",
            )


def main():
    p = parser("azure")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--subscription-id", required=True)
    p.add_argument("--include-recommendations", action="store_true")
    return run(
        "azure",
        p,
        collect,
        SOURCE,
        [
            "Unlisted services and data-plane resources",
            "Effective network reachability, backup and encryption adequacy",
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
