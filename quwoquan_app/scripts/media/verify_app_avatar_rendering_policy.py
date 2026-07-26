#!/usr/bin/env python3
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
LIB = ROOT / "quwoquan_app/lib"
MEDIA_ROOT = ROOT / "quwoquan_service/contracts/metadata/_shared/test_fixtures/media"
CHAT_FIXTURE = (
    ROOT
    / "quwoquan_service/services/chat-service/tests/support/contract_fixtures/scenarios/chat_scenarios.json"
)

violations = []

if (LIB / "components/avatar/group_avatar_grid.dart").exists():
    violations.append("components/avatar/group_avatar_grid.dart must be removed")

production_refs = []
for path in LIB.rglob("*.dart"):
    rel = path.relative_to(LIB).as_posix()
    text = path.read_text(errors="ignore")
    if "GroupAvatarGrid" in text or "group_avatar_grid.dart" in text:
        production_refs.append(rel)

if production_refs:
    violations.append(
        "GroupAvatarGrid production references are forbidden: "
        + ", ".join(sorted(production_refs))
    )

if CHAT_FIXTURE.is_file():
    payload = json.loads(CHAT_FIXTURE.read_text(encoding="utf-8"))
    seed_sets = payload.get("seedSets") or {}
    chat_core = seed_sets.get("chat_core") or {}
    for conversation in chat_core.get("conversations") or []:
        if conversation.get("type") != "group":
            continue
        object_key = str(conversation.get("avatarUrl") or "").strip()
        conversation_id = str(conversation.get("id") or "").strip()
        if not object_key.startswith("media/avatar/"):
            violations.append(
                "chat contract group avatar must use media/avatar: "
                f"{conversation_id}={object_key}"
            )
            continue
        if not (MEDIA_ROOT / object_key).is_file():
            violations.append(
                "chat contract group avatar must be materialized in shared "
                f"media fixtures: {object_key}"
            )

prototype = LIB / "core/mock/prototype_mock_data.dart"
if prototype.exists():
    proto_text = prototype.read_text(errors="ignore")
    if "mockChatContactAvatarFor" not in proto_text:
        violations.append(
            "PrototypeMockData must normalize chat contact avatars to media/avatar"
        )

avatar_bypass_pattern = re.compile(
    r"(avatar|authorAvatar|avatarUrl)[\s\S]{0,160}\b(NetworkImage|CachedNetworkImage|Image\.network)\s*\(",
    re.IGNORECASE,
)
for rel in (
    "components/comment_system/comment_viewer_modal.dart",
    "components/media/shared/toolbar/immersive_engagement_bar.dart",
    "components/media/shared/toolbar/media_viewer_toolbar.dart",
    "ui/discovery/pages/discovery_page.dart",
    "ui/discovery/widgets/home_multi_form_feed.dart",
    "ui/discovery/widgets/works_immersive_viewer.dart",
):
    path = LIB / rel
    if not path.exists():
        continue
    if avatar_bypass_pattern.search(path.read_text(errors="ignore")):
        violations.append(f"{rel}: avatar image bypass must use RoundedSquareAvatar/AppAvatarImage")

if violations:
    print("[app-avatar-rendering-policy] FAIL")
    print("\n".join(violations))
    sys.exit(2)

print("[app-avatar-rendering-policy] OK")
