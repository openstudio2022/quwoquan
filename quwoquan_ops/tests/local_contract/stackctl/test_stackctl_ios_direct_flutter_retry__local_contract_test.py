import tempfile
import unittest
from pathlib import Path

from quwoquan_ops.cli import stackctl


class IosDirectFlutterRetryContractTest(unittest.TestCase):
    def test_only_healthy_cold_terminal_with_lost_log_reader_is_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            flutter_log = Path(temporary_dir) / "flutter-run.log"
            flutter_log.write_text(
                "Error waiting for a debug connection: "
                "The log reader failed unexpectedly\n",
                encoding="utf-8",
            )
            evidence = {
                "status": "failed",
                "issues": [
                    "expected 3 hot-restart Dart startup attempts, got 0"
                ],
                "flutterRunLog": str(flutter_log),
                "flutterProcessGroupStoppedBySigint": True,
                "flutterRunExitCode": 0,
                "attempts": [
                    {
                        "hotRestart": False,
                        "canonicalTerminal": "routerShell",
                        "configurationState": "complete",
                        "bootstrapFailure": False,
                        "terminalEventCount": 1,
                        "reportedSafeTerminalMs": 3492,
                        "nativeReceivedSafeTerminalMs": 4867,
                    }
                ],
            }

            self.assertTrue(
                stackctl._ios_direct_flutter_log_reader_retryable(evidence)
            )
            evidence["attempts"][0]["nativeReceivedSafeTerminalMs"] = 6001
            self.assertFalse(
                stackctl._ios_direct_flutter_log_reader_retryable(evidence)
            )
            evidence["attempts"][0]["nativeReceivedSafeTerminalMs"] = 4867
            evidence["flutterProcessGroupStoppedBySigint"] = False
            self.assertFalse(
                stackctl._ios_direct_flutter_log_reader_retryable(evidence)
            )

    def test_product_or_configuration_failure_is_never_retryable(self) -> None:
        evidence = {
            "status": "failed",
            "issues": ["cold: runtime configuration was not complete"],
            "flutterRunLog": "/missing",
            "attempts": [],
        }

        self.assertFalse(
            stackctl._ios_direct_flutter_log_reader_retryable(evidence)
        )


if __name__ == "__main__":
    unittest.main()
