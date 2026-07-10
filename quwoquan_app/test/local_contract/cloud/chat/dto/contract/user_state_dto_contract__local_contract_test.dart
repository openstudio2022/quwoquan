import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_user_state_dto.dart';

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 常规契约
  // ──────────────────────────────────────────────────────────────────
  group('ConversationUserStateDto — 常规契约', () {
    test('fromMap 解析全字段', () {
      final raw = <String, dynamic>{
        '_id': 'cus_001',
        'userId': 'user_001',
        'conversationId': 'conv_001',
        'readSeq': 40,
        'unreadCount': 2,
        'muted': true,
        'pinned': false,
        'lastReadAt': '2026-03-07T10:28:00Z',
        'updatedAt': '2026-03-07T10:30:00Z',
      };
      final dto = ConversationUserStateDto.fromMap(raw);

      expect(dto.id, equals('cus_001'));
      expect(dto.userId, equals('user_001'));
      expect(dto.conversationId, equals('conv_001'));
      expect(dto.readSeq, equals(40));
      expect(dto.unreadCount, equals(2));
      expect(dto.muted, isTrue);
      expect(dto.pinned, isFalse);
      expect(dto.lastReadAt, isNotNull);
      expect(dto.lastReadAt!.year, equals(2026));
      expect(dto.updatedAt.year, equals(2026));
    });

    test('fromMap 使用 id 字段（非 _id）', () {
      final raw = <String, dynamic>{
        'id': 'cus_alt',
        'userId': 'u1',
        'conversationId': 'conv_001',
        'readSeq': 5,
        'unreadCount': 0,
        'muted': false,
        'pinned': true,
        'updatedAt': '2026-01-01T00:00:00Z',
      };
      final dto = ConversationUserStateDto.fromMap(raw);
      expect(dto.id, equals('cus_alt'));
      expect(dto.pinned, isTrue);
    });

    test('toMap round-trip 保持字段完整', () {
      final raw = <String, dynamic>{
        '_id': 'cus_rt',
        'userId': 'u1',
        'conversationId': 'conv_001',
        'readSeq': 20,
        'unreadCount': 3,
        'muted': false,
        'pinned': true,
        'lastReadAt': '2026-01-01T00:00:00.000Z',
        'updatedAt': '2026-01-01T00:00:00.000Z',
      };
      final dto = ConversationUserStateDto.fromMap(raw);
      final map = dto.toMap();

      expect(map['id'], equals('cus_rt'));
      expect(map['readSeq'], equals(20));
      expect(map['unreadCount'], equals(3));
      expect(map['muted'], isFalse);
      expect(map['pinned'], isTrue);
      expect(map['lastReadAt'], isNotNull);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 兼容性契约
  // ──────────────────────────────────────────────────────────────────
  group('ConversationUserStateDto — 兼容性契约', () {
    test('缺少 readSeq 降级为 0', () {
      final raw = <String, dynamic>{
        '_id': 'cus_old',
        'userId': 'u1',
        'conversationId': 'conv_001',
        'unreadCount': 5,
        'muted': false,
        'pinned': false,
        'updatedAt': '2026-01-01T00:00:00Z',
      };
      final dto = ConversationUserStateDto.fromMap(raw);
      expect(dto.readSeq, equals(0));
    });

    test('缺少 unreadCount 降级为 0', () {
      final raw = <String, dynamic>{
        '_id': 'cus_no_unread',
        'userId': 'u1',
        'conversationId': 'conv_001',
        'readSeq': 10,
        'muted': false,
        'pinned': false,
        'updatedAt': '2026-01-01T00:00:00Z',
      };
      final dto = ConversationUserStateDto.fromMap(raw);
      expect(dto.unreadCount, equals(0));
    });

    test('缺少 muted/pinned 默认为 false', () {
      final raw = <String, dynamic>{
        '_id': 'cus_no_flags',
        'userId': 'u1',
        'conversationId': 'conv_001',
        'updatedAt': '2026-01-01T00:00:00Z',
      };
      final dto = ConversationUserStateDto.fromMap(raw);
      expect(dto.muted, isFalse);
      expect(dto.pinned, isFalse);
    });

    test('_id alias → id round-trip 稳定', () {
      final raw = <String, dynamic>{
        '_id': 'cus_alias_rt',
        'userId': 'u1',
        'conversationId': 'conv_001',
        'readSeq': 10,
        'unreadCount': 0,
        'muted': true,
        'pinned': false,
        'updatedAt': '2026-01-01T00:00:00.000Z',
      };
      final dto = ConversationUserStateDto.fromMap(raw);
      final map = dto.toMap();
      final dto2 = ConversationUserStateDto.fromMap(map);
      expect(dto2.id, equals(dto.id));
      expect(dto2.readSeq, equals(dto.readSeq));
      expect(dto2.muted, equals(dto.muted));
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 异常/边界契约
  // ──────────────────────────────────────────────────────────────────
  group('ConversationUserStateDto — 异常/边界契约', () {
    test('空 map 不崩溃', () {
      expect(
        () => ConversationUserStateDto.fromMap(const {}),
        returnsNormally,
      );
      final dto = ConversationUserStateDto.fromMap(const {});
      expect(dto.id, isEmpty);
      expect(dto.userId, isEmpty);
      expect(dto.conversationId, isEmpty);
      expect(dto.readSeq, equals(0));
      expect(dto.unreadCount, equals(0));
      expect(dto.muted, isFalse);
      expect(dto.pinned, isFalse);
      expect(dto.lastReadAt, isNull);
    });

    test('null 值字段安全', () {
      final raw = <String, dynamic>{
        '_id': null,
        'userId': null,
        'conversationId': null,
        'readSeq': null,
        'unreadCount': null,
        'muted': null,
        'pinned': null,
        'lastReadAt': null,
        'updatedAt': null,
      };
      expect(() => ConversationUserStateDto.fromMap(raw), returnsNormally);
      final dto = ConversationUserStateDto.fromMap(raw);
      expect(dto.id, isEmpty);
      expect(dto.readSeq, equals(0));
      expect(dto.unreadCount, equals(0));
      expect(dto.muted, isFalse);
      expect(dto.pinned, isFalse);
      expect(dto.lastReadAt, isNull);
    });

    test('toMap 省略 null lastReadAt', () {
      final raw = <String, dynamic>{
        '_id': 'cus_no_last_read',
        'userId': 'u1',
        'conversationId': 'conv_001',
        'readSeq': 0,
        'unreadCount': 0,
        'muted': false,
        'pinned': false,
        'updatedAt': '2026-01-01T00:00:00.000Z',
      };
      final dto = ConversationUserStateDto.fromMap(raw);
      final map = dto.toMap();
      expect(map.containsKey('lastReadAt'), isFalse);
    });
  });
}
