from __future__ import annotations

from pathlib import Path

from verify.legacy_runtime_entries import scan_live_python_import_graph


SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def test_public_cli_live_import_graph_reaches_no_retired_or_sdk_runtime() -> None:
    scan = scan_live_python_import_graph(scripts_root=SCRIPTS)
    assert scan.scan_errors == ()
    assert scan.legacy_entry_refs == ()


def test_live_import_gate_blocks_retired_family_sdk_and_reliabletask(tmp_path: Path) -> None:
    (tmp_path / "cli.py").write_text(
        "import content.execution.controller\nimport cursor_sdk\nReliableTask = object()\n",
        encoding="utf-8",
    )
    scan = scan_live_python_import_graph(scripts_root=tmp_path)
    assert any("retired live import content.execution.controller" in ref for ref in scan.legacy_entry_refs)
    assert any("forbidden runtime import cursor_sdk" in ref for ref in scan.legacy_entry_refs)
    assert any("forbidden Data worker/fleet runtime" in ref for ref in scan.legacy_entry_refs)
