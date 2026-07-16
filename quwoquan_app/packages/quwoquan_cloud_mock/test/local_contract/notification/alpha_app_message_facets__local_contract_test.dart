import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';
import 'package:test/test.dart';

void main() {
  test('alpha Notification adapter preserves ack/read semantics', () async {
    final adapter = AlphaAppMessageAdapter();

    final initial = await adapter.getUnreadCount(
      const GetAppMessageUnreadCountQuery(),
    );
    expect(initial.unreadCount, 2);

    final acked = await adapter.acknowledge(
      const AckAppMessageCommand(
        messageId: 'fixture_app_message_assistant_stock',
      ),
    );
    expect(acked.ackedAt, isNotNull);
    expect(acked.read, isFalse);

    final read = await adapter.markRead(
      const ReadAppMessageCommand(
        messageId: 'fixture_app_message_assistant_stock',
      ),
    );
    expect(read.read, isTrue);
    expect(read.readAt, isNotNull);

    final converged = await adapter.getUnreadCount(
      const GetAppMessageUnreadCountQuery(),
    );
    expect(converged.unreadCount, 1);
  });

  test('alpha Notification list uses typed filtering and limit', () async {
    final adapter = AlphaAppMessageAdapter();

    final result = await adapter.listAppMessages(
      const ListAppMessagesQuery(messageType: 'chat', limit: 1),
    );

    expect(result.items, hasLength(1));
    expect(result.items.single.messageType, 'chat');
  });
}
