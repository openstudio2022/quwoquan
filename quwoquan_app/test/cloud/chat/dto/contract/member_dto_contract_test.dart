import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_member_dto.dart';

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 常规契约
  // ──────────────────────────────────────────────────────────────────
  group('ConversationMemberDto — 常规契约', () {
    test('fromMap 解析 user 类型成员全字段', () {
      final raw = <String, dynamic>{
        '_id': 'cm_001',
        'conversationId': 'conv_002',
        'userId': 'user_001',
        'displayName': '群主小王',
        'avatarUrl': 'https://i.pravatar.cc/150?u=wang',
        'memberType': 'user',
        'role': 'owner',
        'invitedBy': 'user_000',
        'joinedAt': '2026-02-01T10:00:00Z',
      };
      final dto = ConversationMemberDto.fromMap(raw);

      expect(dto.id, equals('cm_001'));
      expect(dto.conversationId, equals('conv_002'));
      expect(dto.userId, equals('user_001'));
      expect(dto.displayName, equals('群主小王'));
      expect(dto.avatarUrl, equals('https://i.pravatar.cc/150?u=wang'));
      expect(dto.memberType, equals('user'));
      expect(dto.role, equals('owner'));
      expect(dto.assistantSkillId, isNull);
      expect(dto.invitedBy, equals('user_000'));
      expect(dto.joinedAt.year, equals(2026));
    });

    test('fromMap 解析 assistant 类型成员含 assistantSkillId', () {
      final raw = <String, dynamic>{
        '_id': 'cm_ast',
        'conversationId': 'conv_002',
        'userId': 'assistant',
        'displayName': '小趣助手',
        'memberType': 'assistant',
        'role': 'member',
        'assistantSkillId': 'weather_skill',
        'joinedAt': '2026-03-01T10:00:00Z',
      };
      final dto = ConversationMemberDto.fromMap(raw);

      expect(dto.memberType, equals('assistant'));
      expect(dto.role, equals('member'));
      expect(dto.assistantSkillId, equals('weather_skill'));
    });

    test('toMap round-trip 保持字段完整', () {
      final raw = <String, dynamic>{
        '_id': 'cm_rt',
        'conversationId': 'conv_002',
        'userId': 'u1',
        'displayName': '测试用户',
        'avatarUrl': 'https://example.com/av.jpg',
        'memberType': 'user',
        'role': 'admin',
        'assistantSkillId': 'skill_1',
        'invitedBy': 'u0',
        'joinedAt': '2026-01-01T00:00:00.000Z',
      };
      final dto = ConversationMemberDto.fromMap(raw);
      final map = dto.toMap();

      expect(map['id'], equals('cm_rt'));
      expect(map['memberType'], equals('user'));
      expect(map['role'], equals('admin'));
      expect(map['assistantSkillId'], equals('skill_1'));
      expect(map['invitedBy'], equals('u0'));
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 兼容性契约
  // ──────────────────────────────────────────────────────────────────
  group('ConversationMemberDto — 兼容性契约', () {
    test('无 memberType 降级为 user', () {
      final raw = <String, dynamic>{
        '_id': 'cm_old',
        'conversationId': 'conv_001',
        'userId': 'u1',
        'role': 'member',
        'joinedAt': '2026-01-01T00:00:00Z',
      };
      final dto = ConversationMemberDto.fromMap(raw);
      expect(dto.memberType, equals('user'));
    });

    test('无 role 降级为 member', () {
      final raw = <String, dynamic>{
        '_id': 'cm_no_role',
        'conversationId': 'conv_001',
        'userId': 'u1',
        'memberType': 'user',
        'joinedAt': '2026-01-01T00:00:00Z',
      };
      final dto = ConversationMemberDto.fromMap(raw);
      expect(dto.role, equals('member'));
    });

    test('_id alias → id round-trip 稳定', () {
      final raw = <String, dynamic>{
        '_id': 'cm_alias_rt',
        'conversationId': 'conv_001',
        'userId': 'u1',
        'memberType': 'user',
        'role': 'member',
        'joinedAt': '2026-01-01T00:00:00.000Z',
      };
      final dto = ConversationMemberDto.fromMap(raw);
      final map = dto.toMap();
      final dto2 = ConversationMemberDto.fromMap(map);
      expect(dto2.id, equals(dto.id));
      expect(dto2.memberType, equals(dto.memberType));
      expect(dto2.role, equals(dto.role));
    });

    test('toMap 省略 null optional 字段', () {
      final raw = <String, dynamic>{
        '_id': 'cm_minimal',
        'conversationId': 'conv_001',
        'userId': 'u1',
        'memberType': 'user',
        'role': 'member',
        'joinedAt': '2026-01-01T00:00:00.000Z',
      };
      final dto = ConversationMemberDto.fromMap(raw);
      final map = dto.toMap();
      expect(map.containsKey('displayName'), isFalse);
      expect(map.containsKey('avatarUrl'), isFalse);
      expect(map.containsKey('assistantSkillId'), isFalse);
      expect(map.containsKey('invitedBy'), isFalse);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 异常/边界契约
  // ──────────────────────────────────────────────────────────────────
  group('ConversationMemberDto — 异常/边界契约', () {
    test('空 map 不崩溃', () {
      expect(() => ConversationMemberDto.fromMap(const {}), returnsNormally);
      final dto = ConversationMemberDto.fromMap(const {});
      expect(dto.id, isEmpty);
      expect(dto.conversationId, isEmpty);
      expect(dto.userId, isEmpty);
      expect(dto.memberType, equals('user'));
      expect(dto.role, equals('member'));
      expect(dto.displayName, isNull);
      expect(dto.avatarUrl, isNull);
      expect(dto.assistantSkillId, isNull);
      expect(dto.invitedBy, isNull);
    });

    test('null 值字段安全', () {
      final raw = <String, dynamic>{
        '_id': null,
        'conversationId': null,
        'userId': null,
        'displayName': null,
        'avatarUrl': null,
        'memberType': null,
        'role': null,
        'assistantSkillId': null,
        'invitedBy': null,
        'joinedAt': null,
      };
      expect(() => ConversationMemberDto.fromMap(raw), returnsNormally);
      final dto = ConversationMemberDto.fromMap(raw);
      expect(dto.id, isEmpty);
      expect(dto.memberType, equals('user'));
      expect(dto.role, equals('member'));
      expect(dto.displayName, isNull);
      expect(dto.assistantSkillId, isNull);
    });

    test('仅有 _id 字段时其余均为默认值', () {
      final raw = <String, dynamic>{'_id': 'cm_only_id'};
      final dto = ConversationMemberDto.fromMap(raw);
      expect(dto.id, equals('cm_only_id'));
      expect(dto.conversationId, isEmpty);
      expect(dto.userId, isEmpty);
      expect(dto.memberType, equals('user'));
      expect(dto.role, equals('member'));
    });
  });
}
