"""build 实体主页真实链路契约测试。

prepare 下发产出契约（含 SOP 模板路径 + region/season 菜单 + 字数下限）；
validate 采纳门拦截：主页缺失 / 字数不足 / conditionProfile 取值越界。
catalog 按脚本相对路径定位，故临时 QWQ_DATA_ROOT 不影响 region/season 校验。
可直接运行 python3 quwoquan_data/tests/test_build_homepage.py
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="build_homepage_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _common.io import read_json, write_json  # noqa: E402
from _common.paths import batch_inputs_dir, task_data  # noqa: E402
from build.handler import handle_build  # noqa: E402
from build.homepage import validate_entity_pages  # noqa: E402
from task.store import load_spec, save_spec  # noqa: E402

_TASK = "旅行/地域/四川省/景区/景区全覆盖"
_BATCH = "build_test"
_DOMAIN, _ETYPE, _NAME = "地点", "景区", "稻城亚丁"


def _seed_spec() -> None:
    shutil.rmtree(task_data(_TASK).entities_dir(), ignore_errors=True)
    save_spec({
        "schemaVersion": "quwoquan.task.spec",
        "taskId": _TASK,
        "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": _NAME}]},
        "conditionAxes": {"region": {"applicable": True}, "season": {"applicable": True}},
    })


def _materialize_entity(regions: list[str], seasons: list[str], *, page_chars: int = 900) -> None:
    data = task_data(_TASK)
    data.entity_dir(_DOMAIN, _ETYPE, _NAME).mkdir(parents=True, exist_ok=True)
    body = "稻" * page_chars
    data.entity_page(_DOMAIN, _ETYPE, _NAME).write_text(f"# {_NAME}\n\n{body}\n", encoding="utf-8")
    write_json(data.entity_json(_DOMAIN, _ETYPE, _NAME), {
        "label": _NAME,
        "domain": _DOMAIN,
        "type": _ETYPE,
        "sourceTaskId": _TASK,
        "conditionProfile": {"regions": regions, "seasons": seasons, "altitudeMeters": 4000},
    })
    write_json(data.entity_manifest(_DOMAIN, _ETYPE, _NAME), {"tagRefs": [], "assets": []})


def test_prepare_writes_entity_page_contract():
    _seed_spec()
    handle_build(argparse.Namespace(task=_TASK, batch=_BATCH, stage="prepare"))
    inp = batch_inputs_dir(_TASK, _BATCH, "build", "entity_page") / "地点__景区__稻城亚丁.json"
    assert inp.is_file(), f"missing {inp}"
    payload = read_json(inp)["payload"]
    assert payload["minChars"] == 800
    assert payload["sopTemplate"].endswith("template.md")
    assert "高原" in payload["regionMenu"] and "秋" in payload["seasonMenu"]


def test_validate_blocks_missing_homepage():
    _seed_spec()
    issues = validate_entity_pages(_TASK, load_spec(_TASK))
    assert any("page.md 缺失" in i for i in issues), issues


def test_validate_passes_when_complete():
    _seed_spec()
    _materialize_entity(["高原", "雪山"], ["秋", "冬"])
    issues = validate_entity_pages(_TASK, load_spec(_TASK))
    assert issues == [], issues


def test_validate_blocks_short_page():
    _seed_spec()
    _materialize_entity(["高原"], ["秋"], page_chars=200)
    issues = validate_entity_pages(_TASK, load_spec(_TASK))
    assert any("< 800" in i for i in issues), issues


def test_validate_blocks_condition_profile_out_of_catalog():
    _seed_spec()
    _materialize_entity(["火星基地"], ["雾凇季"])
    issues = validate_entity_pages(_TASK, load_spec(_TASK))
    assert any("regions 越界" in i for i in issues), issues
    assert any("seasons 越界" in i for i in issues), issues


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"build homepage tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
