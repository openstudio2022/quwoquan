# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/spec.md#req-002
"""媒体消费的实体别名只能从受版本控制的实体目录里选出来。

`REQ-002`：「`reference/<vertical>/entities`：稳定实体、别名、分类与行政归属；不得写
来源 URL 或运行结论。」同一 REQ 还要求「静态资产不得包含区域、实体、日期、数量、运行
路径或活动阶段」。`REQ-001` 补充「静态 family、provider、schema、prompt/template 与
reference 不含运行实例值」。

图片与视频检索都要拿实体的别名去发现候选，所以「选哪些别名」这件事必须守住三条：

1. 别名是目录里记录的实体事实，不是 provider 策略里的逐实体例外；provider 侧不得持有
   逐实体 URL、图片提示或拒绝词；
2. 选择不发明事实：未记录别名的叶子选出空集，未知实体选出空集（缺席即空，不是失败），
   而目录本身不可读时必须 fail closed；
3. 一个别名只能指向一个 canonical 实体：同一别名落到两个不同身份时不可选，观测名无法
   唯一定位实体时是 typed 失败，不得猜一个。
"""
from __future__ import annotations

import unicodedata
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from content.source.professional_image_supported_api_metadata_entities import (
    ProfessionalImageMetadataEntityError,
    load_entity_bindings,
    resolve_entity,
    resolve_entity_ref,
)
from content.source.research.source_registry import (
    _known_article_sources,
    _known_entity_aliases,
    _known_image_search_hints,
    _known_official_website,
)
from core.paths import REPO_DATA_ROOT, REPO_ROOT
from core.schema import load_schema
from governance import entity_reference
from governance.entity_reference import ENTITY_REFERENCE_ROOT, entity_aliases

_REAL_CITY_CATALOG = (
    REPO_DATA_ROOT / "reference" / "travel" / "entities" / "china" / "浙江省" / "杭州市.yaml"
)


def _leaf(**overrides: Any) -> dict[str, Any]:
    leaf: dict[str, Any] = {
        "name": "西湖",
        "canonicalName": "杭州西湖",
        "entityType": "地点/景区",
        "aliases": ["西湖风景名胜区", "West Lake Hangzhou"],
    }
    leaf.update(overrides)
    return leaf


def _document(*leaves: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "quwoquan_data.discovery_seed",
        "country": "中国",
        "province": "浙江省",
        "city": "杭州市",
        "districts": [{"district": "西湖区", "leaves": list(leaves)}],
    }


