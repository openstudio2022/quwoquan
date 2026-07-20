import importlib.util
import sys
import unittest
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = APP_ROOT / "scripts/device/verify_welcome_motion_frames.py"
GOLDEN_ROOT = APP_ROOT / "test/local_contract/ui/welcome/goldens"


def _load_probe():
    spec = importlib.util.spec_from_file_location("welcome_motion_probe", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class StartupWelcomeMotionProbeContractTest(unittest.TestCase):
    def test_bloom_v2_goldens_pass_frame_geometry_and_wave_probe(self) -> None:
        probe = _load_probe()
        names = (
            "full_open",
            "gathering_25",
            "gathering_50",
            "bud_peak",
            "blooming_25",
            "blooming_50",
            "blooming_75",
            "final_open",
        )
        report = probe.analyze_sequence(
            [GOLDEN_ROOT / f"welcome_flower_{name}.png" for name in names]
        )

        self.assertTrue(report["passed"], report)
        self.assertEqual(report["motionSpec"], "petal_bloom")
        self.assertTrue(report["gatheringOrderValid"])
        self.assertTrue(report["bloomingOrderValid"])
        self.assertEqual(report["monotonicViolations"], [])
        self.assertLessEqual(
            report["maxMedianAspectRatioDrift"], report["aspectDriftLimit"]
        )
        self.assertGreaterEqual(
            report["bloomMidWaveSpread"], report["minimumWaveSpread"]
        )
        first_petal = report["frames"][1]["petals"][0]
        self.assertIn("oriented_minor", first_petal)
        self.assertIn("oriented_major", first_petal)
        self.assertIn("center_radius", first_petal)
        self.assertIn("frame_displacement", first_petal)


if __name__ == "__main__":
    unittest.main()
