import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/send_message_request.dart';

void main() {
  group('SendMessageRequest — 常规契约', () {
    test('audio 类型 toMap 包含 media 字段', () {
      const req = SendMessageRequest(
        type: 'audio',
        content: '',
        mediaUrl: 'https://cdn.example.com/voice.m4a',
        media: {
          'url': 'https://cdn.example.com/voice.m4a',
          'mimeType': 'audio/mp4',
          'durationMs': 5200,
          'waveform': [0.1, 0.3, 0.7],
          'codec': 'aac',
        },
        clientMsgId: 'test-uuid-1',
      );

      final map = req.toMap();
      expect(map['type'], 'audio');
      expect(map['media'], isNotNull);
      expect(map['media']['durationMs'], 5200);
      expect(map['mediaUrl'], 'https://cdn.example.com/voice.m4a');
      expect(map['clientMsgId'], 'test-uuid-1');
    });

    test('text 类型 toMap 不包含 media 和 mediaUrl', () {
      const req = SendMessageRequest(
        type: 'text',
        content: 'hello world',
        clientMsgId: 'test-uuid-2',
      );

      final map = req.toMap();
      expect(map.containsKey('media'), isFalse);
      expect(map.containsKey('mediaUrl'), isFalse);
    });
  });

  group('SendMessageRequest — 兼容性契约', () {
    test('仅 mediaUrl 无 media 字段（向后兼容）', () {
      const req = SendMessageRequest(
        type: 'audio',
        content: '',
        mediaUrl: 'https://cdn.example.com/old.m4a',
        clientMsgId: 'compat-1',
      );

      final map = req.toMap();
      expect(map['mediaUrl'], isNotNull);
      expect(map.containsKey('media'), isFalse);
    });
  });

  group('SendMessageRequest — 异常/边界契约', () {
    test('空 media Map 被序列化', () {
      const req = SendMessageRequest(
        type: 'audio',
        content: '',
        media: {},
        clientMsgId: 'edge-1',
      );

      final map = req.toMap();
      expect(map['media'], isA<Map>());
      expect((map['media'] as Map).isEmpty, isTrue);
    });
  });
}