@pytest.fixture()
def catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point alias selection at one isolated catalog without keeping its cache."""
    root = tmp_path / "entities" / "china" / "浙江省"
    root.mkdir(parents=True)
    entity_reference._aliases_by_name.cache_clear()
    monkeypatch.setattr(entity_reference, "ENTITY_REFERENCE_ROOT", tmp_path / "entities")
    yield root
    entity_reference._aliases_by_name.cache_clear()


def _normalized_set(values: object) -> set[str]:
    if not isinstance(values, (list, tuple)):
        raise TypeError("alias comparison requires a sequence of alias strings")
    return {unicodedata.normalize("NFKC", str(value)) for value in values}


def _write(path: Path, document: object) -> None:
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def test_the_catalog_leaf_is_a_closed_field_set_that_cannot_hold_a_source_url() -> None:
    """目录叶子是闭集：没有任何字段可以承载来源 URL 或运行结论。"""

    schema = load_schema("governance", "master_list")
    leaf = schema["properties"]["districts"]["items"]["properties"]["leaves"]["items"]

    assert schema["additionalProperties"] is False
    assert leaf["additionalProperties"] is False
    assert "aliases" in leaf["properties"]
    assert not [
        field for field in leaf["properties"] if "url" in field.casefold()
    ]
    assert leaf["properties"]["discoverySources"]["items"]["enum"] == [
        "wiki_category",
        "wikidata_geo",
        "osm_poi",
        "baidu_baike_search",
        "toutiao_baike_search",
    ]


def test_declared_aliases_are_selected_for_the_common_name(catalog: Path) -> None:
    """按常用名查得到规范名与全部已声明别名，且不回显查询名自身。"""

    _write(catalog / "杭州市.yaml", _document(_leaf()))

    assert entity_aliases("西湖") == (
        "杭州西湖",
        "西湖风景名胜区",
        "West Lake Hangzhou",
    )


def test_declared_aliases_are_selected_for_the_canonical_name(catalog: Path) -> None:
    """按规范名查同样得到该实体的其余别名，两个入口指向同一组事实。"""

    _write(catalog / "杭州市.yaml", _document(_leaf()))

    assert entity_aliases("杭州西湖") == (
        "西湖",
        "西湖风景名胜区",
        "West Lake Hangzhou",
    )
    assert set(entity_aliases("杭州西湖")) | {"杭州西湖"} == set(
        entity_aliases("西湖")
    ) | {"西湖"}


def test_alias_selection_dedupes_and_keeps_the_declared_order(catalog: Path) -> None:
    """重复声明只出现一次，顺序仍是目录里的声明顺序。"""

    _write(
        catalog / "杭州市.yaml",
        _document(
            _leaf(aliases=["西湖风景名胜区", "西湖", "西湖风景名胜区", "杭州西湖"])
        ),
    )

    assert entity_aliases("西湖") == ("杭州西湖", "西湖风景名胜区")


def test_blank_alias_entries_are_dropped_instead_of_selected(catalog: Path) -> None:
    """空白别名不是别名，选择时必须丢掉而不是选出一个空字符串。"""

    _write(catalog / "杭州市.yaml", _document(_leaf(aliases=["  ", "", " 西湖景区 "])))

    assert entity_aliases("西湖") == ("杭州西湖", "西湖景区")


def test_an_unknown_entity_selects_nothing_without_failing(catalog: Path) -> None:
    """未记录的实体是缺席：选出空集，不是失败，也不是猜一个别名。"""

    _write(catalog / "杭州市.yaml", _document(_leaf()))

    assert entity_aliases("不在目录里的实体") == ()


@pytest.mark.parametrize("lookup", ["", "   "])
def test_a_blank_lookup_selects_nothing(catalog: Path, lookup: str) -> None:
    """空查询名同样只能得到空集。"""

    _write(catalog / "杭州市.yaml", _document(_leaf()))

    assert entity_aliases(lookup) == ()


@pytest.mark.parametrize(
    "leaf",
    [
        {"name": "西湖", "canonicalName": "杭州西湖"},
        {"name": "西湖", "canonicalName": "杭州西湖", "aliases": "西湖风景名胜区"},
        {"name": "西湖", "canonicalName": "", "aliases": ["西湖风景名胜区"]},
        {"name": "", "canonicalName": "杭州西湖", "aliases": ["西湖风景名胜区"]},
    ],
)
def test_a_leaf_that_records_no_alias_list_yields_no_alias_fact(
    catalog: Path,
    leaf: dict[str, Any],
) -> None:
    """没有可读别名声明的叶子选不出别名，不得由其它字段推导一个。"""

    _write(catalog / "杭州市.yaml", _document(leaf))

    assert entity_aliases("西湖") == ()
    assert entity_aliases("杭州西湖") == ()


def test_alias_selection_never_returns_a_neighbouring_leaf_field(
    catalog: Path,
) -> None:
    """别名只来自 aliases/name/canonicalName，目录其它字段不得混进检索词。"""

    _write(
        catalog / "杭州市.yaml",
        _document(
            _leaf(
                geoTagRef="Topic/地理/行政区/中国/浙江省/杭州市/西湖区",
                typeTagRefs=["Entity/地点/景区/5A景区"],
                discoverySources=["wiki_category"],
                selectionPriority=1,
            )
        ),
    )

    assert entity_aliases("西湖") == (
        "杭州西湖",
        "西湖风景名胜区",
        "West Lake Hangzhou",
    )


def test_every_catalog_file_contributes_its_own_entities(catalog: Path) -> None:
    """目录是整棵树：每个文件的实体都必须可被选中。"""

    _write(catalog / "杭州市.yaml", _document(_leaf()))
    _write(
        catalog / "绍兴市.yaml",
        _document(
            _leaf(
                name="鲁迅故里",
                canonicalName="绍兴鲁迅故里",
                aliases=["鲁迅故居"],
            )
        ),
    )

    assert entity_aliases("西湖") == (
        "杭州西湖",
        "西湖风景名胜区",
        "West Lake Hangzhou",
    )
    assert entity_aliases("鲁迅故里") == ("绍兴鲁迅故里", "鲁迅故居")


def test_an_unreadable_catalog_document_fails_closed(catalog: Path) -> None:
    """目录本身不是对象时必须 fail closed，不得退化为「没有别名」。"""

    _write(catalog / "杭州市.yaml", ["西湖"])

    with pytest.raises(TypeError, match="entity reference must be an object"):
        entity_aliases("西湖")


def test_media_image_search_hints_select_exactly_the_catalog_aliases() -> None:
    """图片检索提示只能是目录别名，provider 侧不另建一套别名。"""

    entity_id = "西湖"
    aliases = entity_aliases(entity_id)
    hints = _known_image_search_hints(entity_id)

    assert aliases
    assert hints == {"aliases": list(aliases), "commonsCategories": []}
    assert _known_entity_aliases(entity_id) == list(aliases)


def test_the_provider_policy_holds_no_per_entity_url_or_article_source() -> None:
    """provider 策略不得持有逐实体 URL 或来源清单，那些是运行结论。"""

    for entity_id in ("西湖", "不在目录里的实体"):
        assert _known_official_website(entity_id) == ""
        assert _known_article_sources(entity_id) == []


def test_the_media_binding_catalog_is_version_controlled_and_digest_bound() -> None:
    """媒体绑定消费的目录必须是仓库内受版本控制的文件，并绑定其摘要。"""

    ref, digest, index = load_entity_bindings(_REAL_CITY_CATALOG)

    assert (REPO_ROOT / ref).resolve() == _REAL_CITY_CATALOG.resolve()
    assert digest.startswith("sha256:") and len(digest) == 71
    assert index


def test_a_catalog_outside_version_control_is_a_typed_failure(tmp_path: Path) -> None:
    """仓库外的目录不得作为实体真相源。"""

    outside = tmp_path / "杭州市.yaml"
    _write(outside, _document(_leaf()))

    with pytest.raises(
        ProfessionalImageMetadataEntityError, match="must be version controlled"
    ):
        load_entity_bindings(outside)


def test_a_missing_catalog_is_a_typed_failure() -> None:
    """目录缺席是失败，不是空索引。"""

    with pytest.raises(
        ProfessionalImageMetadataEntityError, match="missing or unsafe"
    ):
        load_entity_bindings(_REAL_CITY_CATALOG.parent / "不存在的市.yaml")


def test_every_selectable_alias_maps_to_exactly_one_catalog_identity() -> None:
    """可选别名与 canonical 身份是一对一：一个别名只能定位一个实体。"""

    _ref, _digest, index = load_entity_bindings(_REAL_CITY_CATALOG)

    for alias, binding in index.items():
        resolved = resolve_entity(alias, index=index)
        assert resolved["entityId"] == binding["entityId"]
        assert resolved["observedEntityId"] == alias
        assert alias in resolved["entityAliases"]
        assert resolved["entityAliases"] == sorted(set(resolved["entityAliases"]))


def test_an_alias_selects_the_canonical_entity_ref() -> None:
    """别名必须能选出 canonical `/entity/{type}/{name}` 身份。"""

    _ref, _digest, index = load_entity_bindings(_REAL_CITY_CATALOG)
    binding = index["西湖"]

    assert binding["entityId"] == "杭州西湖"
    assert resolve_entity_ref("西湖", index=index) == "/entity/地点/景区/杭州西湖"
    assert resolve_entity_ref("杭州西湖", index=index) == resolve_entity_ref(
        "西湖", index=index
    )


def test_a_compatibility_variant_selects_the_same_entity() -> None:
    """兼容等价的写法必须归一到同一实体，而不是变成一个未知观测名。"""

    _ref, _digest, index = load_entity_bindings(_REAL_CITY_CATALOG)

    assert resolve_entity("Ｗest Lake Hangzhou", index=index)["entityId"] == "杭州西湖"
    assert resolve_entity(" 西湖 ", index=index)["entityId"] == "杭州西湖"


def test_an_observed_name_absent_from_the_catalog_is_a_typed_failure() -> None:
    """观测名不在目录里时是 typed 失败，不得猜一个最相似的实体。"""

    _ref, _digest, index = load_entity_bindings(_REAL_CITY_CATALOG)

    for observed in ("西湖区", "杭州", ""):
        with pytest.raises(
            ProfessionalImageMetadataEntityError, match="absent or ambiguous"
        ):
            resolve_entity(observed, index=index)
        with pytest.raises(
            ProfessionalImageMetadataEntityError, match="absent or ambiguous"
        ):
            resolve_entity_ref(observed, index=index)


def test_only_the_canonical_name_is_a_globally_addressable_lookup_key() -> None:
    """canonicalName 跨文件全局唯一，是唯一可全局定位实体的查询键。

    常用名允许跨市重名（真实目录里就有），因此按常用名查别名本身可能是歧义查询。
    """

    canonical: Counter[str] = Counter()
    common: Counter[str] = Counter()
    for path in sorted(ENTITY_REFERENCE_ROOT.rglob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for group in document["districts"]:
            for leaf in group["leaves"]:
                canonical[leaf["canonicalName"]] += 1
                common[leaf["name"]] += 1

    duplicated = sorted(name for name, count in common.items() if count > 1)

    assert [name for name, count in canonical.items() if count > 1] == []
    assert duplicated
    assert not set(duplicated) & set(canonical)


def test_the_governance_alias_facts_and_the_media_binding_agree() -> None:
    """治理侧别名事实与媒体绑定索引必须同源，不允许两套别名。

    只按 canonicalName 比对：它是跨文件全局唯一的查询键。两侧对别名字符串的归一形式
    不同（治理侧只裁空白，媒体绑定侧按 NFKC 归一），而目录契约没有声明唯一归一形式，
    因此这里只锁定「同一组事实」，不锁定字面形式。
    """

    _ref, _digest, index = load_entity_bindings(_REAL_CITY_CATALOG)
    bindings = {
        str(binding["entityId"]): binding for binding in index.values()
    }
    compared = 0
    for entity_id, binding in bindings.items():
        recorded = entity_aliases(entity_id)
        if not recorded:
            continue
        compared += 1
        assert _normalized_set([*recorded, entity_id]) == _normalized_set(
            binding["entityAliases"]
        )

    assert compared, "no catalog entity records an alias fact to compare"


def test_the_real_catalog_root_is_the_governed_reference_tree() -> None:
    """治理侧读取的目录根就是受版本控制的 reference 实体树。"""

    assert ENTITY_REFERENCE_ROOT == REPO_DATA_ROOT / "reference" / "travel" / "entities"
    assert _REAL_CITY_CATALOG.is_file()
    assert ENTITY_REFERENCE_ROOT in _REAL_CITY_CATALOG.parents
