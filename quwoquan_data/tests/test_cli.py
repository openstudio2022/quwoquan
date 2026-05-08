from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DATA_ROOT = REPO_ROOT / "quwoquan_data"
CLI_PATH = SOURCE_DATA_ROOT / "tools" / "cli.py"


class QwqDataCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tempdir.name) / "quwoquan_data"
        shutil.copytree(SOURCE_DATA_ROOT, self.data_root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["QWQ_DATA_ROOT"] = str(self.data_root)
        env["QWQ_REPO_ROOT"] = str(REPO_ROOT)
        return subprocess.run(
            [sys.executable, str(CLI_PATH), *args],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def assert_ok(self, result: subprocess.CompletedProcess[str]) -> None:
        if result.returncode != 0:
            self.fail(f"命令失败: stdout={result.stdout}\nstderr={result.stderr}")

    def read_json(self, path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))

    def append_ndjson(self, path: Path, row: dict[str, object]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def test_tree_validate_all_green(self) -> None:
        self.assert_ok(self.run_cli("tree", "validate", "--tree", "all"))

    def test_batch_plan_retrieval_generates_round_two_queries(self) -> None:
        plan = self.data_root / "batch_plans" / "west_lake_loop_001.yaml"
        self.assert_ok(self.run_cli("batch", "plan-retrieval", "--plan", str(plan)))
        retrieval_plan = self.read_json(
            self.data_root / "raw" / "west_lake_loop_001" / "retrieval_plan.json"
        )
        self.assertEqual(retrieval_plan["round"], 2)
        self.assertGreater(len(retrieval_plan["search_queries"]), 0)
        self.assertIn(
            "trees/entities/住宿/西湖亲子友好酒店.yaml",
            retrieval_plan["missing_entity_refs"],
        )
        status = json.loads(self.run_cli("batch", "status", "--plan", str(plan)).stdout)
        self.assertEqual(status["status"], "awaiting_collection")
        self.assertEqual(status["current_round"], 1)
        self.assertGreater(status["next_queries_count"], 0)

    def test_batch_run_builds_image_posts(self) -> None:
        plan = self.data_root / "batch_plans" / "west_lake_image_001.yaml"
        self.assert_ok(self.run_cli("batch", "plan-retrieval", "--plan", str(plan)))
        self.assert_ok(
            self.run_cli("batch", "run", "--plan", str(plan), "--targets", "alpha,gamma", "--dry-run")
        )
        publish_dir = self.data_root / "publish" / "west_lake_image_001"
        out_dir = self.data_root / "out" / "west_lake_image_001"
        posts = [
            json.loads(line)
            for line in (publish_dir / "posts.ndjson").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["post_payload"]["contentType"], "image")
        self.assertEqual(posts[0]["semantic"]["entity_refs"][0], "trees/entities/地点/西湖.yaml")
        self.assertTrue((publish_dir / "entities.ndjson").exists())
        self.assertTrue((publish_dir / "summary.md").exists())
        self.assertTrue((out_dir / "alpha_projection.json").exists())
        self.assertTrue((out_dir / "gamma_projection.json").exists())

    def test_batch_run_builds_article_posts(self) -> None:
        plan = self.data_root / "batch_plans" / "west_lake_article_001.yaml"
        self.assert_ok(self.run_cli("batch", "plan-retrieval", "--plan", str(plan)))
        self.assert_ok(
            self.run_cli("batch", "run", "--plan", str(plan), "--targets", "alpha,gamma", "--dry-run")
        )
        publish_dir = self.data_root / "publish" / "west_lake_article_001"
        posts = [
            json.loads(line)
            for line in (publish_dir / "posts.ndjson").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(posts), 1)
        payload = posts[0]["post_payload"]
        self.assertEqual(payload["contentType"], "article")
        self.assertIn("articleDocument", payload)
        self.assertGreaterEqual(len(payload["articleDocument"]["nodes"]), 3)
        projection = json.loads(
            (self.data_root / "out" / "west_lake_article_001" / "alpha_projection.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(projection["batch_id"], "west_lake_article_001")
        self.assertEqual(projection["environment"], "alpha")
        self.assertTrue(projection["dry_run_only"])

    def test_batch_loop_two_rounds_can_finalize(self) -> None:
        batch_id = "west_lake_loop_001"
        plan = self.data_root / "batch_plans" / f"{batch_id}.yaml"
        self.assert_ok(self.run_cli("batch", "plan-retrieval", "--plan", str(plan)))
        raw_dir = self.data_root / "raw" / batch_id
        self.append_ndjson(
            raw_dir / "search_results.ndjson",
            {
                "query": "西湖亲子友好酒店 杭州西湖 亲子 半日路线",
                "title": "西湖亲子友好酒店与家庭回撤路线",
                "url": "https://you.ctrip.com/travels/west-lake-loop-round2",
                "domain": "you.ctrip.com",
                "snippet": "住在景区边缘更适合带孩子回撤，也方便第二天继续延展。",
                "round": 2,
                "collector": "cursor_commands",
            },
        )
        self.append_ndjson(
            raw_dir / "pages.ndjson",
            {
                "url": "https://you.ctrip.com/travels/west-lake-loop-round2",
                "title": "西湖亲子友好酒店与家庭回撤路线",
                "plain_text": "把亲子酒店、龙井路咖啡和西湖步行段放在同一天里，能形成更完整的半日体验。",
                "fetched_at": "2026-05-07T18:00:00Z",
                "round": 2,
                "evidence_hash": "pagehash_west_lake_loop_round2",
            },
        )
        self.append_ndjson(
            raw_dir / "assets.ndjson",
            {
                "asset_id": "asset_loop_hotel_round2",
                "kind": "image",
                "object_key": "media/image/post/west_lake_loop_001/v1/hotel.png",
                "source_url": "https://img.example.com/west-lake-loop-hotel.png",
                "caption": "亲子酒店补充图",
                "round": 2,
            },
        )
        self.append_ndjson(
            raw_dir / "facts.ndjson",
            {
                "fact_id": "fact_west_lake_loop_round2",
                "source_url": "https://you.ctrip.com/travels/west-lake-loop-round2",
                "title": "补齐酒店与亲子视角后的西湖半日路线",
                "summary": "第二轮补齐了酒店回撤与家庭出行视角，批次可以进入 finalize。",
                "entity_refs": [
                    "trees/entities/地点/西湖.yaml",
                    "trees/entities/住宿/西湖亲子友好酒店.yaml",
                    "trees/entities/本地生活/龙井路咖啡.yaml",
                ],
                "tag_refs": [
                    "trees/tags/主题/城市漫游.yaml",
                    "trees/tags/场景/周末一日.yaml",
                    "trees/tags/人群/亲子.yaml",
                ],
                "location_name": "杭州西湖",
                "cover_asset_id": "asset_loop_hotel_round2",
                "figure_asset_ids": ["asset_loop_cover", "asset_loop_hotel_round2"],
                "article_template": "journal",
                "article_font_preset": "clean",
                "article_paragraphs": [
                    "第二轮补齐后，西湖步行、咖啡补给和酒店回撤终于形成闭环。",
                    "对亲子路线来说，这一轮证据让内容更接近可发布状态。",
                ],
                "round": 2,
            },
        )

        status = json.loads(self.run_cli("batch", "status", "--plan", str(plan)).stdout)
        self.assertEqual(status["status"], "ready_for_finalize")
        self.assertTrue(status["can_finalize"])

        self.assert_ok(
            self.run_cli("batch", "run", "--plan", str(plan), "--targets", "alpha,gamma", "--dry-run")
        )
        loop_state = self.read_json(raw_dir / "loop_state.json")
        self.assertTrue(loop_state["completed"])
        publish_dir = self.data_root / "publish" / batch_id
        self.assertTrue((publish_dir / "posts.ndjson").exists())
        self.assertTrue((self.data_root / "out" / batch_id / "alpha_projection.json").exists())


if __name__ == "__main__":
    unittest.main()
