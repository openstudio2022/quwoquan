"""GWT-034：canonical publish execution 的静态闭包不加载退役五家族。"""
from __future__ import annotations

from pathlib import Path

from verify.legacy_runtime_entries import scan_live_python_import_graph


SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"


def test_publish_execution_static_import_graph_reaches_no_retired_family() -> None:
    scan = scan_live_python_import_graph(
        scripts_root=SCRIPTS_ROOT,
        entry_modules=(
            "content.release.canonical.publish_execution",
            "content.execution.closure.pool_delivery",
        ),
    )

    retired_family_refs = tuple(
        ref for ref in scan.legacy_entry_refs if "#retired live import " in ref
    )
    assert scan.scan_errors == ()
    assert retired_family_refs == ()
