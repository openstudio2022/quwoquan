from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
GATE = ROOT / "quwoquan_app/scripts/chat_service/chat/verify_chat_group_roster_consistency.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location(
        "verify_chat_group_roster_consistency_companion",
        GATE,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_group_roster_builder_and_photo_group_contract_are_independent(
    tmp_path: Path,
) -> None:
    gate = _load_gate()
    builder = tmp_path / "chat_state_seed_builder.dart"
    photo_contract = tmp_path / "chat_settings_page_widget__local_contract_test.dart"
    builder.write_text("fixture_conv_group {'members': []}\n", encoding="utf-8")
    photo_contract.write_text("fixture_conv_photo_group\n", encoding="utf-8")
    gate.CHAT_OBJECT_BUILDER = builder
    gate.PHOTO_GROUP_CONTRACT_TEST = photo_contract

    gate.violations.clear()
    gate._check_builder_contract()
    assert gate.violations == []

    builder.write_text("fixture_conv_group {}\n", encoding="utf-8")
    gate.violations.clear()
    gate._check_builder_contract()
    assert any("'members'" in violation for violation in gate.violations)

    photo_contract.write_text("unrelated_photo_group\n", encoding="utf-8")
    gate.violations.clear()
    gate._check_builder_contract()
    assert any("fixture_conv_photo_group" in violation for violation in gate.violations)
