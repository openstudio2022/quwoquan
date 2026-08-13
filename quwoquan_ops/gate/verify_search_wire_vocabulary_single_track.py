#!/usr/bin/env python3
"""搜索请求过滤词汇单轨门禁（canonical-search-contract REQ-004 / GWT-003）。

App enum、api-edge GraphQL schema、api-edge owner 映射表与 search-service
校验函数四处的 objectTypes/contentTypes 词汇必须同源：

  GraphQL 枚举  CONTENT_POST/...  + ARTICLE/IMAGE/VIDEO
  canonical     content.post/user.profile/entity.homepage/circle.circle/
                circle.group/location.place + article/image/video
  内部 target   article/photo/video/user/entity/circle/group/location
                （只允许存在于 runtime/search 实现内部，不得出现在任何 wire）

历史断链：api-edge 把 GraphQL 枚举翻译成 canonical 词汇，而 search-service
只接受内部 target 词汇，导致携带 objectTypes 的正式搜索 100% 返回 400，
且 api-edge 集成测试的 owner 替身掩盖了分裂。本门禁把四处词汇钉死在同一
组绑定上，任一处漂移即 BLOCK。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 单一期望绑定（与 contracts/metadata/_shared/search_objects.yaml 的
# object_types + ai_targets 对齐；此处是门禁的比对基准，不是第二真相源——
# 四个实现位点必须同时命中同一组值，改词汇必须四处齐改并更新本基准）。
EXPECTED_OBJECT_BINDINGS = {
    "CIRCLE": "circle.circle",
    "CIRCLE_GROUP": "circle.group",
    "CONTENT_POST": "content.post",
    "ENTITY_HOMEPAGE": "entity.homepage",
    "LOCATION_PLACE": "location.place",
    "USER_PROFILE": "user.profile",
}
EXPECTED_CONTENT_BINDINGS = {
    "ARTICLE": "article",
    "IMAGE": "image",
    "VIDEO": "video",
}
INTERNAL_TARGET_WORDS = {"photo"}  # target 专属词汇，出现在 wire 词表即为泄漏

GRAPHQL_SCHEMA = ROOT / (
    "quwoquan_service/services/api-edge/resources/policies/graphql_read/schema.graphqls"
)
EDGE_EXECUTOR = ROOT / (
    "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/"
    "infrastructure/owner/search_page_query_executor.go"
)
SEARCH_CANONICAL = ROOT / "quwoquan_service/runtime/search/canonical_object_types.go"
APP_ENUM = ROOT / (
    "quwoquan_app/packages/quwoquan_cloud_contracts/lib/src/gateway/"
    "gateway_operation_contracts.g.dart"
)

failures: list[str] = []


def fail(message: str) -> None:
    failures.append(message)


def read(path: Path) -> str:
    if not path.is_file():
        fail(f"missing vocabulary source: {path.relative_to(ROOT)}")
        return ""
    return path.read_text(encoding="utf-8")


def parse_graphql_enum(text: str, name: str) -> set[str]:
    match = re.search(rf"enum {name} \{{([^}}]*)\}}", text)
    if match is None:
        fail(f"GraphQL schema is missing enum {name}")
        return set()
    return {token for token in match.group(1).split() if token}


def parse_go_bindings(text: str, variable: str) -> dict[str, str]:
    match = re.search(
        rf"var {variable} = map\[string\]string\{{(.*?)\n\}}", text, re.DOTALL
    )
    if match is None:
        fail(f"api-edge executor is missing {variable}")
        return {}
    return dict(re.findall(r'"([A-Z_]+)":\s*"([a-z.]+)"', match.group(1)))


def main() -> int:
    graphql = read(GRAPHQL_SCHEMA)
    executor = read(EDGE_EXECUTOR)
    canonical = read(SEARCH_CANONICAL)
    app_enum = read(APP_ENUM)
    if failures:
        print("GATE_BLOCK: search wire vocabulary sources are missing")
        for failure in failures:
            print(f"- {failure}")
        return 1

    # 1) GraphQL schema 枚举 == 期望枚举集。
    schema_objects = parse_graphql_enum(graphql, "SearchPageObjectType")
    schema_contents = parse_graphql_enum(graphql, "SearchPageContentType")
    if schema_objects != set(EXPECTED_OBJECT_BINDINGS):
        fail(
            "GraphQL SearchPageObjectType drifted: "
            f"{sorted(schema_objects)} != {sorted(EXPECTED_OBJECT_BINDINGS)}"
        )
    if schema_contents != set(EXPECTED_CONTENT_BINDINGS):
        fail(
            "GraphQL SearchPageContentType drifted: "
            f"{sorted(schema_contents)} != {sorted(EXPECTED_CONTENT_BINDINGS)}"
        )

    # 2) api-edge 映射表 == 期望绑定（枚举名与 canonical 值逐对绑定）。
    edge_objects = parse_go_bindings(executor, "searchObjectTypeBindings")
    edge_contents = parse_go_bindings(executor, "searchContentTypeBindings")
    if edge_objects != EXPECTED_OBJECT_BINDINGS:
        fail(f"api-edge searchObjectTypeBindings drifted: {edge_objects}")
    if edge_contents != EXPECTED_CONTENT_BINDINGS:
        fail(f"api-edge searchContentTypeBindings drifted: {edge_contents}")

    # 3) search-service 校验词汇必须逐个声明全部 canonical 值。
    for canonical_value in EXPECTED_OBJECT_BINDINGS.values():
        if f'"{canonical_value}"' not in canonical:
            fail(f"runtime/search canonical vocabulary is missing {canonical_value!r}")
    for canonical_value in EXPECTED_CONTENT_BINDINGS.values():
        if f'"{canonical_value}"' not in canonical:
            fail(
                "runtime/search canonical content vocabulary is missing "
                f"{canonical_value!r}"
            )

    # 4) App 生成枚举 wireName 必须与 GraphQL 枚举一致。
    app_object_wires = set(
        re.findall(r'^\s+\w+\("([A-Z_]+)"\)[,;]$', app_enum, re.MULTILINE)
    )
    for wire in EXPECTED_OBJECT_BINDINGS:
        if wire not in app_object_wires:
            fail(f"App SearchPageObjectType wireName is missing {wire!r}")
    for wire in EXPECTED_CONTENT_BINDINGS:
        if wire not in app_object_wires:
            fail(f"App SearchPageContentType wireName is missing {wire!r}")

    # 5) 内部 target 专属词汇不得泄漏进任何 wire 词表。
    for word in INTERNAL_TARGET_WORDS:
        if re.search(rf'"{word.upper()}"', graphql):
            fail(f"internal target word {word!r} leaked into the GraphQL schema")
        if word.upper() in edge_objects or word.upper() in edge_contents:
            fail(f"internal target word {word!r} leaked into api-edge bindings")

    if failures:
        print("GATE_BLOCK: search wire vocabulary single-track drifted")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(
        "[search-wire-vocabulary] OK: "
        f"objectTypes={len(EXPECTED_OBJECT_BINDINGS)} "
        f"contentTypes={len(EXPECTED_CONTENT_BINDINGS)} sources=4"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
