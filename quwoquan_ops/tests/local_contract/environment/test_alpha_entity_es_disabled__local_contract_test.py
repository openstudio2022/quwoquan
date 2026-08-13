"""Alpha entity-service 不得在无 ES endpoints 时启用搜索。"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
ALPHA_ENTITY_CONFIG = (
    ROOT
    / "quwoquan_service"
    / "services"
    / "entity-service"
    / "environments"
    / "alpha"
    / "config.yaml"
)
ENTITY_SCHEMA = (
    ROOT
    / "quwoquan_service"
    / "services"
    / "entity-service"
    / "config"
    / "schema.yaml"
)


def test_alpha_entity_service__es_disabled_without_endpoints__local_contract() -> None:
    payload = yaml.safe_load(ALPHA_ENTITY_CONFIG.read_text(encoding="utf-8"))
    overrides = payload.get("overrides") or {}
    # 不得显式启用；缺省走 schema default=false（禁止重复写 default override）。
    assert "sys.entity-service.es.enabled" not in overrides
    assert overrides.get("sys.entity-service.es.endpoints") in (None, [], ())

    schema = yaml.safe_load(ENTITY_SCHEMA.read_text(encoding="utf-8"))
    enabled_default = next(
        item["default"]
        for item in schema.get("configs") or []
        if isinstance(item, dict)
        and item.get("key") == "sys.entity-service.es.enabled"
    )
    assert enabled_default is False
