# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-004
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#req-004
"""homepage 读侧的水印高风险判否走出处类别裁决，与采集侧同一判据。

判据只读素材行上显式声明的出处事实（上传者、权利人、搬运路径、原始平台），不读
文件名、URL 形态或托管路径：出处同类的两条素材因此得到同一结论。素材行一个声明位
都没写时判否而不是放行——读侧不得替写侧补一个从未声明过的出处取值。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.homepage.homepage_assets import select_homepage_assets  # noqa: E402
from content.source.source_unit import (  # noqa: E402
    resolve_entity_object_dir,
    write_source_unit,
)
from core.media_source_provenance import (  # noqa: E402
    REASON_PREFIX,
    UNDECLARED_PROVENANCE_REASON,
)
from core.paths import (  # noqa: E402
    ensure_execution_command_layout,
    ensure_execution_layout,
)
from support.execution_manifest_fixture import build_execution_fixture  # noqa: E402
from support.image_fixture import jpeg_bytes  # noqa: E402


def _select(execution_id: str, entity: str, images: list[dict[str, object]]):
    build_execution_fixture(
        execution_id,
        targets=[{"name": entity, "entityType": "地点/景区"}],
    )
    ensure_execution_layout(execution_id)
    ensure_execution_command_layout(execution_id, "source")
    obj = resolve_entity_object_dir(execution_id, entity, etype_hint="地点/景区")
    shutil.rmtree(obj, ignore_errors=True)
    source = write_source_unit(
        obj,
        ordinal=1,
        source_id="home_wikipedia",
        source_md=f"{entity}拥有开放湖面景观与步道。",
        platform="维基百科",
        source_category="encyclopedia",
        source_kind="wikipedia",
        extractor="wikipedia_api",
        policy_revision="encyclopedia-primary",
        source_use_mode="factual_reference_only",
        research_lane="homepage",
        url="https://zh.wikipedia.org/wiki/Test",
        title=entity,
        target_ref=f"/entity/地点/景区/{entity}",
        images=images,
        execution_id=execution_id,
        build_variants=False,
    )
    return select_homepage_assets(
        execution_id,
        "地点",
        "景区",
        entity,
        primary_ref=str(source["sourceRef"]),
    )


def test_same_declared_provenance_excludes_both_regardless_of_locator() -> None:
    """出处同类的两条素材结论一致：命名与 URL 差异不得使结论反转。"""

    execution_id = (
        "20260828--travel-homepage-provenance-locator--test-region-a--pilot-001"
    )
    entity = "出处同类景区"
    # 两条素材声明同一出处类别（批量导入工具搬运的 Panoramio 素材），但文件名、
    # 画面主题与授权证明 URL 全不相同：其中一条的 URL 干净得看不出平台，另一条的
    # URL 里带平台字样。字面匹配会把这两条判成相反结论，出处类别裁决不会。
    selection = _select(
        execution_id,
        entity,
        [
            {
                "bytes": jpeg_bytes(seed=51),
                "ext": ".jpg",
                "caption": f"{entity}湖面全景",
                "relevance": f"{entity}湖面全景",
                "license": "CC BY 3.0",
                "termsUrl": "https://creativecommons.org/licenses/by/3.0/",
                "authorizationProof": (
                    "https://commons.wikimedia.org/wiki/File:Lakeside_view.jpg"
                ),
                "creator": "Panoramio upload bot",
                "credit": "Transferred from Panoramio by Archive Team",
                "usageScope": "app_publish",
                "acquisitionStatus": "acquired",
                "distributionDecision": "research_allowed",
            },
            {
                "bytes": jpeg_bytes(seed=52),
                "ext": ".jpg",
                "caption": f"{entity}石阶步道",
                "relevance": f"{entity}石阶步道",
                "license": "CC BY 3.0",
                "termsUrl": "https://creativecommons.org/licenses/by/3.0/",
                "authorizationProof": (
                    "https://commons.wikimedia.org/wiki/File:Panoramio_stairs.jpg"
                ),
                "creator": "Panoramio upload bot",
                "credit": "Transferred from Panoramio by Archive Team",
                "usageScope": "app_publish",
                "acquisitionStatus": "acquired",
                "distributionDecision": "research_allowed",
            },
        ],
    )

    assert selection.publishable == ()
    reasons = {excluded.reason for excluded in selection.excluded}
    assert reasons == {f"{REASON_PREFIX}:panoramio"}
    assert len(selection.excluded) == 2


def test_row_without_declared_provenance_is_refused_not_admitted() -> None:
    """缺必需出处事实时判否并给 typed 理由，不静默放行也不填默认值。"""

    execution_id = (
        "20260828--travel-homepage-provenance-undeclared--test-region-a--pilot-001"
    )
    entity = "出处未声明景区"
    # 这条素材的授权、许可与分发决定都齐备，唯独没写任何出处声明位：三个出处事实
    # 此时全落各自的未知成员，而未知成员不等价于任何放行态。
    selection = _select(
        execution_id,
        entity,
        [
            {
                "bytes": jpeg_bytes(seed=53),
                "ext": ".jpg",
                "caption": f"{entity}湖面全景",
                "relevance": f"{entity}湖面全景",
                "license": "CC BY 4.0",
                "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                "authorizationProof": (
                    "https://commons.wikimedia.org/wiki/File:Safe.jpg"
                ),
                "usageScope": "app_publish",
                "acquisitionStatus": "acquired",
                "distributionDecision": "commercial_allowed",
            }
        ],
    )

    assert selection.publishable == ()
    assert [excluded.reason for excluded in selection.excluded] == [
        UNDECLARED_PROVENANCE_REASON
    ]
