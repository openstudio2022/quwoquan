"""Topic verticals writer 调用序 + 产物字节 digest：防止语义拆分打乱写入。"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import governance.taxonomy.bootstrap_tags as bootstrap_tags  # noqa: E402
from governance.taxonomy.bootstrap_tags_topic import (  # noqa: E402
    configure_writers,
    _gen_topic_verticals,
)

# 拆分前冻结的 writer 调用流 digest（184 次 group/dim/tag/tags_list）。
# 生成：recording writers + _gen_topic_verticals() + json.dumps(sort_keys=False)。
EXPECTED_WRITER_SEQUENCE_SHA256 = (
    "6793e3182afe80eb79ee0e461e28cf70092ca19160c5b7fe8c5e81598b37ca9a"
)
EXPECTED_CALL_COUNT = 184

# 拆分前冻结的 Topic vertical 产物树 digest（真实 write_json，冻结 NOW_ISO）。
# 生成：TAGS_ROOT=tmp + NOW_ISO=FIXED + 真实 writers + _gen_topic_verticals()，
# 再对 sorted(relpath + bytes) 做 sha256。拆分前 vertical shards 与七模块均为此值。
FIXED_NOW_ISO = "2026-05-15T00:00:00+08:00"
EXPECTED_TOPIC_VERTICALS_ARTIFACT_SHA256 = (
    "dfbb1fd94634c68c92f99c5dc0b046baa711fa42978f5b9bad912dc07edd75a4"
)
EXPECTED_DEFINITION_COUNT = 802
EXPECTED_DIMENSION_COUNT = 26
EXPECTED_JSON_FILE_COUNT = 828


def _record_writer_sequence() -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def make_recorder(name: str):
        def _rec(*args, **kwargs):
            calls.append({"op": name, "args": list(args), "kwargs": kwargs})
            return None

        return _rec

    configure_writers(
        group=make_recorder("group"),
        dim=make_recorder("dim"),
        tag=make_recorder("tag"),
        tags_list=make_recorder("tags_list"),
    )
    _gen_topic_verticals()
    return calls


def _digest(calls: list[dict[str, object]]) -> str:
    raw = json.dumps(calls, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _materialize_topic_verticals(tmp_path: Path) -> tuple[str, dict[str, int]]:
    bootstrap_tags.TAGS_ROOT = tmp_path
    bootstrap_tags.NOW_ISO = FIXED_NOW_ISO
    bootstrap_tags.DRY_RUN = False
    configure_writers(
        group=bootstrap_tags.group,
        dim=bootstrap_tags.dim,
        tag=bootstrap_tags.tag,
        tags_list=bootstrap_tags.tags_list,
    )
    _gen_topic_verticals()

    digest = hashlib.sha256()
    definition_count = 0
    dimension_count = 0
    json_files = sorted(tmp_path.rglob("*.json"))
    for path in json_files:
        relative = path.relative_to(tmp_path).as_posix()
        if path.name == "_definition.json":
            definition_count += 1
        elif path.name == "_dimension.json":
            dimension_count += 1
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest(), {
        "definitions": definition_count,
        "dimensions": dimension_count,
        "json_files": len(json_files),
    }


def test_topic_verticals_writer_sequence_digest_is_stable() -> None:
    calls = _record_writer_sequence()
    assert len(calls) == EXPECTED_CALL_COUNT
    assert _digest(calls) == EXPECTED_WRITER_SEQUENCE_SHA256


def test_topic_verticals_artifact_bytes_match_pre_split_baseline(tmp_path: Path) -> None:
    digest, counts = _materialize_topic_verticals(tmp_path)
    assert counts == {
        "definitions": EXPECTED_DEFINITION_COUNT,
        "dimensions": EXPECTED_DIMENSION_COUNT,
        "json_files": EXPECTED_JSON_FILE_COUNT,
    }
    assert digest == EXPECTED_TOPIC_VERTICALS_ARTIFACT_SHA256
    # 产物树存在关键垂类；food→lodging→travel 的写入序由 writer-sequence digest 守护。
    assert (tmp_path / "Topic/美食餐饮/_definition.json").is_file()
    assert (tmp_path / "Topic/住宿/_definition.json").is_file()
    assert (tmp_path / "Topic/旅行/_definition.json").is_file()
    assert (tmp_path / "Topic/摄影/_definition.json").is_file()


def test_topic_verticals_orchestrator_order_is_semantic_modules() -> None:
    source = (
        SCRIPTS_ROOT / "governance/taxonomy/bootstrap_tags_topic.py"
    ).read_text(encoding="utf-8")
    order = [
        "gen_topic_nature_history()",
        "gen_topic_food()",
        "gen_topic_travel()",
        "gen_topic_lifestyle_wellness()",
        "gen_topic_technology_learning()",
        "gen_topic_relationships_entertainment()",
        "gen_topic_society_public_affairs()",
        "gen_photography()",
    ]
    positions = [source.index(name) for name in order]
    assert positions == sorted(positions)
    retired = "gen_topic_verticals_" + "part"
    assert retired + "1" not in source
    assert retired + "2" not in source
    food_source = (
        SCRIPTS_ROOT / "governance/taxonomy/bootstrap_tags_topic_food.py"
    ).read_text(encoding="utf-8")
    assert "gen_topic_lodging()" in food_source
