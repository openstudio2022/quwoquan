from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib import immutable_configuration_composition as composition


class ImmutableConfigurationCompositionContractTest(unittest.TestCase):
    """The local runtime has one digest identity for all packaged configs."""

    def test_digest_is_derived_from_validated_service_packages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            services = ("content-service", "user-service")
            versions = {
                "content-service": "sha256:" + "1" * 64,
                "user-service": "sha256:" + "2" * 64,
            }
            for service in services:
                package = root / service
                config = package / "config/config.yaml"
                config.parent.mkdir(parents=True)
                config.write_text(f"service: {service}\n", encoding="utf-8")
                raw_digest = "sha256:" + hashlib.sha256(config.read_bytes()).hexdigest()
                (package / "provenance.json").write_text(
                    json.dumps(
                        {
                            "service": service,
                            "environment": "gamma",
                            "configVersion": versions[service],
                            "digests": {"config": raw_digest},
                        }
                    ),
                    encoding="utf-8",
                )

            with mock.patch.object(
                composition,
                "service_deployment_package_dir",
                side_effect=lambda _environment, service, target="": root / service,
            ):
                digest = composition.packaged_configuration_digest(
                    "gamma",
                    target="gamma-local",
                    services=services,
                )

            self.assertRegex(digest, r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(
                digest,
                composition.immutable_configuration_digest(versions),
            )

    def test_config_content_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "content-service"
            config = package / "config/config.yaml"
            config.parent.mkdir(parents=True)
            config.write_text("drifted: true\n", encoding="utf-8")
            (package / "provenance.json").write_text(
                json.dumps(
                    {
                        "service": "content-service",
                        "environment": "gamma",
                        "configVersion": "sha256:" + "1" * 64,
                        "digests": {"config": "sha256:" + "0" * 64},
                    }
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    composition,
                    "service_deployment_package_dir",
                    return_value=package,
                ),
                self.assertRaisesRegex(ValueError, "config digest mismatch"),
            ):
                composition.packaged_configuration_digest(
                    "gamma",
                    services=("content-service",),
                )


if __name__ == "__main__":
    unittest.main()
