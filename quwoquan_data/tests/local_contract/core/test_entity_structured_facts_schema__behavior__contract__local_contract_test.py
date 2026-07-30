"""发布态 structuredFacts 与信源政策、服务契约三方同源。

放开官网与政府/文旅门户是有代价的政策决定：只对固定几个单值事实字段放开，且每
个字段必须留证。这个约束同时写在三处——政策 registry、发布 schema、entity-service
契约——任何一处单独放宽都会让另外两处的保证失效，所以这里把三方一致钉成契约。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
REPO_ROOT = DATA_ROOT.parent
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.content_source_registry import (  # noqa: E402
    STRUCTURED_FACTS_FIELDS,
    STRUCTURED_FACTS_SOURCE_CLASSES,
)

ENTITY_SCHEMA = DATA_ROOT / "schema" / "publish" / "entity.schema.json"
HOMEPAGE_FIELDS = (
    REPO_ROOT
    / "quwoquan_service"
    / "services"
    / "entity-service"
    / "contracts"
    / "entity_homepage"
    / "homepage"
    / "fields.yaml"
)
SHARED_TYPES = (
    REPO_ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared" / "types.yaml"
)


def _structured_facts_schema() -> dict:
    schema = json.loads(ENTITY_SCHEMA.read_text(encoding="utf-8"))
    return schema["properties"]["structuredFacts"]


def _fact_source_schema() -> dict:
    return _structured_facts_schema()["properties"]["factSources"]["items"]


def test_publish_schema_field_set_matches_the_source_policy() -> None:
    facts = _structured_facts_schema()
    declared = set(facts["properties"]) - {"factSources"}
    assert declared == set(STRUCTURED_FACTS_FIELDS)
    # 闭集：额外字段会绕过政策审计，因为它们没有对应的 allowedSourceClasses 约束。
    assert facts["additionalProperties"] is False

    evidence_fields = set(_fact_source_schema()["properties"]["field"]["enum"])
    assert evidence_fields == set(STRUCTURED_FACTS_FIELDS)


def test_publish_schema_source_classes_match_the_source_policy() -> None:
    classes = set(_fact_source_schema()["properties"]["sourceClass"]["enum"])
    assert classes == set(STRUCTURED_FACTS_SOURCE_CLASSES)
    # OTA 是政策明确排除的一类，写进来就等于悄悄放宽准入。
    assert "ota" not in classes


def test_publish_schema_requires_provenance_and_https_evidence() -> None:
    fact_sources = _structured_facts_schema()["properties"]["factSources"]
    # 有 structuredFacts 就必须有证据；空数组等于无证据展示。
    assert fact_sources["minItems"] == 1
    item = fact_sources["items"]
    assert set(item["required"]) == {
        "field",
        "sourceId",
        "sourceClass",
        "sourceUrl",
        "observedAt",
        "confidence",
    }
    assert item["properties"]["sourceUrl"]["pattern"] == "^https://"
    assert item["additionalProperties"] is False
    confidence = item["properties"]["confidence"]
    assert confidence["exclusiveMinimum"] == 0 and confidence["maximum"] == 1


def test_publish_schema_best_season_refs_stay_on_the_season_axis() -> None:
    refs = _structured_facts_schema()["properties"]["bestSeasonTagRefs"]["items"]
    # 自由文本季节无法与内容标签求交，「同季节窗口到访」就永远算不出来。
    assert refs["pattern"] == "^Topic/(时间/四季|旅行/季节窗口)/"


def test_service_contract_enums_match_the_publish_schema() -> None:
    shared = yaml.safe_load(SHARED_TYPES.read_text(encoding="utf-8"))
    enums = shared["enums"]
    assert set(enums["HomepageStructuredFactField"]) == set(STRUCTURED_FACTS_FIELDS)
    assert set(enums["HomepageStructuredFactSourceClass"]) == set(STRUCTURED_FACTS_SOURCE_CLASSES)

    homepage = yaml.safe_load(HOMEPAGE_FIELDS.read_text(encoding="utf-8"))
    view = homepage["types"]["HomepageStructuredFactsView"]
    contract_fields = {field["name"] for field in view["fields"]} - {"factSources"}
    assert contract_fields == set(STRUCTURED_FACTS_FIELDS)
