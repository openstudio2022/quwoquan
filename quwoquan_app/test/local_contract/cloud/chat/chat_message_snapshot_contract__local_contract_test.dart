import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_dto.g.dart';

void main() {
  test('ChatMessageDto 只消费 canonical 记录快照字段', () {
    final dto = ChatMessageDto.fromMap(<String, dynamic>{
      'id': 'm1',
      'conversationId': 'c1',
      'seq': 1,
      'clientMsgId': 'client-m1',
      'senderId': 'current_sender',
      'senderDisplayNameSnapshot': '记录分身名',
      'senderAvatarUrlSnapshot': 'https://example.com/snapshot.jpg',
      'type': 'text',
      'content': 'hello',
      'status': 'sent',
      'timestamp': '2026-01-01T00:00:00.000Z',
    });

    expect(dto.senderId, 'current_sender');
    expect(dto.senderName, '记录分身名');
    expect(dto.senderAvatar, 'https://example.com/snapshot.jpg');
  });
}
