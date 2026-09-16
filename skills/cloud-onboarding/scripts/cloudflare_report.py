"""Cloudflare explicit account/zone onboarding via read APIs."""

import os
import sys
from urllib.parse import urlencode
from report_common import Failure, parser, run, obj, selected, segment

SOURCE = (
    "https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/"
)
ORIGIN = "https://api.cloudflare.com"


def collect(r, a):
    if not a.include_recommendations:
        r.unsupported.append(
            "Cloudflare Insights not requested (--include-recommendations)"
        )
    token = os.environ.get("CLOUDFLARE_READ_TOKEN")
    if not token:
        raise Failure("missing_credential")

    def get(path):
        data = r.http(ORIGIN, "/client/v4" + path, token)
        if not isinstance(data, dict) or data.get("success") is not True:
            raise Failure("unavailable")
        return data

    data, eid = r.read(
        "account.get", a.account_id, lambda: get("/accounts/" + segment(a.account_id))
    )
    r.verify(
        data,
        eid,
        lambda d: obj(d.get("result")).get("id") == a.account_id,
        lambda d: {"account_id": d["result"]["id"]},
    )
    for zone in a.zone_ids:
        base = "/zones/" + segment(zone)
        data, eid = r.read("zone.get", zone, lambda: get(base))
        r.verify(
            data,
            eid,
            lambda d: (
                obj(d.get("result")).get("id") == zone
                and obj(obj(d["result"]).get("account")).get("id") == a.account_id
            ),
            lambda d: {"last_verified_zone": d["result"]["id"]},
        )
    r.observed.pop("last_verified_zone", None)
    r.observed["zone_ids"] = a.zone_ids
    r.limitations.append(
        "Only explicitly selected zones; readable settings and insights depend on token scopes and subscribed features."
    )
    for zone in a.zone_ids:
        base = "/zones/" + segment(zone)

        def next_dns(d):
            info = obj(d.get("result_info"))
            if not all(type(info.get(k)) is int for k in ("page", "total_pages")):
                raise Failure("malformed")
            return info["page"] + 1 if info["page"] < info["total_pages"] else None

        rows, _ = r.listing(
            "dns_records.list",
            zone,
            lambda page: get(
                base + "/dns_records?" + urlencode({"page": page or 1, "per_page": 100})
            ),
            lambda d: d["result"],
            next_dns,
        )
        for x, eid in rows:
            attrs = selected(
                x, {"type": "type", "proxiable": "proxiable", "proxied": "proxied"}
            )
            rid = r.resource(x.get("id"), "dns-record", zone, attrs, eid)
            if attrs["proxied"] is False:
                r.finding(
                    "dns-only",
                    rid,
                    "manual_review",
                    eid,
                    "DNS-only record; origin exposure is workload-dependent.",
                    "Review whether proxying is appropriate.",
                )
        for setting in ("ssl", "min_tls_version", "always_use_https"):
            data, eid = r.read(
                "setting." + setting, zone, lambda: get(base + "/settings/" + setting)
            )
            value = obj(obj(data).get("result")).get("value")
            rid = r.resource(zone, "zone", a.account_id, {}, eid)
            r.observe(eid, {"setting": setting, "value": value})
            if setting == "ssl":
                status = (
                    "pass"
                    if value == "strict"
                    else "fail"
                    if value in ("off", "flexible", "full")
                    else "unknown"
                )
            elif setting == "min_tls_version":
                status = (
                    "pass"
                    if value in ("1.2", "1.3")
                    else "fail"
                    if value in ("1.0", "1.1")
                    else "unknown"
                )
            else:
                status = (
                    "pass" if value == "on" else "fail" if value == "off" else "unknown"
                )
            r.finding(
                setting,
                rid,
                status,
                eid,
                "Zone transport baseline: " + setting + ".",
                "Review and enforce strict origin TLS, TLS 1.2+, and HTTPS redirects.",
            )
    if a.include_recommendations:

        def next_insight(d):
            result = obj(d.get("result"))
            page, size, count = (result.get(k) for k in ("page", "per_page", "count"))
            if any(type(x) is not int for x in (page, size, count)) or size <= 0:
                raise Failure("malformed")
            return page + 1 if page * size < count else None

        rows, _ = r.listing(
            "security-center.insights",
            a.account_id,
            lambda page: get(
                "/accounts/"
                + segment(a.account_id)
                + "/security-center/insights?"
                + urlencode({"page": page or 1, "per_page": 100})
            ),
            lambda d: d["result"]["issues"],
            next_insight,
        )
        for x, eid in rows:
            rid = r.resource(
                x.get("id"),
                "insight",
                a.account_id,
                selected(
                    x,
                    {
                        "type": "issue_type",
                        "severity": "severity",
                        "status": "status",
                        "timestamp": "timestamp",
                    },
                ),
                eid,
            )
            r.finding(
                "native-insight",
                rid,
                "manual_review",
                eid,
                "Existing native Security Center insight.",
                "Review in Cloudflare against workload requirements.",
            )


def main():
    p = parser("cloudflare")
    p.add_argument("--account-id", required=True)
    p.add_argument("--zone-ids", nargs="+", required=True)
    p.add_argument("--include-recommendations", action="store_true")
    return run(
        "cloudflare",
        p,
        collect,
        SOURCE,
        ["Workers, secrets, certificates, DNS content and unselected zones"],
    )


if __name__ == "__main__":
    sys.exit(main())
