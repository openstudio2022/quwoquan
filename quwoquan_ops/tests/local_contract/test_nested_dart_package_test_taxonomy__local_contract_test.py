from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCAFFOLD = ROOT / "quwoquan_ops" / "gate" / "scaffold"
if str(SCAFFOLD) not in sys.path:
    sys.path.insert(0, str(SCAFFOLD))

from test_directory_inventory_lib import iter_canonical_files, recorded_file_is_canonical


CANONICAL_ALPHA_LOCATION_TEST = (
    "quwoquan_app/packages/quwoquan_cloud_mock/test/local_contract/"
    "integration/alpha_location_query__local_contract_test.dart"
)


def test_nested_dart_package_local_contract_is_canonical() -> None:
    assert recorded_file_is_canonical(CANONICAL_ALPHA_LOCATION_TEST)
    assert not recorded_file_is_canonical(
        "quwoquan_app/packages/quwoquan_cloud_mock/test/integration/alpha_location_query_test.dart"
    )


def test_nested_dart_package_local_contract_is_inventory_visible() -> None:
    paths = {path.relative_to(ROOT).as_posix() for _, path, _ in iter_canonical_files()}
    assert CANONICAL_ALPHA_LOCATION_TEST in paths


def test_embedded_real_service_integration_test_is_canonical() -> None:
    embedded = (
        "quwoquan_service/services/content-service/cmd/import/"
        "mongo_import__api_integration_test.go"
    )
    assert recorded_file_is_canonical(embedded)
    layers = {
        path.relative_to(ROOT).as_posix(): layer
        for _, path, layer in iter_canonical_files()
    }
    assert layers[embedded] == "api_integration"
