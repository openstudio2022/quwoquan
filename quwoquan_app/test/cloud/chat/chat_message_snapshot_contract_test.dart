import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_dto.g.dart';

void main() {
  test('ChatMessageDto 优先消费记录快照字段', () {
    final dto = ChatMessageDto.fromMap(<String, dynamic>{
      '_id': 'm1',
      'conversationId': 'c1',
      'seq': 1,
      'senderId': 'current_sender',
      'senderProfileSubjectId': 'persona_sender',
      'senderName': '旧名字',
      'senderDisplayNameSnapshot': '记录分身名',
      'senderAvatar': 'https://example.com/old.jpg',
      'senderAvatarUrlSnapshot': 'https://example.com/snapshot.jpg',
      'type': 'text',
      'content': 'hello',
      'timestamp': '2026-01-01T00:00:00.000Z',
    });

    expect(dto.senderId, 'persona_sender');
    expect(dto.senderName, '记录分身名');
    expect(dto.senderAvatar, 'https://example.com/snapshot.jpg');
  });
}
