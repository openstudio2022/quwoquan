#!/usr/bin/env python3
"""域名治理门禁的 local_contract：公共 authority 识别与私有信任禁令。"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO_ROOT / "quwoquan_ops" / "gate" / "verify_domain_governance.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_domain_governance", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DomainGovernanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def test_public_authority_matches_https_and_wss_with_optional_port(self) -> None:
        for value in (
            "https://quwoquan.com",
            "https://api.quwoquan.com",
            "wss://rtc.quwoquan.com",
            "https://api.quwoquan.com:8443",
        ):
            with self.subTest(value=value):
                self.assertRegex(value, self.verifier.PUBLIC_AUTHORITY_RE)

    def test_public_authority_does_not_match_other_domains(self) -> None:
        for value in ("https://example.com", "https://quwoquan.cn"):
            with self.subTest(value=value):
                self.assertIsNone(self.verifier.PUBLIC_AUTHORITY_RE.search(value))

    def test_generic_media_variable_is_matched_on_exact_token_boundary(self) -> None:
        self.assertIsNotNone(
            self.verifier.GENERIC_PUBLIC_MEDIA_RE.search("MEDIA_BASE_URL")
        )
        # 边界断言存在的意义：更具体的分环境变量不该被泛化变量的禁令误伤。
        self.assertIsNone(
            self.verifier.GENERIC_PUBLIC_MEDIA_RE.search("ALPHA_MEDIA_BASE_URL")
        )
        self.assertIsNone(
            self.verifier.GENERIC_PUBLIC_MEDIA_RE.search("MEDIA_BASE_URL_SUFFIX")
        )

    def test_retired_authorities_are_declared_as_a_closed_set(self) -> None:
        # 不复制退役 authority 的字面量：本文件同样落在该门禁的全仓库扫描面内，
        # 写出来就会让 companion 自己变成违规。只校验禁令集合的形态与规模。
        tokens = self.verifier.RETIRED_AUTHORITY_TOKENS
        self.assertEqual(len(tokens), 3)
        for token in tokens:
            with self.subTest(token=token):
                self.assertRegex(token, r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")

    def test_private_trust_escapes_stay_forbidden(self) -> None:
        for token in (
            "badCertificateCallback",
            "ssl._create_unverified_context",
            "SecurityContext.defaultContext.setTrustedCertificatesBytes",
        ):
            self.assertIn(token, self.verifier.PRIVATE_TRUST_TOKENS)

    def test_local_managed_trust_has_a_closed_owner_set(self) -> None:
        # 本地受管信任只允许这几个 owner 持有，否则等于开放任意私有信任注入。
        self.assertEqual(
            self.verifier.LOCAL_MANAGED_TRUST_OWNERS,
            {
                "quwoquan_ops/cli/lib/local_environment_object_storage.py",
                "quwoquan_ops/cli/stackctl.py",
                "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml",
            },
        )
        for owner in self.verifier.LOCAL_MANAGED_TRUST_OWNERS:
            with self.subTest(owner=owner):
                self.assertTrue((REPO_ROOT / owner).exists())

    def test_probe_edge_address_is_globally_routable_but_not_production(self) -> None:
        # 探针要过 is_global 校验，所以不能退回 RFC 5737 文档地址。
        self.assertEqual(self.verifier.GATE_PROBE_EDGE_ADDRESS, "192.88.99.1")

    def test_runtime_authority_scope_excludes_non_runtime_trees(self) -> None:
        for part in ("/test/", "/tests/", "/generated/", "/contracts/"):
            self.assertIn(part, self.verifier.RUNTIME_AUTHORITY_EXCLUDED_PARTS)
        self.assertIn("quwoquan_app/lib/", self.verifier.RUNTIME_AUTHORITY_PREFIXES)


if __name__ == "__main__":
    unittest.main()
