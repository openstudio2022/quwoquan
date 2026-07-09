"""Shared helpers for site-supply contract tests."""



from __future__ import annotations

import json

import os

import subprocess

import sys

import tempfile

from contextlib import redirect_stdout

from io import StringIO

from pathlib import Path

REPO_DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")

DATA_ROOT = REPO_DATA_ROOT

SCRIPTS_ROOT = DATA_ROOT / "scripts"

_TMP = Path(tempfile.mkdtemp(prefix="site_supply_"))

TEST_DATA_ROOT = _TMP / "data"

TEST_TASKS_ROOT = TEST_DATA_ROOT / "tasks"

TEST_DATA_ROOT.mkdir(parents=True, exist_ok=True)

for _name in ("verticals", "templates"):
    _target = REPO_DATA_ROOT / _name
    _link = TEST_DATA_ROOT / _name
    if _target.exists() and not _link.exists():
        _link.symlink_to(_target, target_is_directory=True)

_service_target = REPO_DATA_ROOT.parent / "quwoquan_service"
_service_link = _TMP / "quwoquan_service"
if _service_target.exists() and not _service_link.exists():
    _service_link.symlink_to(_service_target, target_is_directory=True)

os.environ["QWQ_DATA_ROOT"] = str(TEST_DATA_ROOT)

os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")

os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")

os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(TEST_TASKS_ROOT)

for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from site_supply import handler as ss

from task import store

def _cli_env() -> dict[str, str]:
    """site-supply CLI 子进程的显式环境。

    DATA_ROOT 指向隔离 tmp，并通过 verticals symlink 读取真实 source registry；
    运行态/发布/committed 根也隔离到本测试 tmp。必须显式构造而非继承全局
    os.environ：同一 pytest 进程内其他测试模块会改写 QWQ_*，子进程若继承污染值
    会读到错误的 local/data-runtime/tasks。
    """
    env = dict(os.environ)
    env["QWQ_DATA_ROOT"] = str(TEST_DATA_ROOT)
    env["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
    env["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")
    env["QWQ_COMMITTED_TASKS_ROOT"] = str(TEST_TASKS_ROOT)
    return env

ARTICLE_TEXT = (
    "九寨沟两日深度玩法实测：第一天走树正沟，第二天主攻日则沟，节奏从容不赶路。\n\n"
    "## 交通与门票\n"
    "旺季门票169元、观光车90元；从成都出发约8小时车程，建议清晨发车避开拥堵。\n\n"
    "## 核心海子与体验\n"
    "五花海、诺日朗瀑布、长海色彩层次分明，海拔约2000米需注意高反与保暖；"
    "栈道单程约5公里，留足拍摄时间，最打动人的是清晨无人的镜海倒影。\n\n"
    "## 实用提醒\n"
    "景区内禁止无人机，山区午后多阵雨，雨衣比雨伞更实用，全程信息便于规划行程。"
)

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff"
    b"\xff?\x00\x05\xfe\x02\xfeA\x82\xa9\x99\x00\x00\x00\x00IEND\xaeB`\x82"
)

TEST_COMMITTED_TASK_ID = "旅行/网站供给线/维基导游/真实运营试跑"

def _seed_committed_task_spec() -> None:
    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="网站供给线",
        key="维基导游",
        name="真实运营试跑",
        scope={
            "region": "四川省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [
                {"entityType": "地点/景区", "name": "九寨沟"},
                {"entityType": "地点/景区", "name": "成都"},
                {"entityType": "地点/景区", "name": "乐山大佛"},
                {"entityType": "地点/景区", "name": "三星堆博物馆"},
                {"entityType": "地点/景区", "name": "杭州西湖"},
                {"entityType": "地点/景区", "name": "黄山"},
            ],
        },
        content={
            "modalityContract": "separated_research",
            "quotas": {
                "entityHomepagesPerTarget": 1,
                "entityArticlesPerTarget": 1,
                "imageWorksPerTarget": 1,
            },
        },
        created_by="test",
    )
    assert spec["taskId"] == TEST_COMMITTED_TASK_ID
    store.save_spec(spec)
    ss._known_coverage_entity_targets.cache_clear()


_seed_committed_task_spec()

def _write_frontier(batch: str = "b1") -> dict:
    packet = ss.build_site_frontier_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        daily_target=100_000,
        queue_backend="reliabletask",
        end_date="2026-06-19",
    )
    assert packet["gate"]["passed"], packet["gate"]
    ss.write_site_frontier_packet(packet)
    return packet

def _write_candidate(batch: str = "b1") -> dict:
    _write_frontier(batch)
    packet = ss.build_site_candidate_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        url="https://touch.travel.qunar.com/travelbook/note/123456",
        lane="article",
        title="九寨沟两日玩法",
        text=ARTICLE_TEXT,
        published_at="2026-06-01",
        entity_mentions=["地点/景区/九寨沟"],
        tag_mentions=["Topic/旅行/玩法/自然风光"],
    )
    assert packet["gate"]["passed"], packet["gate"]
    ss.write_site_candidate_packet(packet)
    return packet

_CASUAL_SITE_TEXT = "九寨沟今天天气真好，随手拍了几张照片，特别开心，海子的颜色很美，下次还来玩。"

def _site_works_candidate(*, ref: str, text: str, validation_only: bool, lane: str = "article") -> dict:
    return {
        "schemaVersion": ss.CANDIDATE_SCHEMA,
        "vertical": "travel",
        "siteId": "qunar_guide",
        "batchId": "works_gate_contract",
        "candidateRef": ref,
        "canonicalUrl": f"https://touch.travel.qunar.com/travelbook/note/{ref}",
        "lane": lane,
        "source": {
            "platform": "去哪儿攻略",
            "rightsPolicy": "factual_citation_only",
            "validationOnly": validation_only,
        },
        "title": "九寨沟",
        "text": text,
        "assets": [],
        "publishedAt": "2026-06-01",
        "gate": {"passed": True},
    }



__all__ = sorted(name for name in globals() if name != "__all__" and not name.startswith("__"))
