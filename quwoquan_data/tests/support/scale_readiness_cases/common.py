"""Scale readiness gate contract tests."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
_TMP = Path(tempfile.mkdtemp(prefix="scale_readiness_"))
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_RELEASE_ROOT"] = str(_TMP / "release")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(_TMP / "tasks")
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from _common.io import write_json  # noqa: E402
from _common.paths import batch_root, release_root  # noqa: E402
from task import store  # noqa: E402
from verify.scale_readiness import _homepage_passed_count, build_scale_readiness_report  # noqa: E402


TASK = "旅行/地域/四川省/景区/规模门"
BATCH = "b1"


def _save_spec(queue_backend: str = "reliabletask", max_concurrency: int = 10) -> dict:
    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="四川省",
        category="景区",
        name="规模门",
        scope={
            "region": "四川省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [{"entityType": "地点/景区", "name": "九寨沟"}],
        },
        content={
            "modalityContract": "separated_research",
            "queueBackend": queue_backend,
            "research": {"maxConcurrency": max_concurrency},
            "quotas": {
                "entityHomepagesPerTarget": 1,
                "entityArticlesPerTarget": 4,
                "imageWorksPerTarget": 1,
                "routeArticles": 0,
            },
        },
    )
    spec["status"] = "active"
    store.save_spec(spec)
    return spec


def _write_env_ready(batch_id: str) -> None:
    write_json(
        batch_root(TASK, batch_id) / "_shared" / "env_ready_report.json",
        {
            "schemaVersion": "quwoquan_data.env_ready_report",
            "ready": True,
            "preflight": {"ready": True, "issues": []},
            "cursorStartup": {
                "checked": True,
                "ready": True,
                "probeType": "agent_prompt_smoke",
                "status": "finished",
            },
        },
    )


def _write_token_ledger(
    batch_id: str,
    *,
    measurement_mode: str = "cursor_sdk_result_usage",
    summary: dict | None = None,
) -> None:
    payload = {
        "measurementMode": measurement_mode,
        "summary": {"unitCost": 1, **(summary or {})},
    }
    write_json(batch_root(TASK, batch_id) / "_shared" / "token_ledger.json", payload)


def _seed_passed_homepage(batch_id: str, name: str = "都江堰") -> Path:
    entity = batch_root(TASK, batch_id) / "entities" / "地点" / "景区" / name
    write_json(entity / "_entity.json", {"label": name, "domain": "地点", "type": "景区"})
    (entity / "page.md").parent.mkdir(parents=True, exist_ok=True)
    (entity / "page.md").write_text(f"# {name}\n\n主页正文", encoding="utf-8")
    write_json(entity / "manifest.json", {"assets": []})
    write_json(
        entity / "1.download" / "source_refs.json",
        {
            "schemaVersion": "quwoquan_data.source_refs/2",
            "sources": [
                {
                    "role": "base",
                    "sourceRef": "entities/地点/景区/%s/1.download/sources/homepage_primary/source.md" % name,
                }
            ],
        },
    )
    write_json(
        entity / "1.download" / "sources" / "homepage_primary" / "meta.json",
        {
            "lane": "homepage",
            "focusVerdict": "exact",
            "entityFocusVerdict": "exact",
        },
    )
    (entity / "1.download" / "sources" / "homepage_primary" / "source.md").write_text(
        f"{name}位于四川，是一处用于规模门测试的景区主页底稿。" * 12,
        encoding="utf-8",
    )
    write_json(entity / "5.review" / "review.json", {"decision": "approved", "issues": []})
    write_json(
        entity / "5.review" / "finalization_report.json",
        {
            "schemaVersion": "quwoquan_data.finalization_report",
            "status": "passed",
            "draftArticleRef": "4.draft/page.md",
            "finalArticleRef": "page.md",
        },
    )
    return entity


def _creator_assignment() -> dict:
    return {
        "authorId": "builtin_travel_blogger_chuanxi",
        "creatorProfileId": "qwq_creator_travel_blogger_chuanxi_001",
        "creatorArchetype": "travel_blogger",
        "creatorProfileVersion": "1.0.0",
        "creatorDisclosure": {
            "type": "platform_virtual_creator",
            "displayText": "平台虚拟创作者，内容由资料整理与 AI 辅助生成，经平台审核发布。",
            "visible": True,
        },
        "experienceClaimMode": "editorial_synthesis",
        "authorQualitySignals": {"qualityScore": 0.86, "fatigueScore": 0.2, "riskTier": "low"},
    }

__all__ = [name for name in globals() if not name.startswith("__")]
