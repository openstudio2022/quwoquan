# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/repository-layout-hygiene-and-retirement/spec.md#gwt-002
"""契约视图只投影契约文档，不投影 fixture 媒体载荷。

`_shared/test_fixtures` 是 canonical 树里唯一同时存放契约文档和「文档所描述的媒体
字节」的地方。逐份拷贝那些字节曾让单个视图 680MB 里有 670MB 是死重量，而载荷没有
任何视图消费方：metadata loader 的三处 WalkDir 都对 `test_fixtures` SkipDir，真正读
字节的 gate 与环境脚本一律直接读 canonical 路径。

四向断言：文档必须在（否则 ContractGraph 的 source digest 集会变）、载荷必须不在、
fixture 树之外的非 YAML 文件不得被过滤误伤、纯载荷目录不得留下空壳。
"""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "quwoquan_service" / "scripts" / "contracts"))

import build_service_contract_view as builder  # noqa: E402

CANONICAL_FIXTURES = (
    ROOT / "quwoquan_service/contracts/metadata/_shared/test_fixtures"
)
VIEW_FIXTURES = "_shared/test_fixtures"


@pytest.fixture(scope="module")
def view(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """构建一份真实视图。外部输出根让 `prune_sibling_views` 不触碰仓库缓存。"""
    external = tmp_path_factory.mktemp("contract-view-projection")
    return builder.build(
        ROOT,
        external / "cache" / "view",
        external_output_root=external,
    )


def canonical_fixture_files() -> list[Path]:
    return [path for path in CANONICAL_FIXTURES.rglob("*") if path.is_file()]


def test_fixture_contract_documents_are_projected_with_identical_bytes(view: Path) -> None:
    """文档是编译器真实读取集：少一个，ContractGraph 的 sources 就变了。"""
    documents = [
        path
        for path in canonical_fixture_files()
        if path.suffix.lower() in builder.FIXTURE_DOCUMENT_SUFFIXES
    ]
    assert documents, "canonical fixture 树必须仍有契约文档，否则本断言是空扫描"

    for source in documents:
        projected = view / VIEW_FIXTURES / source.relative_to(CANONICAL_FIXTURES)
        assert projected.is_file(), f"契约文档未进视图: {source.relative_to(ROOT)}"
        assert projected.read_bytes() == source.read_bytes()


def test_fixture_media_payload_never_enters_the_view(view: Path) -> None:
    """载荷的 sha256 已记在随行 descriptor/manifest 里，视图不必再拷字节。"""
    payload = [
        path
        for path in canonical_fixture_files()
        if path.suffix.lower() not in builder.FIXTURE_DOCUMENT_SUFFIXES
    ]
    assert payload, "canonical fixture 树必须仍有媒体载荷，否则本断言是空扫描"

    projected = [
        path.relative_to(view)
        for path in view.rglob("*")
        if path.is_file() and builder.is_fixture_media_payload(path.relative_to(view))
    ]
    assert projected == [], f"视图重新拷贝了媒体载荷: {projected[:5]}"


def test_non_yaml_contract_documents_outside_the_fixture_tree_still_project(
    view: Path,
) -> None:
    """边界：过滤只按 fixture 树定界，不得顺手挡掉别处的非 YAML 契约文档。"""
    assert (view / "_schemas/README.md").is_file()
    assert list((view / "content/content/post/persisted_queries").glob("*.graphql"))


def test_payload_only_directories_leave_no_empty_shell(view: Path) -> None:
    """纯载荷目录若仍被 mkdir，视图里会多出上千个空目录，看起来像内容丢失。"""
    empty = [
        path
        for path in view.rglob("*")
        if path.is_dir() and not any(path.iterdir())
    ]
    assert empty == [], f"视图残留空目录: {empty[:5]}"
