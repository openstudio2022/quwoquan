from __future__ import annotations

import socket
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import domain_governance
from quwoquan_ops.cli.lib import dns_provider, public_domain_tls


class AcmeCredentialProjectionLocalContractTest(unittest.TestCase):
    """ACME challenge 凭据经策略声明投影为客户端变量，模块不写死厂商。"""

    def test_projection_follows_policy_declaration(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（凭据投影由策略声明）"""
        policy = domain_governance._policy()
        acme = policy.get("acme") or {}
        projected = public_domain_tls._challenge_credential_environment(
            policy, acme, "key-id:key-secret"
        )
        self.assertEqual(
            set(projected), set((acme.get("credentialEnvironment") or {}))
        )
        self.assertIn("key-id", projected.values())
        self.assertIn("key-secret", projected.values())

    def test_single_part_credential_fails_closed(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（凭据形状不合即 fail closed）"""
        policy = domain_governance._policy()
        acme = policy.get("acme") or {}
        with self.assertRaisesRegex(
            public_domain_tls.PublicDomainTlsError, "accessKeyId"
        ):
            public_domain_tls._challenge_credential_environment(
                policy, acme, "only-one"
            )

    def test_credential_shape_is_owned_by_the_provider_not_the_tls_module(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（服务商单点隔离）"""
        source = Path(public_domain_tls.__file__).read_text(encoding="utf-8")
        for vendor_token in ("keyId", "keySecret", "ALICLOUD", "partition("):
            self.assertNotIn(
                vendor_token,
                source,
                f"{vendor_token} 是服务商知识，必须留在 DnsProvider 实现里",
            )

    def test_unknown_credential_part_fails_closed(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（未知凭据部件即 fail closed）"""
        policy = domain_governance._policy()
        with self.assertRaisesRegex(
            public_domain_tls.PublicDomainTlsError, "unknown credential part"
        ):
            public_domain_tls._challenge_credential_environment(
                policy,
                {"credentialEnvironment": {"SOME_VAR": "notAPart"}},
                "key-id:key-secret",
            )

class AcmeClientSurfaceLocalContractTest(unittest.TestCase):
    """签发命令跟随 lego 现役 CLI，且不依赖注册邮箱。"""

    def _profile(self) -> dict[str, str]:
        _, _, profile = public_domain_tls.tls_profile("prod-hosted")
        return profile

    def _command(self) -> list[str]:
        return public_domain_tls._lego_command(
            "/usr/local/bin/lego",
            acme=domain_governance._policy().get("acme") or {},
            profile=self._profile(),
            lego_root=Path("/tmp/lego"),
        )

    def test_options_follow_the_subcommand(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（ACME 客户端调用面单轨）"""
        command = self._command()
        self.assertEqual(command[0], "/usr/local/bin/lego")
        # lego v5 起全局位只剩日志与配置，签发选项一律归属子命令。
        self.assertEqual(command[1], "run")
        self.assertLess(command.index("run"), command.index("--accept-tos"))
        self.assertLess(command.index("run"), command.index("--domains"))

    def test_issuance_does_not_require_a_registration_mailbox(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（签发不依赖邮箱）"""
        command = self._command()
        self.assertNotIn("--email", command)
        self.assertNotIn("-m", command)

    def test_issuance_is_idempotent_across_first_issue_and_renewal(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（首签与续期同一调用）"""
        # v5 取消了 renew 子命令：run 依据 --renew-days 自行判定是否需要续期，
        # 因此调用面不得再按证书是否已存在分叉。
        command = self._command()
        self.assertNotIn("renew", command)
        self.assertIn("--renew-days", command)
        self.assertNotIn("--days", command)

    def test_policy_declares_no_account_mailbox(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（策略不再声明邮箱输入）"""
        acme = domain_governance._policy().get("acme") or {}
        self.assertNotIn("accountEmailEnv", acme)


class ProductionCertificateOwnershipLocalContractTest(unittest.TestCase):
    def test_production_certificate_is_owned_automation_not_external(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（生产证书为自有自动化）"""
        profile_name, kind, profile = public_domain_tls.tls_profile("prod-hosted")
        self.assertEqual(profile_name, "public-ca-prod")
        self.assertEqual(kind, "dns-01-public-ca")
        self.assertNotIn("certificateAutomation", profile)
        self.assertEqual(profile["apex"], "quwoquan.com")
        self.assertEqual(profile["wildcard"], "*.quwoquan.com")


class _FakeLiveZone:
    """按名字/类型回放一份可控的公网答案，供 verify 在离线下走完全部判定分支。"""

    def __init__(self, answers: dict[tuple[str, str], list[str]]) -> None:
        self._answers = answers

    def __call__(self, name: str, record_type: str) -> dict[str, list[str]]:
        rows = self._answers.get((name, record_type.upper()), [])
        return {"https://resolver.test/resolve": list(rows)}


def _healthy_answers() -> dict[tuple[str, str], list[str]]:
    """让所有 zone 处于「现网与计划一致」的状态。

    生产 zone 的地址记录取决于是否注入 edge 地址，但它的 CAA 与邮件记录不依赖地址，
    所以每个 zone 都要给出这几条，否则 fixture 会把「未注入」误装成「现网缺记录」。
    """
    policy = domain_governance._policy()
    answers: dict[tuple[str, str], list[str]] = {}
    for zone in domain_governance.dns_zones():
        if str(zone.get("addressing")) == "loopback":
            for name in domain_governance.zone_record_names(zone):
                if name.startswith("*."):
                    continue
                answers[(name, "A")] = ["127.0.0.1"]
                answers[(name, "AAAA")] = ["::1"]
        apex = str(zone["apex"])
        answers[(apex, "CAA")] = [
            dns_provider.caa_value(entry)
            for entry in domain_governance.caa_profile(zone, policy)
        ]
        guard = (policy.get("mailGuards") or {})[str(zone["mailGuard"])]
        answers[(apex, "MX")] = ["0 ."] if guard.get("nullMx") else []
        answers[(apex, "TXT")] = [str(guard["spf"])]
        answers[(f"_dmarc.{apex}", "TXT")] = [str(guard["dmarc"])]
    return answers


class VerifyLiveStateLocalContractTest(unittest.TestCase):
    """verify 的判定分支在离线回放下逐条可证，不依赖真实公网。"""

    def _verify(
        self, answers: dict[tuple[str, str], list[str]], *, prod_edge: str = ""
    ) -> dict[str, object]:
        with (
            mock.patch.object(
                domain_governance,
                "_dns_over_https_by_resolver",
                new=_FakeLiveZone(answers),
            ),
            mock.patch.object(
                domain_governance,
                "_topology_hosts",
                return_value=[],
            ),
            mock.patch.object(
                domain_governance.socket,
                "gethostbyaddr",
                side_effect=socket.herror("no PTR"),
            ),
        ):
            return domain_governance.verify_live_state(
                verify_tls=False,
                prod_edge_address=prod_edge or domain_governance.EDGE_ADDRESS_ABSENT,
            )

    def test_absent_edge_address_reports_incomplete_not_ok(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（未核对的 scope 不冒充通过）"""
        payload = self._verify(_healthy_answers())
        self.assertEqual(payload["status"], "incomplete")
        self.assertEqual([item["scope"] for item in payload["pending"]], ["prod"])
        self.assertEqual(payload["issues"], [])

    def test_deny_all_zone_with_a_permissive_caa_is_blocked(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（CAA 反向校验，越权签发被拦）"""
        answers = _healthy_answers()
        answers[("alpha.quwoquan.com", "CAA")] = [
            *answers[("alpha.quwoquan.com", "CAA")],
            '0 issue "letsencrypt.org"',
        ]
        with self.assertRaises(domain_governance.DomainGovernanceError) as caught:
            self._verify(answers)
        self.assertIn("outside its profile", str(caught.exception))

    def test_issue_is_not_satisfied_by_issuewild_alone(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（CAA 精确匹配而非子串）"""
        answers = _healthy_answers()
        answers[("alpha.quwoquan.com", "CAA")] = [
            row
            for row in answers[("alpha.quwoquan.com", "CAA")]
            if " issue " not in row
        ]
        with self.assertRaises(domain_governance.DomainGovernanceError) as caught:
            self._verify(answers)
        self.assertIn("CAA must publish 0 issue ;", str(caught.exception))

    def test_missing_dmarc_is_blocked(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（DMARC 缺失即阻断）"""
        answers = _healthy_answers()
        answers[("_dmarc.alpha.quwoquan.com", "TXT")] = []
        with self.assertRaises(domain_governance.DomainGovernanceError) as caught:
            self._verify(answers)
        self.assertIn("_dmarc.alpha.quwoquan.com", str(caught.exception))

    def test_address_outside_the_plan_is_blocked(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（计划外地址即漂移）"""
        answers = _healthy_answers()
        answers[("alpha.quwoquan.com", "A")] = ["127.0.0.1", "203.0.113.5"]
        with self.assertRaises(domain_governance.DomainGovernanceError) as caught:
            self._verify(answers)
        self.assertIn("outside the canonical", str(caught.exception))

    def test_reverse_lookup_failure_is_reported_instead_of_silently_passing(
        self,
    ) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（查询失败不得降级为通过）"""
        answers = _healthy_answers()
        with (
            mock.patch.object(
                domain_governance,
                "_dns_over_https_by_resolver",
                new=_FakeLiveZone(answers),
            ),
            mock.patch.object(
                domain_governance, "_topology_hosts", return_value=[]
            ),
            mock.patch.object(
                domain_governance.socket,
                "gethostbyaddr",
                side_effect=OSError("resolver unreachable"),
            ),
            self.assertRaises(domain_governance.DomainGovernanceError) as caught,
        ):
            domain_governance.verify_live_state(
                verify_tls=False,
                prod_edge_address=domain_governance.EDGE_ADDRESS_ABSENT,
            )
        self.assertIn("reverse DNS lookup failed", str(caught.exception))

    def test_tls_coverage_includes_every_declared_profile_target(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（证书覆盖面由策略派生）"""
        targets = domain_governance.tls_verifiable_targets()
        self.assertIn("prod-hosted", targets)
        self.assertIn("prod-sim", targets)
        for target in ("alpha-local", "beta-local", "gamma-local"):
            self.assertIn(target, targets)


class AliyunProviderTranslationLocalContractTest(unittest.TestCase):
    """中立记录与阿里云 API 参数之间的翻译面。"""

    def setUp(self) -> None:
        self.provider = dns_provider.AliyunDnsProvider(
            credential="test-key-id:test-key-secret", zone="quwoquan.com"
        )

    def test_apex_is_projected_to_the_at_marker(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（apex 相对名投影）"""
        self.assertEqual(
            dns_provider.relative_name("quwoquan.com", "quwoquan.com"), "@"
        )
        self.assertEqual(
            dns_provider.relative_name("www.quwoquan.com", "quwoquan.com"), "www"
        )
        with self.assertRaises(dns_provider.DnsProviderError):
            dns_provider.relative_name("example.org", "quwoquan.com")

    def test_caa_identity_is_shared_between_expectation_and_live_shape(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（CAA 两侧身份归一）"""
        entry = {"flags": 0, "tag": "issue", "value": "letsencrypt.org"}
        expected = {"type": "CAA", "name": "quwoquan.com", "data": entry}
        live = {
            "type": "CAA",
            "name": "quwoquan.com",
            "content": dns_provider.caa_value(entry),
        }
        self.assertEqual(
            dns_provider.record_identity(expected),
            dns_provider.record_identity(live),
        )

    def test_unparsable_caa_text_is_absent_not_empty(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（解析失败不塌陷为空值）"""
        self.assertIsNone(dns_provider.parse_caa_text("not-a-caa"))
        self.assertEqual(
            dns_provider.parse_caa_text('0 issue "letsencrypt.org"'),
            (0, "issue", "letsencrypt.org"),
        )

    def test_mx_priority_is_carried_into_provider_arguments(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（null MX 优先级如实下发）"""
        calls: list[dict[str, str]] = []

        def _capture(action: str, **arguments: str) -> dict[str, object]:
            calls.append({"action": action, **arguments})
            return {"RecordId": "new-id"}

        with mock.patch.object(self.provider, "_call", side_effect=_capture):
            self.provider.create_record(
                {
                    "type": "MX",
                    "name": "quwoquan.com",
                    "content": ".",
                    "priority": 0,
                    "ttl": 3600,
                }
            )
        self.assertEqual(calls[0]["RR"], "@")
        self.assertEqual(calls[0]["Type"], "MX")
        self.assertEqual(calls[0]["Priority"], "0")

    def test_signature_is_stable_and_percent_encoded(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（签名可复算）"""
        parameters = {"Action": "DescribeDomainRecords", "DomainName": "quwoquan.com"}
        first = self.provider._signature(dict(parameters))
        second = self.provider._signature(dict(reversed(list(parameters.items()))))
        self.assertEqual(first, second)
        self.assertEqual(dns_provider._percent_encode("*"), "%2A")
        self.assertEqual(dns_provider._percent_encode("a b"), "a%20b")

    def test_malformed_credential_fails_closed(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（凭据形状不合即 fail closed）"""
        with self.assertRaisesRegex(dns_provider.DnsProviderError, "accessKeyId"):
            dns_provider.AliyunDnsProvider(credential="no-separator", zone="x.com")

    def test_unregistered_kind_fails_closed(self) -> None:
        """spec_ref: environment-topology-and-packaging GWT-001（未注册服务商即 fail closed）"""
        with self.assertRaisesRegex(dns_provider.DnsProviderError, "unsupported"):
            dns_provider.provider_for_kind("some-other-dns")


if __name__ == "__main__":
    unittest.main()
