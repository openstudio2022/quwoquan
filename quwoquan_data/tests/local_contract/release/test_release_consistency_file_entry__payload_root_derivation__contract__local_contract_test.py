"""scan_release_file 的 release root 推导契约。

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-001
release_layout 只承认 <releaseRoot>/payload/desired_state.json 单一布局且禁止 flat
回退，因此文件入口必须把 payload 的父目录当 release root；desired state 不在
payload/ 下时 fail-closed，而不是把错误目录当 release root 静默扫描。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.release.environment.consistency import (  # noqa: E402
    DESIRED_SCHEMA,
    scan_release_file,
)


def _minimal_desired_state() -> dict[str, object]:
    return {
        "schema": DESIRED_SCHEMA,
        "releaseId": "release-consistency-entry-fixture",
        "desiredRefs": {"posts": [], "entities": [], "creators": []},
    }


class ReleaseConsistencyFileEntryContractTest(unittest.TestCase):
    def test_payload_located_desired_state_derives_release_root_from_payload_parent(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary:
            release_root = Path(temporary) / "release-consistency-entry-fixture"
            payload = release_root / "payload"
            (payload / "index").mkdir(parents=True)
            (payload / "objects").mkdir()
            desired = payload / "desired_state.json"
            desired.write_text(
                json.dumps(_minimal_desired_state(), ensure_ascii=False),
                encoding="utf-8",
            )
            for name in ("release.json", "media_manifest.json", "sample_bundle.json"):
                (payload / name).write_text("{}", encoding="utf-8")
            (payload / "index" / "objects.json").write_text("{}", encoding="utf-8")

            report = scan_release_file(desired, publish_root=Path(temporary) / "publish")

            self.assertNotIn(
                "release_artifact_missing",
                {issue["code"] for issue in report.get("blockingIssues") or []},
                "payload 布局下 release root 必须是 payload 的父目录，"
                "不得把 payload 自身当 release root 再找 payload/payload",
            )

    def test_desired_state_outside_payload_fails_closed(self) -> None:
        with TemporaryDirectory() as temporary:
            stray = Path(temporary) / "desired_state.json"
            stray.write_text(
                json.dumps(_minimal_desired_state(), ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit):
                scan_release_file(stray)


if __name__ == "__main__":
    unittest.main()
