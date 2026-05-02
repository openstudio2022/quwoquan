import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';

void main() {
  group('ChatMessageNotifier', () {
    test('loadMessages fills missing sender snapshots from members', () async {
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(MockChatRepository()),
        ],
      );
      addTearDown(container.dispose);

      final notifier = container.read(
        chatMessageProvider('fixture_conv_direct').notifier,
      );
      await notifier.loadMessages();

      final state = container.read(chatMessageProvider('fixture_conv_direct'));
      final friendMessage = state.messages.firstWhere(
        (message) => message.senderId == 'fixture_user_friend',
      );
      final selfMessage = state.messages.firstWhere(
        (message) => message.senderId == 'fixture_user_current',
      );

      expect(friendMessage.senderName, '契约好友');
      expect(friendMessage.senderAvatar, startsWith('https://'));
      expect(selfMessage.senderName, '我');
      expect(selfMessage.senderAvatar, startsWith('https://'));
    });
  });
}
