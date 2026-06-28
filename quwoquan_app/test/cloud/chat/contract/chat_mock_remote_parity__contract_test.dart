import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/chat/mock/chat_repository_mock.dart';
import 'package:quwoquan_app/core/mock/prototype_mock_data.dart';

void main() {
  group('chat mock remote parity contract', () {
    test('MockChatRepository contact rows only use media/avatar object keys', () async {
      final repo = MockChatRepository();
      final contacts = await repo.listContacts(limit: 500);
      expect(contacts, isNotEmpty);
      for (final contact in contacts) {
        expect(
          contact.avatarUrl.toLowerCase().startsWith('media/avatar/'),
          isTrue,
          reason: '${contact.userId} avatar=${contact.avatarUrl}',
        );
      }
    });

    test('listContactHome all includes user rows with contract avatars', () async {
      final repo = MockChatRepository();
      final rows = await repo.listContactHome(filter: 'all', limit: 500);
      expect(rows.where((row) => row.kind == 'user'), isNotEmpty);
      for (final row in rows) {
        if (row.avatarUrl.trim().isEmpty) {
          continue;
        }
        expect(
          row.avatarUrl.toLowerCase().startsWith('media/avatar/'),
          isTrue,
          reason: '${row.id} avatar=${row.avatarUrl}',
        );
      }
    });

    test('listMessageHome notification filter matches cloud empty contract', () async {
      final repo = MockChatRepository();
      final rows = await repo.listMessageHome(filter: 'notification', limit: 50);
      expect(rows, isEmpty);
    });

    test('prototype chatMockContacts normalize avatars to media/avatar', () {
      for (final contact in PrototypeMockData.chatMockContacts) {
        final avatar = contact['avatar']?.toString() ?? '';
        expect(
          avatar.toLowerCase().startsWith('media/avatar/'),
          isTrue,
          reason: '${contact['id']} avatar=$avatar',
        );
      }
    });
  });
}
