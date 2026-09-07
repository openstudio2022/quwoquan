"""Review registry 与 content-production producer/downstream 边界治理。"""

from __future__ import annotations

import os
import shlex
import subprocess
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[4]
REGISTRY = ROOT / ".agents/skills/review/references/registry.yaml"
CHECKLIST = (
    ROOT
    / ".agents/skills/review/references/roles/data-quality/checklists/"
    "content-production/base.md"
)
PUBLISH_CLOSURE_COMMAND = (
    "python3 -B quwoquan_data/scripts/cli.py verify publish-closure"
)


class ContentProductionReviewBoundaryTest(unittest.TestCase):
    def test_publish_purity_evidence_uses_registered_canonical_closure_cli(
        self,
    ) -> None:
        registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
        command = registry["evidence"]["content-publish-purity"]["command"]

        self.assertEqual(PUBLISH_CLOSURE_COMMAND, command)
        completed = subprocess.run(
            [*shlex.split(command), "--help"],
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("qwq-data verify publish-closure", completed.stdout)

    def test_content_production_checklist_separates_producer_from_downstream(
        self,
    ) -> None:
        checklist = CHECKLIST.read_text(encoding="utf-8")
        producer_must = next(
            line
            for line in checklist.splitlines()
            if line.startswith("- [MUST]") and "producer 准出" in line
        )

        for required in (
            "acquire/author/review 三份 seal receipt",
            "逐对象 publish",
            "explicit cohort",
            "immutable producer handoff",
        ):
            self.assertIn(required, producer_must)
        self.assertNotIn("import", producer_must)
        self.assertNotIn("readback", producer_must)

        self.assertIn("downstream 独立验证", checklist)
        self.assertIn("不得写入或改写 producer", checklist)
        self.assertNotIn("immutable release、导入与可读回执", checklist)
        self.assertNotIn("execution/release/import/readback 身份", checklist)

    def test_content_production_has_exactly_one_reviewer(self) -> None:
        registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
        workflow = registry["workflows"]["content-production"]

        self.assertEqual("data-quality", workflow["primary"]["role"])
        self.assertNotIn("content-release", registry.get("profiles", {}))
        for profile in registry.get("profiles", {}).values():
            self.assertNotIn(
                "content-release",
                profile.get("deliverables", []),
                "content-release 不得再挂任何 specialist，唯一 reviewer 是 data-quality",
            )
            self.assertNotEqual("data-legal", profile.get("specialist", {}).get("role"))
        self.assertFalse(
            (ROOT / ".agents/skills/review/references/roles/data-legal").exists()
        )
        self.assertIn("权利六字段", CHECKLIST.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
