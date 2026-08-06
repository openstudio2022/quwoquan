import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart'
    show ChatMessageView;

void main() {
  test('ChatMessageViewData 只消费 generated 公开消息投影字段', () {
    final wire = ChatMessageView.fromWire(<String, dynamic>{
      'id': 'm1',
      'conversationId': 'c1',
      'seq': 1,
      'clientMsgId': 'client-m1',
      'senderId': 'current_sender',
      'senderName': '记录分身名',
      'senderAvatar': 'https://example.com/snapshot.jpg',
      'type': 'text',
      'content': 'hello',
      'status': 'sent',
      'timestamp': '2026-01-01T00:00:00.000Z',
    });
    final dto = ChatMessageViewData.fromWire(wire);

    expect(dto.senderId, 'current_sender');
    expect(dto.senderName, '记录分身名');
    expect(dto.senderAvatar, 'https://example.com/snapshot.jpg');
  });
}
