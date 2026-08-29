#!/usr/bin/env python3
"""门禁：群聊 memberCount、名册与 contract 媒体 alias 一致性。"""
from __future__ import annotations


import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

import hashlib
import re

ROOT = REPO_ROOT
LOCAL_MEDIA_ORIGIN = ROOT / "quwoquan_ops/cli/lib/local_media_origin.py"
MEDIA_ROOT = ROOT / "quwoquan_service/contracts/metadata/_shared/test_fixtures/media"
CHAT_OBJECT_BUILDER = (
    ROOT
    / "quwoquan_app/test/support/service/chat_service/chat/conversation/chat_state_seed_builder.dart"
)
PHOTO_GROUP_CONTRACT_TEST = (
    ROOT
    / "quwoquan_app/test/local_contract/service/chat_service/chat/conversation/"
    "chat_settings_page_widget__local_contract_test.dart"
)
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


def _check_builder_contract() -> None:
    if not CHAT_OBJECT_BUILDER.is_file():
        _fail(f"missing chat object builder: {CHAT_OBJECT_BUILDER}")
        return
    text = CHAT_OBJECT_BUILDER.read_text(encoding="utf-8")
    for token in ("fixture_conv_group", "'members'"):
        if token not in text:
            _fail(f"chat object builder must retain {token}")
    if not PHOTO_GROUP_CONTRACT_TEST.is_file():
        _fail(f"missing autonomous photo-group contract: {PHOTO_GROUP_CONTRACT_TEST}")
        return
    if "fixture_conv_photo_group" not in PHOTO_GROUP_CONTRACT_TEST.read_text(
        encoding="utf-8"
    ):
        _fail("photo-group contract must retain fixture_conv_photo_group")


def main() -> int:
    _check_alpha_alias()
    _check_conv_grid_avatar_distinct()
    _check_no_client_side_group_avatar_composite()
    _check_builder_contract()
    if violations:
        print("verify_chat_group_roster_consistency: FAIL", file=sys.stderr)
        for item in violations:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_chat_group_roster_consistency: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
