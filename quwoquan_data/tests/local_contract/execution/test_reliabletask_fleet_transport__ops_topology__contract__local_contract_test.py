"""Data resolves fleet transport from stackctl rather than caller environment."""
from __future__ import annotations

import os
import json
import sys
from pathlib import Path


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
for path in (DATA_ROOT.parent, DATA_ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from content.execution.reliabletask_fleet import resolve_reliabletask_fleet_transport  # noqa: E402


def test_reliabletask_fleet_transport__ignores_caller_endpoint_variables__contract__local_contract(
    monkeypatch,
) -> None:
    monkeypatch.setenv("QWQ_DATA_FLEET_MONGO_URI", "mongodb://caller.invalid:27017")
    monkeypatch.setenv("QWQ_DATA_FLEET_REDIS_ADDR", "caller.invalid:6379")

    transport = resolve_reliabletask_fleet_transport()
    policy = json.loads(
        (DATA_ROOT.parent / "quwoquan_ops/environments/data_execution_fleet.json").read_text(
            encoding="utf-8"
        )
    )

    assert transport.target == policy["localTarget"]
    assert "caller.invalid" not in transport.mongo_uri
    assert "caller.invalid" not in transport.redis_addr
    assert os.environ["QWQ_DATA_FLEET_MONGO_URI"] == "mongodb://caller.invalid:27017"
