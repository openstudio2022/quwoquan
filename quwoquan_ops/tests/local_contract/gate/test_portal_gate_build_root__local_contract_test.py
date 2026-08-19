import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[4]
GATE = ROOT / "quwoquan_ops" / "gate" / "gate_repo.sh"


def _portal_gate_function() -> str:
    source = GATE.read_text(encoding="utf-8")
    start = source.index("\nrun_portal() (") + 1
    end = source.index("\nrun_data() {", start)
    return source[start:end]


class PortalGateBuildRootTest(unittest.TestCase):
    def test_builds_into_an_external_temporary_deploy_root(self) -> None:
        portal = _portal_gate_function()

        self.assertIn(
            'mktemp -d "${TMPDIR:-/tmp}/qwq-portal-build.XXXXXX"', portal
        )
        self.assertIn('QWQ_DEPLOY_WORK_ROOT="$portal_build_root"', portal)
        self.assertIn('QWQ_DEPLOY_TARGET="prod-hosted"', portal)
        self.assertEqual(portal.count('rm -rf "$portal_build_root"'), 1)
        self.assertIn("trap cleanup_portal_build_root EXIT", portal)
        self.assertIn("trap 'exit 130' INT", portal)
        self.assertIn("trap 'exit 143' TERM", portal)

    def test_failed_build_cleans_the_external_temporary_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-portal-gate-test-") as root:
            temporary = Path(root)
            bin_dir = temporary / "bin"
            bin_dir.mkdir()
            record = temporary / "build-root.txt"
            npm = bin_dir / "npm"
            npm.write_text(
                "#!/bin/sh\n"
                'if [ "${4:-}" = "build" ]; then\n'
                '  printf "%s" "$QWQ_DEPLOY_WORK_ROOT" > "$PORTAL_BUILD_ROOT_RECORD"\n'
                "  exit 31\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            npm.chmod(0o755)
            harness = temporary / "run-portal.sh"
            harness.write_text(
                "#!/bin/bash\nset -euo pipefail\n"
                f"cd {str(ROOT)!r}\n"
                f"{_portal_gate_function()}\n"
                "run_portal\n",
                encoding="utf-8",
            )
            harness.chmod(0o755)
            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{bin_dir}:/usr/bin:/bin",
                    "PORTAL_BUILD_ROOT_RECORD": str(record),
                    "TMPDIR": str(temporary),
                }
            )

            result = subprocess.run(
                [str(harness)],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 31, result.stderr)
            build_root = Path(record.read_text(encoding="utf-8"))
            self.assertFalse(build_root.exists())


if __name__ == "__main__":
    unittest.main()
