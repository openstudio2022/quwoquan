#!/usr/bin/env python3
"""静态门禁：Chat contract-seeded adapter 与 Remote 契约 parity。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP_LIB = ROOT / "quwoquan_app/lib"
APP_TEST = ROOT / "quwoquan_app/test"
APP_ADAPTER = ROOT / "quwoquan_app/runners/alpha/lib/alpha_chat_repository.dart"
ALPHA_COMPOSITION = (
    ROOT / "quwoquan_app/runners/alpha/lib/alpha_cloud_composition.dart"
)
TEST_ADAPTER = (
    ROOT / "quwoquan_app/test/support/cloud_services/chat_repository_mock.dart"
)
TEST_ADAPTER_GENERATOR = (
    ROOT / "quwoquan_app/scripts/chat/generate_chat_test_adapter.py"
)
CHAT_CONTRACTS_BARREL = (
    ROOT / "quwoquan_app/packages/quwoquan_cloud_contracts/lib/chat_contracts.dart"
)
CHAT_MOCK_BARREL = (
    ROOT / "quwoquan_app/packages/quwoquan_cloud_mock/lib/chat_fixture.dart"
)
ENGINE = (
    ROOT
    / "quwoquan_app/packages/quwoquan_cloud_mock/lib/src/chat/alpha_chat_state_engine.dart"
)
ENGINE_CONVERSATIONS = ENGINE.with_name("alpha_chat_state_engine_conversations.dart")
ENGINE_GROUPS = ENGINE.with_name("alpha_chat_state_engine_groups.dart")
MESSAGE_WRITER = ENGINE.with_name("alpha_message_writer.dart")
PROTOTYPE = ROOT / "quwoquan_app/lib/core/mock/prototype_mock_data.dart"
CHAT_FIXTURE = (
    ROOT
    / "quwoquan_service/services/chat-service/tests/support/contract_fixtures/scenarios/chat_scenarios.json"
)
GO_HANDLER_SUPPORT = (
    ROOT
    / "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/http/chat_handler_support.go"
)

violations: list[str] = []


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _fail(message: str) -> None:
    violations.append(message)


def _scan_avatar_media_plane() -> None:
    payload = json.loads(_read(CHAT_FIXTURE))
    seed_sets = payload.get("seedSets") or {}
    contacts = (seed_sets.get("chat_contacts_core") or {}).get("contacts") or []
    for contact in contacts:
        avatar = str(contact.get("avatarUrl") or "").strip().lower()
        if not avatar.startswith("media/avatar/"):
            _fail(
                "chat_contacts_core uses non-avatar media plane: "
                f"{contact.get('userId')}={avatar}"
            )


def _check_mock_repository() -> None:
    adapter = _read(APP_ADAPTER)
    alpha_composition = _read(ALPHA_COMPOSITION)
    engine_main = _read(ENGINE)
    message_writer = _read(MESSAGE_WRITER)
    test_adapter = _read(TEST_ADAPTER)
    if "AlphaChatStateEngine" not in adapter:
        _fail("alpha/test App adapter must delegate to AlphaChatStateEngine")
    if "package:quwoquan_cloud_mock/chat_fixture.dart" not in adapter:
        _fail("alpha App adapter must use the narrow chat fixture package entry")
    if "package:quwoquan_cloud_contracts/chat_contracts.dart" not in engine_main:
        _fail("chat state engine must use the narrow chat contracts entry")
    if "AppContentPrototypeBundle" in adapter or "chatMockContacts" in adapter:
        _fail("alpha/test App adapter must not merge prototype contacts")
    generated_header = (
        "// Code generated from runners/alpha/lib/alpha_chat_repository.dart. "
        "DO NOT EDIT.\n"
    )
    if test_adapter != generated_header + adapter:
        _fail(
            "test support adapter must be the generated copy of the alpha "
            "DTO mapper; run generate_chat_test_adapter.py"
        )
    shared_engine_snippets = (
        "final chatState = AlphaChatStateEngine();",
        "MockChatRepository(engine: chatState)",
        "AlphaChatMessageCommandWriter(engine: chatState)",
    )
    for snippet in shared_engine_snippets:
        if snippet not in alpha_composition:
            _fail(f"alpha composition must share one chat state engine: {snippet}")
    if (
        "_nextSeqByConversation" in message_writer
        or "_receipts" in message_writer
        or "_engine.sendMessage(command)" not in message_writer
    ):
        _fail("alpha message writer must delegate all state to AlphaChatStateEngine")
    production_hits: list[str] = []
    for path in APP_LIB.rglob("*.dart"):
        text = _read(path)
        if (
            "MockChatRepository" in text
            or "ChatMockData" in text
            or "cloud/services/chat/mock/" in text
        ):
            production_hits.append(path.relative_to(APP_LIB).as_posix())
    if production_hits:
        _fail(
            "production lib retains chat mock symbols/imports: "
            + ", ".join(sorted(production_hits))
        )
    stale_test_imports: list[str] = []
    invalid_test_imports: list[str] = []
    chat_adapter_import = re.compile(
        r"import\s+['\"]([^'\"]*chat_repository_mock\.dart)['\"]"
    )
    for path in APP_TEST.rglob("*.dart"):
        text = _read(path)
        rel = path.relative_to(APP_TEST).as_posix()
        if (
            "package:quwoquan_app/cloud/services/chat/mock/" in text
            or re.search(
                r"import\s+['\"][^'\"]*runners/alpha/lib/"
                r"alpha_chat_repository\.dart['\"]",
                text,
            )
        ):
            stale_test_imports.append(rel)
        for match in chat_adapter_import.finditer(text):
            resolved = (path.parent / match.group(1)).resolve()
            if resolved != TEST_ADAPTER.resolve():
                invalid_test_imports.append(f"{rel}: {match.group(1)}")
    if stale_test_imports:
        _fail(
            "tests retain production chat mock imports: "
            + ", ".join(sorted(stale_test_imports))
        )
    if invalid_test_imports:
        _fail(
            "tests resolve chat adapter imports outside test/support: "
            + ", ".join(sorted(invalid_test_imports))
        )


def _check_notification_filter_parity() -> None:
    mock = _read(ENGINE_CONVERSATIONS)
    go_support = _read(GO_HANDLER_SUPPORT)
    mock_has_notification_false = "'notification' => false" in mock
    go_has_notification_false = (
        'case "notification":' in go_support and "return false" in go_support
    )
    if mock_has_notification_false != go_has_notification_false:
        _fail("listMessageHome(notification) filter parity drift between Mock and Go handler")


def _check_mock_no_op_bypasses() -> None:
    text = _read(ENGINE_GROUPS) + "\n" + _read(ENGINE_CONVERSATIONS)
    if re.search(r"void inviteAssistant[\s\S]{0,220}\)\s*\{\s*\}", text):
        _fail("AlphaChatStateEngine.inviteAssistant must not be an empty no-op")
    receipts_start = text.find("List<ChatFixtureObject> getReceipts")
    receipts_end = text.find(
        "List<ChatFixtureObject> getConversationTimestamps",
        receipts_start,
    )
    receipts_body = text[receipts_start:receipts_end]
    if receipts_start < 0 or "'userId': currentUserId" not in receipts_body:
        _fail("AlphaChatStateEngine.getReceipts must not always return an empty list")


def _check_prototype_contact_normalization() -> None:
    text = _read(PROTOTYPE)
    if "mockChatContactAvatarFor" not in text:
        _fail("PrototypeMockData.chatMockContacts must normalize avatars via mockChatContactAvatarFor")
    if "..['avatar'] = mockChatContactAvatarFor(id)" not in text:
        _fail("chatMockContacts getter must rewrite avatar to media/avatar object keys")


def main() -> int:
    required = (
        APP_ADAPTER,
        ALPHA_COMPOSITION,
        TEST_ADAPTER,
        TEST_ADAPTER_GENERATOR,
        CHAT_CONTRACTS_BARREL,
        CHAT_MOCK_BARREL,
        ENGINE,
        ENGINE_CONVERSATIONS,
        ENGINE_GROUPS,
        MESSAGE_WRITER,
        CHAT_FIXTURE,
    )
    missing = [path for path in required if not path.is_file()]
    if missing:
        for path in missing:
            _fail(f"missing {path}")
    else:
        _check_mock_repository()
        _scan_avatar_media_plane()
    if PROTOTYPE.is_file():
        _check_prototype_contact_normalization()
    _check_mock_no_op_bypasses()
    _check_notification_filter_parity()
    if violations:
        print("verify_chat_mock_remote_parity: FAIL", file=sys.stderr)
        for item in violations:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_chat_mock_remote_parity: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
