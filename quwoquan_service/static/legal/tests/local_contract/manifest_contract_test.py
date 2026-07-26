from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

import yaml


LEGAL_ROOT = Path(__file__).resolve().parents[2]


class LegalManifestContractTest(unittest.TestCase):
    def test_current_version_sources_and_digests_are_immutable(self) -> None:
        manifest = yaml.safe_load((LEGAL_ROOT / "manifest.yaml").read_text(encoding="utf-8"))
        current_version = str(manifest["currentVersion"])
        slugs: set[str] = set()
        for document in manifest["documents"]:
            self.assertEqual(str(document["version"]), current_version)
            self.assertNotIn(document["slug"], slugs)
            slugs.add(document["slug"])
            source = LEGAL_ROOT / document["source"]
            self.assertTrue(source.is_file(), source)
            digest = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
            self.assertEqual(digest, document["checksumSha256"])


if __name__ == "__main__":
    unittest.main()
