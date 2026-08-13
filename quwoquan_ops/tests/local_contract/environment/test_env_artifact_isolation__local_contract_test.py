from __future__ import annotations

import unittest

from quwoquan_ops.gate import verify_env_artifact_isolation as isolation


class EnvironmentArtifactIsolationContractTest(unittest.TestCase):
    def test_environment_subdomain_does_not_match_prod_suffix_hosts(self) -> None:
        hosts = isolation._referenced_hosts(
            'PUBLIC_WEB_BASE_URL: "https://alpha.quwoquan.com/path"\n'
        )
        self.assertEqual(hosts, {"alpha.quwoquan.com"})
        self.assertNotIn("quwoquan.com", hosts)
        self.assertNotIn("quwoquan.com", hosts)

    def test_url_and_bare_host_are_normalized_to_exact_hosts(self) -> None:
        self.assertEqual(
            isolation._normalized_host("https://quwoquan.com:443/path"),
            "quwoquan.com",
        )
        self.assertEqual(
            isolation._normalized_host("api.gamma.quwoquan.com:19000"),
            "api.gamma.quwoquan.com",
        )


if __name__ == "__main__":
    unittest.main()
