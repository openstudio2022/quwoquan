#!/usr/bin/env python3

import sys
from pathlib import Path

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

import re

ROOT = REPO_ROOT
LIB = ROOT / "quwoquan_app/lib"
MEDIA_ROOT = ROOT / "quwoquan_service/contracts/metadata/_shared/test_fixtures/media"
CHAT_OBJECT_BUILDER = (
    ROOT
    / "quwoquan_app/test/support/runtime/fixtures/object_scenario_builders.dart"
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

if not CHAT_OBJECT_BUILDER.is_file():
    violations.append("chat object builder must exist")
else:
    builder = CHAT_OBJECT_BUILDER.read_text(encoding="utf-8")
    avatar_template = "media/avatar/s/archived-avatar/group/$id/v1/composite.png"
    if avatar_template not in builder:
        violations.append(
            f"chat object builder must use canonical group avatar template: {avatar_template}"
        )
    for conversation_id in ("fixture_conv_group", "fixture_conv_photo_group"):
        object_key = (
            f"media/avatar/s/archived-avatar/group/{conversation_id}/v1/composite.png"
        )
        if conversation_id not in builder:
            violations.append(f"chat object builder must retain {conversation_id}")
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
