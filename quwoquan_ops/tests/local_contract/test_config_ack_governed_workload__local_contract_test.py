from __future__ import annotations

# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-006

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RENDER_PATH = ROOT / "quwoquan_ops/cli/prod/render_prod_plane_stack.py"


def _load_renderer():
    spec = importlib.util.spec_from_file_location("render_prod_plane_stack_ack", RENDER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class GovernedConfigAckWorkloadContractTest(unittest.TestCase):
    def test_every_rendered_governed_workload_starts_machine_config_ack(self) -> None:
        renderer = _load_renderer()
        for service in sorted(renderer.RUNTIME_LOG_EXPORT_SERVICES):
            with self.subTest(service=service):
                if service == "platform-ops-service":
                    source_root = ROOT / "quwoquan_service/control-plane/platform-ops/cmd/api"
                else:
                    source_root = ROOT / "quwoquan_service/services" / service / "cmd/api"
                sources = list(source_root.glob("*.go"))
                self.assertTrue(sources, f"{service} must have a checked-in API entrypoint")
                source_text = "\n".join(path.read_text(encoding="utf-8") for path in sources)
                self.assertTrue(
                    "StartReleaseConfigAttestation" in source_text
                    or "RunConfigSyncLoop" in source_text,
                    f"{service} is rendered as governed but does not start machine config ACK",
                )


if __name__ == "__main__":
    unittest.main()
