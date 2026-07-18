import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_dto.dart';

void main() {
  group('ConversationDto — 常规契约', () {
    test('fromMap 解析全字段', () {
      final dto = ConversationDto.fromMap(
        _conversationWire(<String, dynamic>{
          'id': 'conv_001',
          'title': '周末登山群',
          'avatarUrl': 'https://example.com/avatar.jpg',
          'circleId': 'circle_001',
          'maxSeq': 256,
          'memberCount': 15,
          'lastMessageId': 'msg_last',
          'lastMessagePreview': '周六早上8点出发',
          'lastMessageTime': '2026-03-07T09:15:00Z',
          'messageCount': 256,
          'updatedAt': '2026-03-07T09:15:00Z',
        }),
      );

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
      expect(dto.lastMessageTime, DateTime.parse('2026-03-07T09:15:00Z'));
      expect(dto.messageCount, equals(256));
      expect(dto.status, equals('active'));
    });

    test('toMap round-trip 保持公开字段且不泄漏存储键', () {
      final dto = ConversationDto.fromMap(
        _conversationWire(<String, dynamic>{
          'id': 'conv_round_trip',
          'receiptEnabled': false,
        }),
      );
      final map = dto.toMap();
      final decoded = ConversationDto.fromMap(map);

      expect(decoded.id, equals(dto.id));
      expect(decoded.maxSeq, equals(dto.maxSeq));
      expect(decoded.memberCount, equals(dto.memberCount));
      expect(decoded.receiptEnabled, isFalse);
      expect(map.containsKey('_id'), isFalse);
      expect(map.containsKey('conversationId'), isFalse);
    });
  });

  group('ConversationDto — 单轨契约', () {
    test('拒绝 _id 与 conversationId alias，只认 id', () {
      final storageAlias = _conversationWire(<String, dynamic>{
        '_id': 'conv_storage_alias',
      })..remove('id');
      final projectionAlias = _conversationWire(<String, dynamic>{
        'conversationId': 'conv_projection_alias',
      })..remove('id');

      expect(
        () => ConversationDto.fromMap(storageAlias),
        throwsFormatException,
      );
      expect(
        () => ConversationDto.fromMap(projectionAlias),
        throwsFormatException,
      );
    });

    test('metadata 默认字段缺失时只应用已声明默认值', () {
      final wire = _conversationWire()
        ..remove('maxSeq')
        ..remove('memberCount')
        ..remove('messageCount')
        ..remove('originType')
        ..remove('bindingType')
        ..remove('lifecyclePolicy');
      final dto = ConversationDto.fromMap(wire);

      expect(dto.maxSeq, isZero);
      expect(dto.memberCount, isZero);
      expect(dto.messageCount, isZero);
      expect(dto.originType, equals('direct_init'));
      expect(dto.bindingType, equals('none'));
      expect(dto.lifecyclePolicy, equals('persistent'));
    });
  });

  group('ConversationDto — 异常/边界契约', () {
    test('缺失必填字段立即失败', () {
      for (final field in <String>{
        'id',
        'type',
        'creatorId',
        'maxGroupSize',
        'receiptEnabled',
        'status',
        'createdAt',
        'updatedAt',
      }) {
        final wire = _conversationWire()..remove(field);
        expect(
          () => ConversationDto.fromMap(wire),
          throwsFormatException,
          reason: field,
        );
      }
    });

    test('无效必填时间与可选时间立即失败', () {
      expect(
        () => ConversationDto.fromMap(
          _conversationWire(<String, dynamic>{'createdAt': 'not-a-time'}),
        ),
        throwsFormatException,
      );
      expect(
        () => ConversationDto.fromMap(
          _conversationWire(<String, dynamic>{'lastMessageTime': 'not-a-time'}),
        ),
        throwsFormatException,
      );
    });

    test('可选字段缺失不影响完整必填契约', () {
      final dto = ConversationDto.fromMap(_conversationWire());

      expect(dto.title, isNull);
      expect(dto.avatarUrl, isNull);
      expect(dto.circleId, isNull);
      expect(dto.lastMessageId, isNull);
      expect(dto.lastMessagePreview, isNull);
      expect(dto.lastMessageTime, isNull);
    });
  });
}

Map<String, dynamic> _conversationWire([
  Map<String, dynamic> overrides = const <String, dynamic>{},
]) {
  return <String, dynamic>{
    'id': 'conv_default',
    'type': 'group',
    'creatorId': 'user_001',
    'originType': 'direct_init',
    'bindingType': 'none',
    'lifecyclePolicy': 'persistent',
    'maxSeq': 0,
    'memberCount': 0,
    'maxGroupSize': 1000,
    'receiptEnabled': true,
    'messageCount': 0,
    'status': 'active',
    'createdAt': '2026-02-01T10:00:00Z',
    'updatedAt': '2026-02-01T10:00:00Z',
    ...overrides,
  };
}
