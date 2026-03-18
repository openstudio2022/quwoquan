import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_inbox_provider.dart';

void main() {
  group('ChatInboxListNotifier', () {
    test('markConversationRead clears unread and mention counts', () async {
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(MockChatRepository()),
        ],
      );
      addTearDown(container.dispose);

      final notifier = container.read(chatInboxListProvider.notifier);
      await notifier.load(force: true);

      final before = container
          .read(chatInboxListProvider)
          .items
          .firstWhere((item) => item.id == 'conv_006');
      expect(before.unreadCount, greaterThan(0));
      expect(before.mentionUnreadCount, greaterThan(0));

      notifier.markConversationRead('conv_006');

      final after = container
          .read(chatInboxListProvider)
          .items
          .firstWhere((item) => item.id == 'conv_006');
      expect(after.unreadCount, equals(0));
      expect(after.mentionUnreadCount, equals(0));
    });
  });
}
