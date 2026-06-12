"""source_plan guidance should include registry hints."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import os

_TMP = tempfile.mkdtemp(prefix="source_plan_guidance_")
os.environ["QWQ_RUNTIME_ROOT"] = _TMP

from _common.io import read_json  # noqa: E402
from _common.source_unit import resolve_entity_object_dir  # noqa: E402
from download.prepare import prepare_source_plan  # noqa: E402


def test_prepare_source_plan_includes_registry_guidance_for_travel():
    task = "旅行/地域/四川省/景区/景区全覆盖"
    batch = "guidance_batch"
    entity = {"entityId": "九寨沟", "canonicalName": "九寨沟", "entityType": "景区"}
    prepare_source_plan(task, batch, [entity])
    plan = resolve_entity_object_dir(task, batch, "九寨沟", etype_hint="景区") / "1.download" / "source_plan.json"
    payload = read_json(plan)["payload"]
    assert payload["sourceCategoryGuidance"]["categories"]
    registry = payload["sourceRegistryGuidance"]
    assert registry["fetchableSites"], registry
    assert any(site["siteId"] == "wikipedia_zh" for site in registry["fetchableSites"]), registry
    assert any(site["siteId"] == "mafengwo_travelogue" for site in registry["nonFetchableSites"]), registry


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"source plan guidance tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
