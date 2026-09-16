"""Namespaced Kubernetes metadata/configuration assessment; no workload mutation."""

import sys
from report_common import Failure, parser, run, obj, items, selected

SOURCE = "https://kubernetes.io/docs/concepts/security/pod-security-standards/"


def collect(r, a):
    def kube(*args):
        return r.cli(
            [
                "kubectl",
                "--context",
                a.context,
                "--request-timeout=" + str(a.command_timeout) + "s",
                *args,
            ]
        )

    config, eid = r.read(
        "config.view",
        a.context,
        lambda: kube(
            "config", "view", "--minify", "-o", "jsonpath={.clusters[0].cluster}"
        ),
    )
    if (
        not isinstance(config, dict)
        or config.get("server") != a.expected_server
        or not a.expected_server.startswith("https://")
        or config.get("insecure-skip-tls-verify")
    ):
        raise Failure("identity_failure")
    # Never request --raw; kubectl redacts credentials, and this projection selects only cluster settings.
    who, eid = r.read(
        "auth.whoami", a.context, lambda: kube("auth", "whoami", "-o", "json")
    )
    r.verify(
        who,
        eid,
        lambda d: (
            obj(obj(d.get("status")).get("userInfo")).get("username")
            == a.expected_principal
        ),
        lambda d: {
            "server": a.expected_server,
            "principal": d["status"]["userInfo"]["username"],
        },
        "TLS endpoint and non-persistent SelfSubjectReview",
    )
    r.limitations.append(
        "Context name is local; identity is the verified TLS endpoint/principal and observed Namespace UIDs. Policies do not prove effective isolation."
    )
    namespace_uids = {}

    def scalar(path):
        return (
            "{{if eq ("
            + path
            + ') nil}}null{{else}}{{printf "%v" '
            + path
            + "}}{{end}}"
        )

    def security(prefix):
        return (
            '{"privileged":'
            + scalar(prefix + ".privileged")
            + ',"allowPrivilegeEscalation":'
            + scalar(prefix + ".allowPrivilegeEscalation")
            + "}"
        )

    # Selected output uses boolean presence for arbitrary quantity/probe objects.
    def present(path):
        return "{{if " + path + "}}true{{else}}false{{end}}"

    def pod(path):
        fields = [
            '"' + flag + '":' + scalar(path + "." + flag)
            for flag in ("hostNetwork", "hostPID", "hostIPC")
        ]
        for kind in ("containers", "initContainers"):
            fields.append(
                '"'
                + kind
                + '":[{{range $i,$c := '
                + path
                + "."
                + kind
                + '}}{{if $i}},{{end}}{"securityContext":'
                + security("$c.securityContext")
                + ',"resources":{"requests":'
                + present("$c.resources.requests")
                + ',"limits":'
                + present("$c.resources.limits")
                + '},"readinessProbe":'
                + present("$c.readinessProbe")
                + ',"livenessProbe":'
                + present("$c.livenessProbe")
                + "}{{end}}]"
            )
        return "{" + ",".join(fields) + "}"

    template = (
        '{"items":[{{range $i,$x := .items}}{{if $i}},{{end}}{"metadata":{"uid":{{printf "%q" $x.metadata.uid}},"ownerReferences":[{{range $j,$o := $x.metadata.ownerReferences}}{{if $j}},{{end}}{"uid":{{printf "%q" $o.uid}}}{{end}}]},"spec":'
        + pod("$x.spec")[:-1]
        + ',"type":{{if $x.spec.type}}{{printf "%q" $x.spec.type}}{{else}}null{{end}},"replicas":'
        + scalar("$x.spec.replicas")
        + ',"tls":[{{range $i,$t := $x.spec.tls}}{{if $i}},{{end}}{"secretName":'
        + present("$t.secretName")
        + '}{{end}}],"template":{"spec":'
        + pod("$x.spec.template.spec")
        + '}},"status":{"readyReplicas":'
        + scalar("$x.status.readyReplicas")
        + ',"desiredNumberScheduled":'
        + scalar("$x.status.desiredNumberScheduled")
        + ',"numberReady":'
        + scalar("$x.status.numberReady")
        + "}}{{end}}]}"
    )
    kinds = (
        "pods",
        "deployments",
        "statefulsets",
        "daemonsets",
        "services",
        "ingresses",
        "networkpolicies",
    )
    for ns in a.namespaces:
        n, eid = r.read(
            "namespace.get",
            ns,
            lambda: kube(
                "get",
                "namespace",
                ns,
                "-o",
                'go-template={{printf "%q" .metadata.uid}}',
            ),
        )
        if isinstance(n, str):
            namespace_uids[ns] = n
            r.observe(eid, {"uid": n})
        for kind in kinds:
            rows, complete = r.listing(
                "get." + kind,
                ns,
                lambda _: kube(
                    "get",
                    kind,
                    "--namespace",
                    ns,
                    "--chunk-size=100",
                    "-o",
                    "go-template=" + template,
                ),
                lambda d: d["items"],
            )
            if kind == "networkpolicies" and not rows and complete:
                r.finding(
                    "network-policy-coverage",
                    ns,
                    "manual_review",
                    r.operations[-1]["evidence"],
                    "No NetworkPolicy observed.",
                    "Review network plugin and workload isolation.",
                )
            for x, eid in rows:
                meta = obj(x.get("metadata"))
                spec = obj(x.get("spec"))
                status = obj(x.get("status"))
                pod = (
                    (
                        spec
                        if kind == "pods"
                        else obj(obj(spec.get("template")).get("spec"))
                    )
                    if kind in ("pods", "deployments", "statefulsets", "daemonsets")
                    else {}
                )
                attrs = {
                    "owners": [
                        o.get("uid")
                        for o in items(meta.get("ownerReferences"))
                        if isinstance(o, dict)
                    ]
                }
                if kind == "services":
                    attrs["exposure_type"] = spec.get("type")
                if kind == "ingresses":
                    attrs["tls_reference_present"] = any(
                        bool(obj(t).get("secretName")) for t in items(spec.get("tls"))
                    )
                if pod:
                    for flag in ("hostNetwork", "hostPID", "hostIPC"):
                        attrs[flag] = pod.get(flag)
                    attrs["containers"] = [
                        {
                            "security": selected(
                                obj(c.get("securityContext")),
                                {
                                    "privileged": "privileged",
                                    "escalation": "allowPrivilegeEscalation",
                                },
                            ),
                            "requests_present": bool(
                                obj(c.get("resources")).get("requests")
                            ),
                            "limits_present": bool(
                                obj(c.get("resources")).get("limits")
                            ),
                            "readiness_present": bool(c.get("readinessProbe")),
                            "liveness_present": bool(c.get("livenessProbe")),
                        }
                        for c in items(pod.get("containers"))
                        + items(pod.get("initContainers"))
                        if isinstance(c, dict)
                    ]
                desired = spec.get("replicas", status.get("desiredNumberScheduled"))
                ready = status.get("readyReplicas", status.get("numberReady"))
                attrs.update({"desired": desired, "ready": ready})
                rid = r.resource(meta.get("uid"), kind, ns, attrs, eid)
                for flag in ("hostNetwork", "hostPID", "hostIPC"):
                    if pod:
                        r.finding(
                            flag,
                            rid,
                            "fail"
                            if pod.get(flag) is True
                            else "pass"
                            if pod.get(flag) is False
                            else "manual_review",
                            eid,
                            flag + " isolation setting.",
                            "Review explicit security settings and admission defaults.",
                        )
                for index, c in enumerate(attrs.get("containers", [])):
                    for flag, value in c["security"].items():
                        r.finding(
                            f"container-{index}-{flag}",
                            rid,
                            "fail"
                            if value is True
                            else "pass"
                            if value is False
                            else "manual_review",
                            eid,
                            "Container " + flag + " setting.",
                            "Review security context and admission defaults.",
                        )
                    if not all(
                        c[k]
                        for k in (
                            "requests_present",
                            "limits_present",
                            "readiness_present",
                            "liveness_present",
                        )
                    ):
                        r.finding(
                            f"container-{index}-operability",
                            rid,
                            "manual_review",
                            eid,
                            "Missing resource bounds or probes.",
                            "Review container role and required probes/resources.",
                        )
                if type(desired) is int and type(ready) is int and ready < desired:
                    r.finding(
                        "readiness",
                        rid,
                        "manual_review",
                        eid,
                        "Ready count below desired at observation time.",
                        "Investigate rollout state and availability requirements.",
                    )
    r.observed["namespace_uids"] = namespace_uids


def main():
    p = parser("kubernetes")
    for name in ("context", "expected-server", "expected-principal"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--namespaces", nargs="+", required=True)
    return run(
        "kubernetes",
        p,
        collect,
        SOURCE,
        [
            "Nodes, RBAC, Secrets, ConfigMaps, logs and runtime scans",
            "Effective network isolation and admission defaults",
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
