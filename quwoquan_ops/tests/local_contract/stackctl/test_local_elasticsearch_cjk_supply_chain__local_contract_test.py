from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib import local_elasticsearch_cjk_supply_chain as supply

_IMAGE_ID = (  # sha256("image")
    "sha256:6105d6cc76af400325e94d588ce511be5bfdbb73b437dc51eca43917d7a43e3d"
)


def completed(payload: object, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        [],
        returncode,
        json.dumps(payload) if not isinstance(payload, str) else payload,
        "",
    )


class LocalElasticsearchCjkSupplyChainContractTest(unittest.TestCase):
    def _manifest(self, digest: str) -> dict[str, object]:
        return {
            "schema": supply.SCHEMA,
            "elasticsearch": {
                "version": "8.13.4",
                "image": "example/elasticsearch@sha256:" + ("a" * 64),
                "license": "Elastic-License-2.0",
            },
            "plugins": [
                {
                    "name": name,
                    "version": "8.13.4",
                    "sourceUrl": f"https://example.test/{name}.zip",
                    "sourceRevision": "revision",
                    "sourceRepository": "https://example.test/source",
                    "sha256": digest,
                    "license": "Apache-2.0",
                    "licenseUrl": "https://example.test/LICENSE.txt",
                }
                for name in ("analysis-ik", "analysis-pinyin")
            ],
            "supportedArchitectures": ["amd64", "arm64"],
        }

    def test_checksum_tampering_and_missing_plugin_fail_closed(self) -> None:
        content = b"canonical plugin"
        digest = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archives = {}
            for name in supply.PLUGIN_NAMES:
                path = root / f"{name}.zip"
                path.write_bytes(content)
                archives[name] = path
            manifest = self._manifest(digest)
            self.assertEqual(
                set(supply.verify_plugin_archives(manifest, archives)),
                supply.PLUGIN_NAMES,
            )
            archives["analysis-ik"].write_bytes(b"tampered")
            with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                supply.verify_plugin_archives(manifest, archives)
            with self.assertRaisesRegex(RuntimeError, "archive is missing"):
                supply.verify_plugin_archives(
                    manifest,
                    {"analysis-pinyin": archives["analysis-pinyin"]},
                )

    def test_wrong_architecture_and_missing_plugin_fail_closed(self) -> None:
        manifest = self._manifest("a" * 64)
        wrong_arch = mock.Mock(
            side_effect=[
                completed([{"Id": _IMAGE_ID, "Architecture": "s390x"}]),
            ]
        )
        with self.assertRaisesRegex(RuntimeError, "architecture is unsupported"):
            supply.verify_runtime_image("image:test", manifest, runner=wrong_arch)

        missing_plugin = mock.Mock(
            side_effect=[
                completed([{"Id": _IMAGE_ID, "Architecture": "arm64"}]),
                completed("analysis-ik\n"),
            ]
        )
        with self.assertRaisesRegex(RuntimeError, "plugin closure is incomplete"):
            supply.verify_runtime_image(
                "image:test",
                manifest,
                runner=missing_plugin,
            )


if __name__ == "__main__":
    unittest.main()
