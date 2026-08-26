from __future__ import annotations

import json
import os
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import domain_governance
from quwoquan_ops.cli.lib import dns_provider, public_domain_tls


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self._raw = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._raw


class DomainGovernanceDnsLocalContractTest(unittest.TestCase):
    def test_dns_over_https_reads_public_answer_without_system_resolver(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（公网解析证据不经本机解析器）"""
        with mock.patch.object(
            domain_governance.urllib.request,
            "urlopen",
            return_value=_Response(
                {
                    "Status": 0,
                    "Answer": [
                        {"data": "127.0.0.1"},
                        {"data": "127.0.0.1"},
                    ],
                }
            ),
        ) as urlopen:
            answers = domain_governance._dns_over_https_by_resolver(
                "alpha.quwoquan.com", "A"
            )

        resolvers = domain_governance._resolvers(domain_governance._policy())
        self.assertEqual(sorted(answers), sorted(resolvers))
        for rows in answers.values():
            self.assertEqual(rows, ["127.0.0.1"])

        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Accept"), "application/dns-json")
        self.assertIn("name=alpha.quwoquan.com", request.full_url)
        self.assertIn("type=A", request.full_url)

    def test_dns_over_https_treats_nxdomain_as_empty_evidence(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（NXDOMAIN 是在场为空而非失败）"""
        with mock.patch.object(
            domain_governance.urllib.request,
            "urlopen",
            return_value=_Response({"Status": 3}),
        ):
            answers = domain_governance._dns_over_https_by_resolver(
                "missing.quwoquan.com",
                "AAAA",
            )
        self.assertTrue(answers)
        for rows in answers.values():
            self.assertEqual(rows, [])

    def test_public_resolvers_stay_independent_of_the_authoritative_vendor(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（两个相互独立的公共解析器）"""
        # spec_ref: specs/feature-tree/runtime/system-topology-and-networking/spec.md#sit-001.t2
        policy = domain_governance._policy()
        resolvers = domain_governance._resolvers(policy)
        self.assertGreaterEqual(len(resolvers), 2)
        provider_class = dns_provider.provider_for_kind(
            str((policy.get("dnsProvider") or {}).get("kind") or "")
        )
        for resolver in resolvers:
            hostname = urllib.parse.urlsplit(resolver).hostname or ""
            for token in provider_class.vendor_hostname_tokens:
                self.assertNotIn(token, hostname.lower())

    def test_dns_apply_requires_the_dedicated_provisioning_token(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（provisioning 与 challenge 双凭据隔离）"""
        with mock.patch.dict(domain_governance.os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                domain_governance.DomainGovernanceError,
                "QWQ_DNS_PROVISIONING_API_TOKEN",
            ):
                domain_governance.apply_dns_records()

    def test_acme_rejects_the_broader_dns_provisioning_token(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（challenge 侧拒绝更宽的 provisioning 凭据）"""
        with mock.patch.dict(
            public_domain_tls.os.environ,
            {"QWQ_DNS_PROVISIONING_API_TOKEN": "must-not-be-reused"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                public_domain_tls.PublicDomainTlsError,
                "QWQ_ACME_DNS_API_TOKEN",
            ):
                public_domain_tls.issue_certificate("prod-sim")

    def test_local_managed_certificate_uses_topology_sans_without_protected_inputs(
        self,
    ) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（本地 SAN 由 topology 派生）"""
        # spec_ref: specs/feature-tree/runtime/system-topology-and-networking/spec.md#sit-001.t2
        with tempfile.TemporaryDirectory() as temporary:
            deploy_root = Path(temporary) / "deploy"
            with mock.patch.dict(
                os.environ,
                {
                    "PATH": os.environ.get("PATH", ""),
                    "QWQ_DEPLOY_WORK_ROOT": str(deploy_root),
                },
                clear=True,
            ):
                evidence = public_domain_tls.issue_certificate("alpha-local")
                verified = public_domain_tls.verify_certificate("alpha-local")

            self.assertEqual(evidence["profile"], "local-managed")
            self.assertEqual(evidence["kind"], "local-managed")
            self.assertEqual(evidence["sans"], verified["sans"])
            self.assertIn("api.alpha.quwoquan.com", evidence["sans"])
            self.assertIn("cdn.alpha.quwoquan.com", evidence["sans"])
            self.assertTrue(Path(evidence["rootCertificate"]).is_file())


class DnsProviderNeutralityLocalContractTest(unittest.TestCase):
    """DNS 写入面必须经中立 provider 接口，策略是唯一的厂商选择点。"""

    def test_policy_names_a_registered_neutral_provider(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（服务商由 dnsProvider.kind 单点选择）"""
        kind = str(
            (domain_governance._policy().get("dnsProvider") or {}).get("kind") or ""
        )
        self.assertIn(kind, dns_provider.registered_kinds())

    def test_unregistered_provider_kind_fails_closed(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（未注册服务商即 fail closed）"""
        with self.assertRaisesRegex(dns_provider.DnsProviderError, "unsupported"):
            dns_provider.build_provider(
                kind="no-such-provider",
                credential="id:secret",
                zone="quwoquan.com",
            )

    def test_plan_records_carry_no_vendor_only_fields(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（计划记录保持供应商中立）

        用白名单而非黑名单，且必须带上注入地址后的生产记录——只查非生产记录会漏掉
        只在生产路径上产生的字段。
        """
        neutral_fields = {"type", "name", "content", "data", "ttl", "priority"}
        records = [
            *domain_governance.desired_dns_records(
                domain_governance.EDGE_ADDRESS_ABSENT
            ),
            *domain_governance.desired_dns_records("1.2.3.4"),
        ]
        prod_names = {
            str(record["name"])
            for record in records
            if str(record.get("content")) == "1.2.3.4"
        }
        self.assertTrue(prod_names, "生产记录必须进入这条守卫的取样范围")
        for record in records:
            self.assertEqual(set(record) - neutral_fields, set(), record)

    def test_relative_name_folds_apex_and_wildcard(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（apex 与 wildcard 相对名投影）"""
        self.assertEqual(
            dns_provider.relative_name("quwoquan.com", "quwoquan.com"), "@"
        )
        self.assertEqual(
            dns_provider.relative_name("api.quwoquan.com", "quwoquan.com"), "api"
        )
        self.assertEqual(
            dns_provider.relative_name("*.sim.quwoquan.com", "quwoquan.com"),
            "*.sim",
        )
        with self.assertRaises(dns_provider.DnsProviderError):
            dns_provider.relative_name("api.example.com", "quwoquan.com")

    def test_caa_wire_value_is_shared_by_provider_and_evidence(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（CAA 线上形状单一）"""
        self.assertEqual(
            dns_provider.caa_value({"flags": 0, "tag": "issue", "value": "x.org"}),
            '0 issue "x.org"',
        )

    def test_provider_credential_must_carry_both_key_parts(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（凭据形状不合即 fail closed）"""
        with self.assertRaisesRegex(dns_provider.DnsProviderError, "accessKeyId"):
            dns_provider.build_provider(
                kind="aliyun-dns",
                credential="only-one-part",
                zone="quwoquan.com",
            )


class ProdEdgeAddressLocalContractTest(unittest.TestCase):
    """生产 edge 地址是部署时事实：缺席与失败必须区分，且不入仓库。"""

    def _prod_zone(self) -> dict[str, object]:
        return next(
            zone
            for zone in domain_governance.dns_zones()
            if str(zone.get("scope")) == "prod"
        )

    def test_absent_edge_address_keeps_prod_records_absent_and_reported(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（未注入时生产地址缺席并显式 pending）"""
        with mock.patch.dict(domain_governance.os.environ, {}, clear=True):
            records = domain_governance.desired_dns_records()
            pending = domain_governance.pending_dns_scopes()
        self.assertEqual([item["scope"] for item in pending], ["prod"])
        # 断言覆盖生产 zone 的全部名字，而不是只看 apex：漏掉业务子域会让「地址记录
        # 缺席」这条守卫在最需要它的地方失效。
        prod_names = set(domain_governance.zone_record_names(self._prod_zone()))
        self.assertGreaterEqual(len(prod_names), 7)
        self.assertEqual(
            [
                (record["type"], record["name"])
                for record in records
                if record["type"] in {"A", "AAAA"}
                and str(record["name"]) in prod_names
            ],
            [],
        )

    def test_protected_variable_is_the_only_injection_path(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（生产地址只经受保护变量注入）"""
        policy = domain_governance._policy()
        variable = str(policy["prodEdgeAddressEnv"])
        self.assertEqual(variable, "QWQ_PROD_EDGE_IPV4")
        with mock.patch.dict(
            domain_governance.os.environ, {variable: "1.2.3.4"}, clear=True
        ):
            records = domain_governance.desired_dns_records()
            self.assertEqual(domain_governance.pending_dns_scopes(), [])
        addressed = {
            str(record["name"])
            for record in records
            if record["type"] == "A" and record["content"] == "1.2.3.4"
        }
        self.assertEqual(
            addressed,
            {
                name
                for name in domain_governance.zone_record_names(self._prod_zone())
                if not name.startswith("*.")
            },
        )

    def test_explicit_absence_never_falls_back_to_the_environment(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（缺席语义不随运行环境漂移）"""
        with mock.patch.dict(
            domain_governance.os.environ,
            {"QWQ_PROD_EDGE_IPV4": "1.2.3.4"},
            clear=True,
        ):
            records = domain_governance.desired_dns_records(
                domain_governance.EDGE_ADDRESS_ABSENT
            )
            pending = domain_governance.pending_dns_scopes(
                domain_governance.EDGE_ADDRESS_ABSENT
            )
        self.assertEqual([item["scope"] for item in pending], ["prod"])
        self.assertEqual(
            [record for record in records if record.get("content") == "1.2.3.4"], []
        )

    def test_injected_edge_address_covers_every_prod_topology_host(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（注入后覆盖全部 topology host）"""
        # spec_ref: specs/feature-tree/runtime/system-topology-and-networking/spec.md#sit-001.t1
        records = domain_governance.desired_dns_records("1.2.3.4")
        addressed = {
            str(record["name"])
            for record in records
            if record["type"] == "A" and record["content"] == "1.2.3.4"
        }
        self.assertEqual(
            addressed,
            {
                "quwoquan.com",
                "www.quwoquan.com",
                "api.quwoquan.com",
                "ops.quwoquan.com",
                "cdn.quwoquan.com",
                "rtc.quwoquan.com",
                "upload.quwoquan.com",
            },
        )
        self.assertEqual(domain_governance.pending_dns_scopes("1.2.3.4"), [])

    def test_private_and_malformed_edge_addresses_fail_closed(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（非全球可路由或格式非法即 fail closed）"""
        for candidate in ("192.168.1.10", "127.0.0.1", "not-an-ip", "::1"):
            with self.assertRaises(domain_governance.DomainGovernanceError):
                domain_governance.desired_dns_records(candidate)

    def test_production_apex_publishes_no_null_mx(self) -> None:
        """生产 apex 不显式拒收，将来接入收件无需先撤销一条 null MX。

        这里断言的是「没有 null MX」，不是「邮件可达」：本域名不收件，
        因此 CAA 与 DMARC 都不声明任何回报邮箱。

        spec_ref: environment-topology-and-packaging GWT-001（非生产 null MX，生产不拒收）
        """
        records = domain_governance.desired_dns_records("1.2.3.4")
        apex_mx = [
            record
            for record in records
            if record["type"] == "MX" and record["name"] == "quwoquan.com"
        ]
        apex_spf = [
            record
            for record in records
            if record["type"] == "TXT" and record["name"] == "quwoquan.com"
        ]
        self.assertEqual(apex_mx, [])
        self.assertEqual([record["content"] for record in apex_spf], ["v=spf1 -all"])
        sim_mx = [
            record
            for record in records
            if record["type"] == "MX" and record["name"] == "sim.quwoquan.com"
        ]
        self.assertEqual([record["content"] for record in sim_mx], ["."])

    def test_www_follows_the_apex_address_instead_of_a_cname(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（apexFollowers 共享地址记录而非 CNAME）"""
        self.assertEqual(
            [
                record
                for record in domain_governance.desired_dns_records("1.2.3.4")
                if record["type"] == "CNAME"
            ],
            [],
        )
        followers = {
            (str(record["name"]), str(record["content"]))
            for record in domain_governance.desired_dns_records("1.2.3.4")
            if record["type"] == "A" and record["name"] == "www.quwoquan.com"
        }
        self.assertEqual(followers, {("www.quwoquan.com", "1.2.3.4")})

    def test_absent_edge_address_also_withholds_the_apex_followers(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（apex 缺席时 follower 一同缺席）"""
        with mock.patch.dict(domain_governance.os.environ, {}, clear=True):
            records = domain_governance.desired_dns_records()
        self.assertEqual(
            [
                record
                for record in records
                if record["name"] == "www.quwoquan.com"
            ],
            [],
        )

    def test_record_ttl_respects_the_provider_floor(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（TTL 下限由 dnsProvider 策略拥有）"""
        floor = int(
            (domain_governance._policy().get("dnsProvider") or {})[
                "minimumTtlSeconds"
            ]
        )
        for record in domain_governance.desired_dns_records("1.2.3.4"):
            self.assertGreaterEqual(int(record["ttl"]), floor, record)


class ZoneIssuanceAndMailGuardLocalContractTest(unittest.TestCase):
    """每个 zone 都自证签发授权与邮件伪造防护，不靠继承 apex 的宽松默认值。"""

    def _zone(self, scope: str) -> dict[str, object]:
        for zone in domain_governance.dns_zones():
            if str(zone.get("scope")) == scope:
                return zone
        raise AssertionError(f"dnsZones is missing scope {scope}")

    def test_zones_without_public_certificates_deny_every_ca(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（不签发公共证书的 zone 发布 deny-all）"""
        records = domain_governance.desired_dns_records("1.2.3.4")
        for scope in ("alpha", "beta", "gamma"):
            apex = str(self._zone(scope)["apex"])
            issue_values = {
                str(record["data"]["value"])
                for record in records
                if record["type"] == "CAA"
                and record["name"] == apex
                and record["data"]["tag"] in {"issue", "issuewild"}
            }
            self.assertEqual(issue_values, {";"}, apex)

    def test_zones_with_public_certificates_authorize_only_the_chosen_ca(
        self,
    ) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（签发公共证书的 zone 用允许清单）"""
        records = domain_governance.desired_dns_records("1.2.3.4")
        for scope in ("sim", "prod"):
            apex = str(self._zone(scope)["apex"])
            issue_values = {
                str(record["data"]["value"])
                for record in records
                if record["type"] == "CAA"
                and record["name"] == apex
                and record["data"]["tag"] in {"issue", "issuewild"}
            }
            self.assertEqual(issue_values, {"letsencrypt.org"}, apex)

    def test_every_apex_publishes_a_rejecting_dmarc_policy(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（每个 apex 发布 p=reject 的 DMARC）"""
        records = domain_governance.desired_dns_records("1.2.3.4")
        dmarc = {
            str(record["name"]): str(record["content"])
            for record in records
            if record["type"] == "TXT" and record["name"].startswith("_dmarc.")
        }
        expected_names = {
            f"_dmarc.{zone['apex']}" for zone in domain_governance.dns_zones()
        }
        self.assertEqual(set(dmarc), expected_names)
        for name, value in dmarc.items():
            self.assertTrue(value.startswith("v=DMARC1"), name)
            self.assertIn("p=reject", value, name)

    def test_unknown_caa_profile_fails_closed(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（未知 caaProfile 即 fail closed）"""
        zone = dict(self._zone("prod"))
        zone["caa"] = "no-such-profile"
        with self.assertRaisesRegex(
            domain_governance.DomainGovernanceError, "caaProfile"
        ):
            domain_governance.caa_profile(zone)

    def test_mail_guard_without_dmarc_fails_closed(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（mail guard 缺 dmarc 即 fail closed）"""
        policy = json.loads(json.dumps(domain_governance._policy()))
        for guard in policy["mailGuards"].values():
            guard.pop("dmarc", None)
        with mock.patch.object(
            domain_governance, "_policy", return_value=policy
        ):
            with self.assertRaisesRegex(
                domain_governance.DomainGovernanceError, "dmarc"
            ):
                domain_governance.desired_dns_records("1.2.3.4")



if __name__ == "__main__":
    unittest.main()
