#!/usr/bin/env python3
"""静态门禁：Chat Mock 与 Remote 契约 parity（禁止 prototype 联系人合并、avatar 平面泄漏）。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MOCK_REPO = ROOT / "quwoquan_app/lib/cloud/services/chat/mock/chat_repository_mock.dart"
PROTOTYPE = ROOT / "quwoquan_app/lib/core/mock/prototype_mock_data.dart"
CHAT_MOCK_DATA = ROOT / "quwoquan_app/lib/cloud/services/chat/mock/chat_mock_data.dart"
GO_HANDLER_SUPPORT = (
    ROOT
    / "quwoquan_service/services/chat-service/internal/adapters/http/chat_handler_support.go"
)

violations: list[str] = []


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _fail(message: str) -> None:
    violations.append(message)


def _scan_avatar_media_plane(path: Path, label: str) -> None:
    text = _read(path)
    for match in re.finditer(r"['\"]avatar(?:Url)?['\"]\s*:\s*['\"]([^'\"]+)['\"]", text):
        value = match.group(1)
        if "media/image/" in value.lower():
            _fail(f"{label} uses media/image avatar plane: {value}")
    for match in re.finditer(r"avatarFor\([^)]+\)", text):
        pass
    for match in re.finditer(r"['\"]media/image/[^'\"]+['\"]", text):
        snippet = match.group(0)
        if "avatar" in text[max(0, match.start() - 40) : match.start()].lower():
            continue
        if "/contact" in label.lower() or "chat_mock" in label.lower():
            if "avatarUrl" in text[max(0, match.start() - 80) : match.end() + 20]:
                _fail(f"{label} contact/circle avatar uses media/image: {snippet}")


def _check_mock_repository() -> None:
    text = _read(MOCK_REPO)
    if "AppContentPrototypeBundle" in text:
        _fail("MockChatRepository must not merge AppContentPrototypeBundle contacts")
    if "chatMockContacts" in text:
        _fail("MockChatRepository must not reference chatMockContacts")


def _check_notification_filter_parity() -> None:
    mock = _read(MOCK_REPO)
    go_support = _read(GO_HANDLER_SUPPORT)
    mock_has_notification_false = "case 'notification':" in mock and "return false" in mock
    go_has_notification_false = (
        'case "notification":' in go_support and "return false" in go_support
    )
    if mock_has_notification_false != go_has_notification_false:
        _fail("listMessageHome(notification) filter parity drift between Mock and Go handler")


def _check_mock_no_op_bypasses() -> None:
    text = _read(MOCK_REPO)
    if re.search(r"Future<void> inviteAssistant[\s\S]{0,220}\)\s*async\s*\{\s*\}", text):
        _fail("MockChatRepository.inviteAssistant must not be an empty no-op")
    if re.search(
        r"Future<List<ChatMessageReceiptDto>> getReceipts[\s\S]{0,220}\)\s*async\s*\{\s*return const <ChatMessageReceiptDto>\[\];\s*\}",
        text,
    ):
        _fail("MockChatRepository.getReceipts must not always return an empty list")


def _check_prototype_contact_normalization() -> None:
    text = _read(PROTOTYPE)
    if "mockChatContactAvatarFor" not in text:
        _fail("PrototypeMockData.chatMockContacts must normalize avatars via mockChatContactAvatarFor")
    if "..['avatar'] = mockChatContactAvatarFor(id)" not in text:
        _fail("chatMockContacts getter must rewrite avatar to media/avatar object keys")


def main() -> int:
    if not MOCK_REPO.is_file():
        _fail(f"missing {MOCK_REPO}")
    else:
        _check_mock_repository()
    if CHAT_MOCK_DATA.is_file():
        _scan_avatar_media_plane(CHAT_MOCK_DATA, "chat_mock_data.dart")
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
