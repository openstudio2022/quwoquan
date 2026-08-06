from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCAFFOLD = ROOT / "quwoquan_ops" / "gate" / "scaffold"
if str(SCAFFOLD) not in sys.path:
    sys.path.insert(0, str(SCAFFOLD))

from test_directory_layout_lib import (
    go_has_test_entrypoint,
    iter_canonical_files,
    evidence_path_is_canonical,
)


CANONICAL_APP_LOCATION_TEST = (
    "quwoquan_app/test/local_contract/runtime/di/"
    "create_location_service_provider__local_contract_test.dart"
)
CANONICAL_APP_PYTHON_TEST = (
    "quwoquan_app/test/local_contract/runtime/"
    "ios_runtime_dart_defines__local_contract_test.py"
)


def test_app_local_contract_is_canonical_after_mock_package_retirement() -> None:
    assert evidence_path_is_canonical(CANONICAL_APP_LOCATION_TEST)
    assert not evidence_path_is_canonical(
        "quwoquan_app/packages/quwoquan_cloud_mock/test/integration/alpha_location_query_test.dart"
    )


def test_app_local_contract_is_inventory_visible() -> None:
    paths = {path.relative_to(ROOT).as_posix() for _, path, _ in iter_canonical_files()}
    assert CANONICAL_APP_LOCATION_TEST in paths
    assert CANONICAL_APP_PYTHON_TEST in paths


def test_embedded_real_service_integration_test_is_canonical() -> None:
    embedded = (
        "quwoquan_service/services/content-service/tests/api_integration/"
        "content/post/import/mongo_import__api_integration_test.go"
    )
    assert evidence_path_is_canonical(embedded)
    layers = {
        path.relative_to(ROOT).as_posix(): layer
        for _, path, layer in iter_canonical_files()
    }
    assert layers[embedded] == "api_integration"


def test_go_entrypoint_parser_accepts_gofmt_multiline_signature(
    tmp_path: Path,
) -> None:
    multiline = tmp_path / "multiline_test.go"
    multiline.write_text(
        "package contract_test\n\n"
        "import \"testing\"\n\n"
        "func TestContract(\n"
        "\tt *testing.T,\n"
        ") {\n"
        "\tt.Parallel()\n"
        "}\n",
        encoding="utf-8",
    )
    helper = tmp_path / "helper_test.go"
    helper.write_text("package contract_test\n", encoding="utf-8")

    assert go_has_test_entrypoint(multiline)
    assert not go_has_test_entrypoint(helper)
