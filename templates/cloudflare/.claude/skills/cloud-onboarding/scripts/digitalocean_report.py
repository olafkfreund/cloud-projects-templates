"""DigitalOcean explicit project resource assessment."""

import os
import sys
from urllib.parse import urlencode, urlsplit, parse_qs
from report_common import Failure, parser, run, obj, items, selected, segment

SOURCE = "https://docs.digitalocean.com/products/networking/firewalls/how-to/configure-rules/"
ORIGIN = "https://api.digitalocean.com"


def collect(r, a):
    token = os.environ.get("DIGITALOCEAN_READ_TOKEN")
    if not token:
        raise Failure("missing_credential")

    def get(path):
        return r.http(ORIGIN, "/v2" + path, token)

    data, eid = r.read("account.get", a.account_uuid, lambda: get("/account"))
    r.verify(
        data,
        eid,
        lambda d: obj(d.get("account")).get("uuid") == a.account_uuid,
        lambda d: {"account_uuid": d["account"]["uuid"]},
    )
    owner_ids = {a.account_uuid}
    team_uuid = obj(obj(data.get("account")).get("team")).get("uuid")
    if isinstance(team_uuid, str):
        owner_ids.add(team_uuid)
        r.observed["team_uuid"] = team_uuid
        r.observe(eid, {"team_uuid": team_uuid})
    data, eid = r.read(
        "project.get", a.project_id, lambda: get("/projects/" + segment(a.project_id))
    )
    r.verify(
        data,
        eid,
        lambda d: (
            obj(d.get("project")).get("id") == a.project_id
            and obj(d.get("project")).get("owner_uuid", a.account_uuid) in owner_ids
        ),
        lambda d: {"project_id": d["project"]["id"]},
    )
    r.limitations.append(
        "Project lists silently omit resource families lacking token read scopes. Account UUID does not independently verify team identity."
    )

    def next_page(d, path):
        pages = obj(obj(d.get("links")).get("pages"))
        url = pages.get("next")
        if not url:
            return None
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or parts.netloc != "api.digitalocean.com"
            or parts.path != "/v2" + path
            or parts.fragment
        ):
            raise Failure("unsafe_pagination")
        query = parse_qs(parts.query)
        if not set(query) <= {"page", "per_page"} or len(query.get("page", [])) != 1:
            raise Failure("malformed")
        page = int(query["page"][0])
        if page < 1:
            raise Failure("malformed")
        return page

    path = "/projects/" + segment(a.project_id) + "/resources"
    rows, _ = r.listing(
        "project.resources",
        a.project_id,
        lambda page: get(path + "?" + urlencode({"page": page or 1, "per_page": 100})),
        lambda d: d["resources"],
        lambda d: next_page(d, path),
    )
    types = {
        "droplet": ("droplets", "droplet"),
        "volume": ("volumes", "volume"),
        "loadbalancer": ("load_balancers", "load_balancer"),
    }
    for x, eid in rows:
        urn = x.get("urn")
        if not isinstance(urn, str):
            r.mark(eid, "malformed")
            continue
        parts = urn.split(":")
        if len(parts) != 3 or parts[0] != "do":
            r.mark(eid, "malformed")
            continue
        kind, native = parts[1:]
        if kind not in types:
            rid = r.resource(urn, "unsupported", a.project_id, {}, eid)
            r.finding(
                "unsupported-resource",
                rid,
                "unknown",
                eid,
                "Resource configuration is not supported.",
                "Review with the provider procedure.",
            )
            continue
        plural, singular = types[kind]
        data, de = r.read(
            plural + ".get", urn, lambda: get("/" + plural + "/" + segment(native))
        )
        detail = obj(obj(data).get(singular))
        attrs = selected(detail, {"region": "region.slug", "status": "status"})
        if kind == "droplet":
            attrs["backups"] = (
                "backups" in detail["features"]
                if isinstance(detail.get("features"), list)
                else None
            )
        rid = r.resource(urn, kind, a.project_id, attrs, de)
        if kind == "droplet":
            value = attrs["backups"]
            r.finding(
                "backups",
                rid,
                "pass"
                if value is True
                else "manual_review"
                if value is False
                else "unknown",
                de,
                "Droplet backup configuration.",
                "Review recovery requirements.",
            )
            firewall_path = "/droplets/" + segment(native) + "/firewalls"
            firewalls, complete = r.listing(
                "droplet.firewalls",
                urn,
                lambda page: get(
                    firewall_path
                    + "?"
                    + urlencode({"page": page or 1, "per_page": 100})
                ),
                lambda d: d["firewalls"],
                lambda d: next_page(d, firewall_path),
            )
            if not firewalls and complete:
                r.finding(
                    "cloud-firewall",
                    rid,
                    "manual_review",
                    de,
                    "No cloud firewall observed.",
                    "Review host firewall and exposure requirements.",
                )
            for fw, fe in firewalls:
                rules = (
                    None
                    if not isinstance(fw.get("inbound_rules"), list)
                    else [
                        {
                            "active": True,
                            "protocol": v.get("protocol"),
                            "sources": obj(v.get("sources")).get("addresses", []),
                            "ports": [v.get("ports")],
                        }
                        for v in fw["inbound_rules"]
                        if isinstance(v, dict)
                    ]
                )
                fr = r.resource(
                    fw.get("id"), "firewall", a.project_id, {"ingress": rules}, fe
                )
                r.ingress(fr, rules, fe)
        elif kind == "loadbalancer":
            forwarding = [
                obj(v).get("entry_protocol")
                for v in items(detail.get("forwarding_rules"))
            ]
            r.observe(
                de,
                {
                    "entry_protocols": forwarding,
                    "redirect_http_to_https": detail.get("redirect_http_to_https"),
                },
            )
            if forwarding and all(x == "http" for x in forwarding):
                r.finding(
                    "lb-http",
                    rid,
                    "manual_review",
                    de,
                    "HTTP-only forwarding observed.",
                    "Review TLS termination and traffic requirements.",
                )


def main():
    p = parser("digitalocean")
    p.add_argument("--account-uuid", required=True)
    p.add_argument("--project-id", required=True)
    return run(
        "digitalocean",
        p,
        collect,
        SOURCE,
        [
            "Spaces, managed database configuration, app specs and unlisted team services"
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
