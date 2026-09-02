from __future__ import annotations

import hashlib
import json
from pathlib import Path

from verify.legacy_runtime_entries import scan_live_python_import_graph
from verify.verify_public_cli_live_import_zero import (
    FORBIDDEN_PREFIXES,
    PUBLIC_COMMAND_MODULES,
    build_receipt,
)


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


def test_public_cli_live_import_zero_clean_subprocess_closed_receipt() -> None:
    receipt = build_receipt()
    assert receipt["schema"] == "quwoquan_data.public_cli_live_import_zero_receipt"
    assert receipt["sourceFingerprint"].startswith("sha256:")
    assert receipt["command"] == {
        "commandId": "data.public_cli.live_import_zero",
        "entrypoint": "quwoquan_data/scripts/cli.py",
        "arguments": ["governance", "public-cli-live-import-zero"],
    }
    assert receipt["forbiddenPrefixes"] == list(FORBIDDEN_PREFIXES)
    assert receipt["importedModules"] == sorted(PUBLIC_COMMAND_MODULES)
    assert receipt["forbiddenLoadedModules"] == []
    assert receipt["verdict"] == "pass"
    assert receipt["exitCode"] == 0
    assert receipt["capturedOutput"]["stdoutDigest"].startswith("sha256:")
    assert receipt["capturedOutput"]["stderrDigest"].startswith("sha256:")
    identity = {
        "sourceFingerprint": receipt["sourceFingerprint"],
        "probeDigest": receipt["probeDigest"],
        "checkedCommands": receipt["checkedCommands"],
        "forbiddenPrefixes": receipt["forbiddenPrefixes"],
        "loadedModulesDigest": receipt["loadedModulesDigest"],
    }
    expected_id = "sha256:" + hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    ).hexdigest()
    assert receipt["receiptId"] == expected_id
