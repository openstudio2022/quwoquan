from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import domain_governance
from quwoquan_ops.cli.lib import public_domain_tls


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
            self.assertEqual(
                domain_governance._dns_over_https("alpha.quwoquan.com", "A"),
                ["127.0.0.1"],
            )

        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Accept"), "application/dns-json")
        self.assertIn("name=alpha.quwoquan.com", request.full_url)
        self.assertIn("type=A", request.full_url)

    def test_dns_over_https_treats_nxdomain_as_empty_evidence(self) -> None:
        with mock.patch.object(
            domain_governance.urllib.request,
            "urlopen",
            return_value=_Response({"Status": 3}),
        ):
            self.assertEqual(
                domain_governance._dns_over_https(
                    "missing.quwoquan.com",
                    "AAAA",
                ),
                [],
            )

    def test_dns_apply_requires_the_dedicated_provisioning_token(self) -> None:
        with mock.patch.dict(domain_governance.os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                domain_governance.DomainGovernanceError,
                "QWQ_DNS_PROVISIONING_API_TOKEN",
            ):
                domain_governance.apply_dns_records()

    def test_acme_rejects_the_broader_dns_provisioning_token(self) -> None:
        with mock.patch.dict(
            public_domain_tls.os.environ,
            {
                "QWQ_ACME_ACCOUNT_EMAIL": "acme@example.invalid",
                "QWQ_DNS_PROVISIONING_API_TOKEN": "must-not-be-reused",
            },
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


if __name__ == "__main__":
    unittest.main()
