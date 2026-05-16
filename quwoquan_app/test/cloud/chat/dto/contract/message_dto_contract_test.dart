import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 常规契约
  // ──────────────────────────────────────────────────────────────────
  group('MessageDto — 常规契约', () {
    test('fromMap 解析全字段', () {
      final raw = <String, dynamic>{
        '_id': 'msg_001',
        'conversationId': 'conv_001',
        'seq': 42,
        'clientMsgId': 'client-uuid-001',
        'senderId': 'user_001',
        'senderSubAccountId': 'persona_a',
        'type': 'text',
        'content': '你好世界',
        'mediaUrl': 'https://example.com/media.jpg',
        'cardPayload': {'title': '卡片', 'body': '内容'},
        'replyToMessageId': 'msg_000',
        'mentions': ['user_002', 'user_003'],
        'status': 'read',
        'recalledAt': '2026-03-07T10:00:00Z',
        'metadata': {'source': 'mobile'},
        'timestamp': '2026-03-07T10:30:00Z',
      };
      final dto = MessageDto.fromMap(raw);

      expect(dto.id, equals('msg_001'));
      expect(dto.conversationId, equals('conv_001'));
      expect(dto.seq, equals(42));
      expect(dto.clientMsgId, equals('client-uuid-001'));
      expect(dto.senderId, equals('persona_a'));
      expect(dto.senderSubAccountId, equals('persona_a'));
      expect(dto.type, equals('text'));
      expect(dto.content, equals('你好世界'));
      expect(dto.mediaUrl, equals('https://example.com/media.jpg'));
      expect(dto.cardPayload, isNotNull);
      expect(dto.cardPayload!['title'], equals('卡片'));
      expect(dto.replyToMessageId, equals('msg_000'));
      expect(dto.mentions, isNotNull);
      expect(dto.mentions!.length, equals(2));
      expect(dto.status, equals('read'));
      expect(dto.recalledAt, isNotNull);
      expect(dto.recalledAt!.year, equals(2026));
      expect(dto.metadata, isNotNull);
      expect(dto.metadata!['source'], equals('mobile'));
      expect(dto.timestamp!.year, equals(2026));
    });

    test('fromMap 使用 id 字段（非 _id）', () {
      final raw = <String, dynamic>{
        'id': 'msg_alt',
        'conversationId': 'conv_001',
        'seq': 1,
        'clientMsgId': 'cid',
        'senderId': 'u1',
        'type': 'text',
        'status': 'sent',
        'timestamp': '2026-01-01T00:00:00Z',
      };
      final dto = MessageDto.fromMap(raw);
      expect(dto.id, equals('msg_alt'));
    });

    test('toMap round-trip 保持字段完整', () {
      final raw = <String, dynamic>{
        '_id': 'msg_rt',
        'conversationId': 'conv_001',
        'seq': 10,
        'clientMsgId': 'cid_rt',
        'senderId': 'u1',
        'senderSubAccountId': 'p1',
        'type': 'image',
        'content': '图片',
        'mediaUrl': 'https://example.com/img.jpg',
        'replyToMessageId': 'msg_prev',
        'mentions': ['u2'],
        'status': 'sent',
        'metadata': {'key': 'value'},
        'timestamp': '2026-01-01T00:00:00.000Z',
      };
      final dto = MessageDto.fromMap(raw);
      final map = dto.toMap();

      expect(map['id'], equals('msg_rt'));
      expect(map['seq'], equals(10));
      expect(map['senderSubAccountId'], equals('p1'));
      expect(map['mediaUrl'], equals('https://example.com/img.jpg'));
      expect(map['mentions'], equals(['u2']));
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 兼容性契约
  // ──────────────────────────────────────────────────────────────────
  group('MessageDto — 兼容性契约', () {
    test('无 seq 的旧消息降级为 seq=0', () {
      final raw = <String, dynamic>{
        '_id': 'msg_old',
        'conversationId': 'conv_001',
        'clientMsgId': 'cid_old',
        'senderId': 'u1',
        'type': 'text',
        'content': '旧消息',
        'status': 'sent',
        'timestamp': '2026-01-01T00:00:00Z',
      };
      final dto = MessageDto.fromMap(raw);
      expect(dto.seq, equals(0));
    });

    test('缺少 type 默认为 text', () {
      final raw = <String, dynamic>{
        '_id': 'msg_no_type',
        'conversationId': 'conv_001',
        'clientMsgId': 'cid',
        'senderId': 'u1',
        'status': 'sent',
        'timestamp': '2026-01-01T00:00:00Z',
      };
      final dto = MessageDto.fromMap(raw);
      expect(dto.type, equals('text'));
    });

    test('缺少 status 默认为 sent', () {
      final raw = <String, dynamic>{
        '_id': 'msg_no_status',
        'conversationId': 'conv_001',
        'clientMsgId': 'cid',
        'senderId': 'u1',
        'type': 'text',
        'timestamp': '2026-01-01T00:00:00Z',
      };
      final dto = MessageDto.fromMap(raw);
      expect(dto.status, equals('sent'));
    });

    test('_id alias → id round-trip 稳定', () {
      final raw = <String, dynamic>{
        '_id': 'msg_alias_rt',
        'conversationId': 'conv_001',
        'seq': 5,
        'clientMsgId': 'cid',
        'senderId': 'u1',
        'type': 'text',
        'status': 'sent',
        'timestamp': '2026-01-01T00:00:00.000Z',
      };
      final dto = MessageDto.fromMap(raw);
      final map = dto.toMap();
      final dto2 = MessageDto.fromMap(map);
      expect(dto2.id, equals(dto.id));
      expect(dto2.seq, equals(dto.seq));
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 异常/边界契约
  // ──────────────────────────────────────────────────────────────────
  group('MessageDto — 异常/边界契约', () {
    test('空 map 不崩溃', () {
      expect(() => MessageDto.fromMap(const {}), returnsNormally);
      final dto = MessageDto.fromMap(const {});
      expect(dto.id, isEmpty);
      expect(dto.conversationId, isEmpty);
      expect(dto.seq, equals(0));
      expect(dto.clientMsgId, isEmpty);
      expect(dto.senderId, isEmpty);
      expect(dto.type, equals('text'));
      expect(dto.content, isNull);
      expect(dto.status, equals('sent'));
    });

    test('null 值字段安全', () {
      final raw = <String, dynamic>{
        '_id': null,
        'conversationId': null,
        'seq': null,
        'clientMsgId': null,
        'senderId': null,
        'senderSubAccountId': null,
        'type': null,
        'content': null,
        'mediaUrl': null,
        'cardPayload': null,
        'replyToMessageId': null,
        'mentions': null,
        'status': null,
        'recalledAt': null,
        'metadata': null,
        'timestamp': null,
      };
      expect(() => MessageDto.fromMap(raw), returnsNormally);
      final dto = MessageDto.fromMap(raw);
      expect(dto.id, isEmpty);
      expect(dto.seq, equals(0));
      expect(dto.senderSubAccountId, isNull);
      expect(dto.content, isNull);
      expect(dto.mediaUrl, isNull);
      expect(dto.cardPayload, isNull);
      expect(dto.mentions, isNull);
      expect(dto.recalledAt, isNull);
      expect(dto.metadata, isNull);
    });

    test('cardPayload 为非 Map 类型时返回 null', () {
      final raw = <String, dynamic>{
        '_id': 'msg_bad_card',
        'conversationId': 'conv_001',
        'clientMsgId': 'cid',
        'senderId': 'u1',
        'type': 'card',
        'cardPayload': 'not_a_map',
        'status': 'sent',
        'timestamp': '2026-01-01T00:00:00Z',
      };
      final dto = MessageDto.fromMap(raw);
      expect(dto.cardPayload, isNull);
    });

    test('mentions 为非 List 类型时返回 null', () {
      final raw = <String, dynamic>{
        '_id': 'msg_bad_mentions',
        'conversationId': 'conv_001',
        'clientMsgId': 'cid',
        'senderId': 'u1',
        'type': 'text',
        'mentions': 'not_a_list',
        'status': 'sent',
        'timestamp': '2026-01-01T00:00:00Z',
      };
      final dto = MessageDto.fromMap(raw);
      expect(dto.mentions, isNull);
    });
  });
}
