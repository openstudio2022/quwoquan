#!/usr/bin/env python3
"""门禁：群聊 memberCount、名册、contract seed 与 alpha 媒体 alias 一致性。"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LOCAL_MEDIA_ORIGIN = ROOT / "quwoquan_ops/cli/lib/local_media_origin.py"
MEDIA_ROOT = ROOT / "quwoquan_service/contracts/metadata/_shared/test_fixtures/media"
CHAT_SCENARIOS = (
    ROOT
    / "quwoquan_service/services/chat-service/tests/support/contract_fixtures/scenarios/chat_scenarios.json"
)
CHAT_SCENARIOS_GAMMA = (
    ROOT
    / "quwoquan_service/services/chat-service/tests/support/contract_fixtures/scenarios/chat_scenarios.gamma-curated.json"
)
DART_RUNNER = (
    ROOT / "quwoquan_app/scripts/chat/verify_chat_group_roster_consistency_runner.dart"
)
APP_DIR = ROOT / "quwoquan_app"
LIB = ROOT / "quwoquan_app/lib"

violations: list[str] = []


def _fail(message: str) -> None:
    violations.append(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_alpha_alias() -> None:
    text = LOCAL_MEDIA_ORIGIN.read_text(encoding="utf-8")
    for match in re.finditer(r'"conv_grid_\d+"\s*:', text):
        _fail(
            f"local_media_origin.py must not alias {match.group(0)[:-1]} "
            "to previous composite; serve conv_grid PNG on disk"
        )


def _check_conv_grid_avatar_distinct() -> None:
    conv_grid_12 = (
        MEDIA_ROOT
        / "media/avatar/s/archived-avatar/conversation/conv_grid_12/v1/mock.png"
    )
    previous_composites = (
        MEDIA_ROOT
        / "media/avatar/s/archived-avatar/group/fixture_conv_group/v1/composite.png",
        MEDIA_ROOT
        / "media/avatar/s/archived-avatar/group/fixture_conv_photo_group/v1/composite.png",
    )
    if not conv_grid_12.is_file():
        _fail(f"missing conv_grid_12 precomposed avatar: {conv_grid_12}")
        return
    grid_hash = _sha256(conv_grid_12)
    for previous in previous_composites:
        if not previous.is_file():
            continue
        if grid_hash == _sha256(previous):
            _fail(
                f"conv_grid_12 avatar must differ from previous composite: {previous.name}"
            )


def _check_no_client_side_group_avatar_composite() -> None:
    if (LIB / "components/avatar/group_avatar_grid.dart").exists():
        _fail("components/avatar/group_avatar_grid.dart must be removed")
    forbidden_symbols = ("GroupAvatarGrid", "group_avatar_grid.dart")
    for path in LIB.rglob("*.dart"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for symbol in forbidden_symbols:
            if symbol in text:
                rel = path.relative_to(LIB).as_posix()
                _fail(f"forbidden client-side group avatar composite: {rel} ({symbol})")
                break


def _check_contract_fixture(path: Path, label: str) -> None:
    text = LOCAL_MEDIA_ORIGIN.read_text(encoding="utf-8")
    for match in re.finditer(r'"conv_grid_\d+"\s*:', text):
        _fail(
            f"local_media_origin.py must not alias {match.group(0)[:-1]} "
            "to previous composite; serve conv_grid PNG on disk"
        )


def _check_contract_fixture(path: Path, label: str) -> None:
    if not path.is_file():
        _fail(f"missing contract fixture: {path}")
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    seed_sets = payload.get("seedSets") or {}
    for seed_ref, seed_set in seed_sets.items():
        conversations = seed_set.get("conversations") or []
        members_by_conv = seed_set.get("members") or {}
        for conv in conversations:
            if conv.get("type") != "group":
                continue
            conv_id = (
                conv.get("id")
                or conv.get("_id")
                or conv.get("conversationId")
                or ""
            )
            if not conv_id:
                continue
            declared = conv.get("memberCount")
            roster = members_by_conv.get(conv_id) or []
            if declared != len(roster):
                _fail(
                    f"{label}/{seed_ref} {conv_id}: "
                    f"memberCount={declared} roster={len(roster)}"
                )
            source_ids = conv.get("groupAvatarSourceUserIds") or []
            roster_ids = {m.get("userId") for m in roster if m.get("userId")}
            extra = [uid for uid in source_ids if uid not in roster_ids]
            if extra:
                _fail(
                    f"{label}/{seed_ref} {conv_id}: "
                    f"groupAvatarSourceUserIds not in roster: {extra}"
                )


def _check_mock_dart() -> None:
    if not DART_RUNNER.is_file():
        _fail(f"missing dart runner: {DART_RUNNER}")
        return
    proc = subprocess.run(
        ["dart", "run", str(DART_RUNNER.relative_to(APP_DIR))],
        cwd=APP_DIR,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stdout + proc.stderr).strip()
        _fail(f"AlphaChatStateEngine roster check failed:\n{detail}")


def main() -> int:
    _check_alpha_alias()
    _check_conv_grid_avatar_distinct()
    _check_no_client_side_group_avatar_composite()
    _check_contract_fixture(CHAT_SCENARIOS, "chat_scenarios.json")
    if CHAT_SCENARIOS_GAMMA.is_file():
        _check_contract_fixture(CHAT_SCENARIOS_GAMMA, "chat_scenarios.gamma-curated.json")
    _check_mock_dart()

    if violations:
        print("verify_chat_group_roster_consistency: FAIL", file=sys.stderr)
        for item in violations:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_chat_group_roster_consistency: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
