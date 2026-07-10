import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_dto.dart';

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 常规契约
  // ──────────────────────────────────────────────────────────────────
  group('ConversationDto — 常规契约', () {
    test('fromMap 解析全字段', () {
      final raw = <String, dynamic>{
        '_id': 'conv_001',
        'type': 'group',
        'title': '周末登山群',
        'avatarUrl': 'https://example.com/avatar.jpg',
        'creatorId': 'user_001',
        'circleId': 'circle_001',
        'maxSeq': 256,
        'memberCount': 15,
        'maxGroupSize': 1000,
        'receiptEnabled': true,
        'lastMessageId': 'msg_last',
        'lastMessagePreview': '周六早上8点出发',
        'lastMessageTime': '2026-03-07T09:15:00Z',
        'messageCount': 256,
        'status': 'active',
        'createdAt': '2026-02-01T10:00:00Z',
        'updatedAt': '2026-03-07T09:15:00Z',
      };
      final dto = ConversationDto.fromMap(raw);

      expect(dto.id, equals('conv_001'));
      expect(dto.type, equals('group'));
      expect(dto.title, equals('周末登山群'));
      expect(dto.avatarUrl, equals('https://example.com/avatar.jpg'));
      expect(dto.creatorId, equals('user_001'));
      expect(dto.circleId, equals('circle_001'));
      expect(dto.maxSeq, equals(256));
      expect(dto.memberCount, equals(15));
      expect(dto.maxGroupSize, equals(1000));
      expect(dto.receiptEnabled, isTrue);
      expect(dto.lastMessageId, equals('msg_last'));
      expect(dto.lastMessagePreview, equals('周六早上8点出发'));
      expect(dto.lastMessageTime, isNotNull);
      expect(dto.lastMessageTime!.year, equals(2026));
      expect(dto.messageCount, equals(256));
      expect(dto.status, equals('active'));
      expect(dto.createdAt.year, equals(2026));
      expect(dto.updatedAt.month, equals(3));
    });

    test('fromMap 使用 id 字段（非 _id）', () {
      final raw = <String, dynamic>{
        'id': 'conv_002',
        'type': 'direct',
        'creatorId': 'user_002',
        'maxSeq': 42,
        'memberCount': 2,
        'maxGroupSize': 2,
        'receiptEnabled': true,
        'messageCount': 42,
        'status': 'active',
        'createdAt': '2026-01-15T08:00:00Z',
        'updatedAt': '2026-03-07T10:30:00Z',
      };
      final dto = ConversationDto.fromMap(raw);
      expect(dto.id, equals('conv_002'));
    });

    test('toMap round-trip 保持字段完整', () {
      final raw = <String, dynamic>{
        '_id': 'conv_rt',
        'type': 'group',
        'title': '测试群',
        'avatarUrl': 'https://example.com/av.jpg',
        'creatorId': 'u1',
        'circleId': 'c1',
        'maxSeq': 10,
        'memberCount': 5,
        'maxGroupSize': 500,
        'receiptEnabled': false,
        'lastMessageId': 'msg_rt',
        'lastMessagePreview': '你好',
        'lastMessageTime': '2026-01-01T00:00:00.000Z',
        'messageCount': 10,
        'status': 'active',
        'createdAt': '2026-01-01T00:00:00.000Z',
        'updatedAt': '2026-01-01T00:00:00.000Z',
      };
      final dto = ConversationDto.fromMap(raw);
      final map = dto.toMap();

      expect(map['id'], equals('conv_rt'));
      expect(map['type'], equals('group'));
      expect(map['title'], equals('测试群'));
      expect(map['maxGroupSize'], equals(500));
      expect(map['receiptEnabled'], isFalse);
      expect(map['lastMessageId'], equals('msg_rt'));
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 兼容性契约
  // ──────────────────────────────────────────────────────────────────
  group('ConversationDto — 兼容性契约', () {
    test('_id alias → id 正确解析', () {
      final raw = <String, dynamic>{
        '_id': 'conv_alias',
        'type': 'direct',
        'creatorId': 'u1',
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': '2026-01-01T00:00:00Z',
      };
      final dto = ConversationDto.fromMap(raw);
      expect(dto.id, equals('conv_alias'));
    });

    test('缺少新字段 maxGroupSize 使用默认值 1000', () {
      final raw = <String, dynamic>{
        '_id': 'conv_old',
        'type': 'group',
        'creatorId': 'u1',
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': '2026-01-01T00:00:00Z',
      };
      final dto = ConversationDto.fromMap(raw);
      expect(dto.maxGroupSize, equals(1000));
    });

    test('缺少 receiptEnabled 默认为 true', () {
      final raw = <String, dynamic>{
        '_id': 'conv_no_receipt',
        'type': 'direct',
        'creatorId': 'u1',
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': '2026-01-01T00:00:00Z',
      };
      final dto = ConversationDto.fromMap(raw);
      expect(dto.receiptEnabled, isTrue);
    });

    test('缺少 type 默认为 direct', () {
      final raw = <String, dynamic>{
        '_id': 'conv_no_type',
        'creatorId': 'u1',
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': '2026-01-01T00:00:00Z',
      };
      final dto = ConversationDto.fromMap(raw);
      expect(dto.type, equals('direct'));
    });

    test('toMap round-trip 保持 maxSeq 和 memberCount', () {
      final raw = <String, dynamic>{
        '_id': 'conv_compat_rt',
        'type': 'group',
        'creatorId': 'u1',
        'maxSeq': 42,
        'memberCount': 10,
        'maxGroupSize': 500,
        'receiptEnabled': true,
        'messageCount': 42,
        'status': 'active',
        'createdAt': '2026-01-01T00:00:00.000Z',
        'updatedAt': '2026-01-01T00:00:00.000Z',
      };
      final dto = ConversationDto.fromMap(raw);
      final map = dto.toMap();
      final dto2 = ConversationDto.fromMap(map);
      expect(dto2.maxSeq, equals(dto.maxSeq));
      expect(dto2.memberCount, equals(dto.memberCount));
      expect(dto2.maxGroupSize, equals(dto.maxGroupSize));
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 异常/边界契约
  // ──────────────────────────────────────────────────────────────────
  group('ConversationDto — 异常/边界契约', () {
    test('空 map 不崩溃', () {
      expect(() => ConversationDto.fromMap(const {}), returnsNormally);
      final dto = ConversationDto.fromMap(const {});
      expect(dto.id, isEmpty);
      expect(dto.type, equals('direct'));
      expect(dto.creatorId, isEmpty);
      expect(dto.maxSeq, equals(0));
      expect(dto.memberCount, equals(0));
      expect(dto.messageCount, equals(0));
      expect(dto.status, equals('active'));
    });

    test('null 值字段安全', () {
      final raw = <String, dynamic>{
        '_id': null,
        'type': null,
        'title': null,
        'avatarUrl': null,
        'creatorId': null,
        'circleId': null,
        'maxSeq': null,
        'memberCount': null,
        'maxGroupSize': null,
        'receiptEnabled': null,
        'lastMessageId': null,
        'lastMessagePreview': null,
        'lastMessageTime': null,
        'messageCount': null,
        'status': null,
        'createdAt': null,
        'updatedAt': null,
      };
      expect(() => ConversationDto.fromMap(raw), returnsNormally);
      final dto = ConversationDto.fromMap(raw);
      expect(dto.id, isEmpty);
      expect(dto.maxSeq, equals(0));
      expect(dto.memberCount, equals(0));
      expect(dto.maxGroupSize, equals(1000));
      expect(dto.receiptEnabled, isTrue);
      expect(dto.title, isNull);
      expect(dto.lastMessageTime, isNull);
    });

    test('optional 字段缺失不影响 required 字段', () {
      final raw = <String, dynamic>{
        '_id': 'conv_minimal',
        'type': 'direct',
        'creatorId': 'u1',
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': '2026-01-01T00:00:00Z',
      };
      final dto = ConversationDto.fromMap(raw);
      expect(dto.id, equals('conv_minimal'));
      expect(dto.title, isNull);
      expect(dto.avatarUrl, isNull);
      expect(dto.circleId, isNull);
      expect(dto.lastMessageId, isNull);
      expect(dto.lastMessagePreview, isNull);
      expect(dto.lastMessageTime, isNull);
    });
  });
}
