#!/usr/bin/env python3
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
LIB = ROOT / "quwoquan_app/lib"
MEDIA_ROOT = ROOT / "quwoquan_service/contracts/metadata/_shared/test_fixtures/media"

violations = []
group_avatar_call_re = re.compile(r"groupAvatarFor\('([^']+)'\)")

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

chat_mock_data = LIB / "cloud/services/chat/mock/chat_mock_data.dart"
if chat_mock_data.exists():
    text = chat_mock_data.read_text(errors="ignore")
    forbidden_mock_patterns = (
        "avatarFor('grid_",
        "avatarFor('hiking')",
        "avatarFor('photo')",
        "avatarFor('product-collab')",
    )
    for pattern in forbidden_mock_patterns:
        if pattern in text:
            violations.append(
                "chat mock group conversations must use groupAvatarFor(), "
                f"found {pattern}"
            )
    conversation_ids = {
        match.group(1)
        for match in group_avatar_call_re.finditer(text)
        if "$" not in match.group(1)
    }
    if "groupAvatarFor('conv_grid_$n')" in text:
        conversation_ids.update(f"conv_grid_{index}" for index in range(1, 17))
    for conversation_id in sorted(conversation_ids):
        object_key = (
            "media/avatar/s/archived-avatar/conversation/"
            f"{conversation_id}/v1/mock.png"
        )
        if not (MEDIA_ROOT / object_key).is_file():
            violations.append(
                "chat mock group avatar must be materialized in shared media "
                f"fixtures: {object_key}"
            )
    contact_groups = re.search(
        r"contactTabFunGroups[\s\S]*?=>\s*\[[\s\S]*?\n\s*\];",
        text,
    )
    if contact_groups and "media/image/" in contact_groups.group(0):
        violations.append(
            "contactTabFunGroups group avatars must use media/avatar object "
            "keys, not media/image placeholders"
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
