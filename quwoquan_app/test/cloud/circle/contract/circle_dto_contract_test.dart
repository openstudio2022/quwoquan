import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';

void main() {
  group('CircleDto — 常规契约', () {
    test('fromMap / toMap round-trip 保留全字段', () {
      final original = CircleDto(
        id: 'c1',
        name: 'Test Circle',
        description: 'A test circle',
        coverUrl: 'https://example.com/cover.jpg',
        ownerId: 'u1',
        category: 'tech',
        tags: ['flutter', 'dart'],
        memberCount: 42,
        postCount: 100,
        weeklyActiveCount: 15,
        status: 'active',
        visibility: 'public',
        joinPolicy: 'open',
        conversationId: 'conv_1',
        autoSyncChat: true,
        sectionConfig: [
          CircleSectionConfigDto(
              sectionType: 'works', visible: true, order: 0),
          CircleSectionConfigDto(
              sectionType: 'chat', visible: true, order: 1),
        ],
        storageUsedBytes: 1024,
        storageQuotaBytes: 1073741824,
        domainId: 'tech',
        createdAt: DateTime.utc(2025, 1, 1),
        updatedAt: DateTime.utc(2025, 6, 1),
      );
      final map = original.toMap();
      final restored = CircleDto.fromMap(map);
      expect(restored.id, original.id);
      expect(restored.name, original.name);
      expect(restored.description, original.description);
      expect(restored.coverUrl, original.coverUrl);
      expect(restored.ownerId, original.ownerId);
      expect(restored.category, original.category);
      expect(restored.tags, original.tags);
      expect(restored.memberCount, original.memberCount);
      expect(restored.postCount, original.postCount);
      expect(restored.weeklyActiveCount, original.weeklyActiveCount);
      expect(restored.status, original.status);
      expect(restored.visibility, original.visibility);
      expect(restored.joinPolicy, original.joinPolicy);
      expect(restored.conversationId, original.conversationId);
      expect(restored.autoSyncChat, original.autoSyncChat);
      expect(restored.sectionConfig.length, original.sectionConfig.length);
      expect(restored.sectionConfig[0].sectionType, 'works');
      expect(restored.sectionConfig[1].sectionType, 'chat');
      expect(restored.storageUsedBytes, original.storageUsedBytes);
      expect(restored.storageQuotaBytes, original.storageQuotaBytes);
      expect(restored.domainId, original.domainId);
      expect(restored.createdAt, original.createdAt);
      expect(restored.updatedAt, original.updatedAt);
    });

    test('fromMap 支持 _id alias 作为 id', () {
      final dto = CircleDto.fromMap({
        '_id': 'mongo_id',
        'name': 'Test',
        'ownerId': 'u1',
        'createdAt': '2025-01-01T00:00:00.000Z',
        'updatedAt': '2025-01-01T00:00:00.000Z',
      });
      expect(dto.id, 'mongo_id');
    });

    test('fromMap 支持 cover alias 作为 coverUrl', () {
      final dto = CircleDto.fromMap({
        'id': 'c1',
        'name': 'Test',
        'ownerId': 'u1',
        'cover': 'https://example.com/img.jpg',
        'createdAt': '2025-01-01T00:00:00.000Z',
        'updatedAt': '2025-01-01T00:00:00.000Z',
      });
      expect(dto.coverUrl, 'https://example.com/img.jpg');
    });

    test('copyWith 正确修改部分字段', () {
      final original = CircleDto(
        id: 'c1',
        name: 'Old Name',
        ownerId: 'u1',
        createdAt: DateTime.utc(2025),
        updatedAt: DateTime.utc(2025),
      );
      final updated = original.copyWith(name: 'New Name', memberCount: 10);
      expect(updated.name, 'New Name');
      expect(updated.memberCount, 10);
      expect(updated.id, 'c1');
      expect(updated.ownerId, 'u1');
    });
  });

  group('CircleDto — 兼容性契约', () {
    test('toMap round-trip 稳定（nullable 字段缺失不输出）', () {
      final dto = CircleDto(
        id: 'c1',
        name: 'Test',
        ownerId: 'u1',
        createdAt: DateTime.utc(2025),
        updatedAt: DateTime.utc(2025),
      );
      final map = dto.toMap();
      expect(map.containsKey('description'), isFalse);
      expect(map.containsKey('coverUrl'), isFalse);
      expect(map.containsKey('category'), isFalse);
      expect(map.containsKey('conversationId'), isFalse);
      expect(map.containsKey('domainId'), isFalse);
    });

    test('DateTime 字段序列化为 ISO-8601 字符串', () {
      final dt = DateTime.utc(2025, 3, 15, 12, 30, 0);
      final dto = CircleDto(
        id: 'c1',
        name: 'Test',
        ownerId: 'u1',
        createdAt: dt,
        updatedAt: dt,
      );
      final map = dto.toMap();
      expect(map['createdAt'], dt.toIso8601String());
      expect(map['updatedAt'], dt.toIso8601String());
    });

    test('sectionConfig 序列化为 List<Map>', () {
      final dto = CircleDto(
        id: 'c1',
        name: 'Test',
        ownerId: 'u1',
        sectionConfig: [
          CircleSectionConfigDto(
              sectionType: 'works', visible: true, order: 0),
        ],
        createdAt: DateTime.utc(2025),
        updatedAt: DateTime.utc(2025),
      );
      final map = dto.toMap();
      final sections = map['sectionConfig'] as List;
      expect(sections.length, 1);
      expect((sections[0] as Map)['sectionType'], 'works');
    });
  });

  group('CircleDto — 异常/边界契约', () {
    test('fromMap 缺失可选字段降级为默认值', () {
      final minimal = CircleDto.fromMap({
        'id': 'c2',
        'name': 'Minimal',
        'ownerId': 'u2',
        'createdAt': '2025-01-01T00:00:00.000Z',
        'updatedAt': '2025-01-01T00:00:00.000Z',
      });
      expect(minimal.description, isNull);
      expect(minimal.coverUrl, isNull);
      expect(minimal.category, isNull);
      expect(minimal.tags, isEmpty);
      expect(minimal.sectionConfig, isEmpty);
      expect(minimal.memberCount, 0);
      expect(minimal.postCount, 0);
      expect(minimal.weeklyActiveCount, 0);
      expect(minimal.status, 'active');
      expect(minimal.visibility, 'public');
      expect(minimal.joinPolicy, 'open');
      expect(minimal.autoSyncChat, true);
      expect(minimal.storageUsedBytes, 0);
      expect(minimal.storageQuotaBytes, 1073741824);
      expect(minimal.domainId, isNull);
      expect(minimal.conversationId, isNull);
    });

    test('fromMap 全字段缺失不崩溃', () {
      expect(
        () => CircleDto.fromMap(const <String, dynamic>{}),
        returnsNormally,
      );
    });

    test('fromMap sectionConfig 为 null 时降级为空列表', () {
      final dto = CircleDto.fromMap({
        'id': 'c1',
        'name': 'Test',
        'ownerId': 'u1',
        'sectionConfig': null,
        'createdAt': '2025-01-01T00:00:00.000Z',
        'updatedAt': '2025-01-01T00:00:00.000Z',
      });
      expect(dto.sectionConfig, isEmpty);
    });

    test('fromMap 无效日期字符串降级为 DateTime.now()', () {
      final dto = CircleDto.fromMap({
        'id': 'c1',
        'name': 'Test',
        'ownerId': 'u1',
        'createdAt': 'invalid-date',
        'updatedAt': 'invalid-date',
      });
      expect(dto.createdAt, isA<DateTime>());
      expect(dto.updatedAt, isA<DateTime>());
    });

    test('fromMap num 类型字段可正确解析 double 值', () {
      final dto = CircleDto.fromMap({
        'id': 'c1',
        'name': 'Test',
        'ownerId': 'u1',
        'memberCount': 42.0,
        'postCount': 100.5,
        'storageUsedBytes': 2048.0,
        'createdAt': '2025-01-01T00:00:00.000Z',
        'updatedAt': '2025-01-01T00:00:00.000Z',
      });
      expect(dto.memberCount, 42);
      expect(dto.postCount, 100);
      expect(dto.storageUsedBytes, 2048);
    });
  });

  group('CircleMemberDto — 常规契约', () {
    test('fromMap / toMap round-trip 保留全字段', () {
      final map = {
        'id': 'm1',
        'circleId': 'c1',
        'userId': 'u1',
        'role': 'admin',
        'joinedAt': '2025-03-01T00:00:00.000Z',
        'lastActiveAt': '2025-03-07T10:00:00.000Z',
        'contribution': 150,
      };
      final member = CircleMemberDto.fromMap(map);
      expect(member.id, 'm1');
      expect(member.circleId, 'c1');
      expect(member.userId, 'u1');
      expect(member.role, 'admin');
      expect(member.contribution, 150);
      expect(member.lastActiveAt, isNotNull);

      final restored = CircleMemberDto.fromMap(member.toMap());
      expect(restored.userId, member.userId);
      expect(restored.role, member.role);
      expect(restored.contribution, member.contribution);
    });

    test('fromMap 支持 _id alias', () {
      final member = CircleMemberDto.fromMap({
        '_id': 'mongo_member_id',
        'circleId': 'c1',
        'userId': 'u1',
        'role': 'member',
        'joinedAt': '2025-01-01T00:00:00.000Z',
      });
      expect(member.id, 'mongo_member_id');
    });
  });

  group('CircleMemberDto — 兼容性契约', () {
    test('toMap 中 lastActiveAt 为空时不输出', () {
      final member = CircleMemberDto(
        id: 'm1',
        circleId: 'c1',
        userId: 'u1',
        role: 'member',
        joinedAt: DateTime.utc(2025),
      );
      final map = member.toMap();
      expect(map.containsKey('lastActiveAt'), isFalse);
    });
  });

  group('CircleMemberDto — 异常/边界契约', () {
    test('fromMap 缺失字段降级为默认值', () {
      final member = CircleMemberDto.fromMap(const <String, dynamic>{});
      expect(member.id, '');
      expect(member.circleId, '');
      expect(member.userId, '');
      expect(member.role, 'member');
      expect(member.contribution, 0);
      expect(member.lastActiveAt, isNull);
    });
  });

  group('CircleFileDto — 常规契约', () {
    test('fromMap / toMap round-trip 保留全字段', () {
      final map = {
        'id': 'f1',
        'circleId': 'c1',
        'parentFolderId': 'folder_1',
        'name': 'test.pdf',
        'fileType': 'file',
        'mimeType': 'application/pdf',
        'sizeBytes': 2048,
        'uploaderId': 'u1',
        'status': 'active',
        'createdAt': '2025-03-01T00:00:00.000Z',
        'updatedAt': '2025-03-01T00:00:00.000Z',
      };
      final file = CircleFileDto.fromMap(map);
      expect(file.id, 'f1');
      expect(file.name, 'test.pdf');
      expect(file.fileType, 'file');
      expect(file.mimeType, 'application/pdf');
      expect(file.sizeBytes, 2048);
      expect(file.parentFolderId, 'folder_1');
      expect(file.isFolder, isFalse);

      final restored = CircleFileDto.fromMap(file.toMap());
      expect(restored.id, file.id);
      expect(restored.name, file.name);
      expect(restored.sizeBytes, file.sizeBytes);
    });

    test('isFolder computed getter 正确', () {
      final folder = CircleFileDto.fromMap({
        'id': 'f2',
        'circleId': 'c1',
        'name': 'Documents',
        'fileType': 'folder',
        'uploaderId': 'u1',
        'createdAt': '2025-01-01T00:00:00.000Z',
        'updatedAt': '2025-01-01T00:00:00.000Z',
      });
      expect(folder.isFolder, isTrue);

      final file = CircleFileDto.fromMap({
        'id': 'f3',
        'circleId': 'c1',
        'name': 'doc.pdf',
        'fileType': 'file',
        'uploaderId': 'u1',
        'createdAt': '2025-01-01T00:00:00.000Z',
        'updatedAt': '2025-01-01T00:00:00.000Z',
      });
      expect(file.isFolder, isFalse);
    });

    test('fromMap 支持 _id alias', () {
      final file = CircleFileDto.fromMap({
        '_id': 'mongo_file_id',
        'circleId': 'c1',
        'name': 'test.txt',
        'uploaderId': 'u1',
        'createdAt': '2025-01-01T00:00:00.000Z',
        'updatedAt': '2025-01-01T00:00:00.000Z',
      });
      expect(file.id, 'mongo_file_id');
    });
  });

  group('CircleFileDto — 兼容性契约', () {
    test('toMap 中 nullable 字段为空时不输出', () {
      final file = CircleFileDto(
        id: 'f1',
        circleId: 'c1',
        name: 'test.txt',
        fileType: 'file',
        uploaderId: 'u1',
        createdAt: DateTime.utc(2025),
        updatedAt: DateTime.utc(2025),
      );
      final map = file.toMap();
      expect(map.containsKey('parentFolderId'), isFalse);
      expect(map.containsKey('mimeType'), isFalse);
    });
  });

  group('CircleFileDto — 异常/边界契约', () {
    test('fromMap 缺失字段降级为默认值', () {
      final file = CircleFileDto.fromMap(const <String, dynamic>{});
      expect(file.id, '');
      expect(file.circleId, '');
      expect(file.name, '');
      expect(file.fileType, 'file');
      expect(file.sizeBytes, 0);
      expect(file.uploaderId, '');
      expect(file.status, 'active');
      expect(file.parentFolderId, isNull);
      expect(file.mimeType, isNull);
    });
  });

  group('CircleSectionConfigDto — 常规契约', () {
    test('fromMap / toMap round-trip 保留全字段', () {
      final config = CircleSectionConfigDto(
        sectionType: 'works',
        visible: true,
        order: 0,
        customTitle: 'My Works',
      );
      final map = config.toMap();
      final restored = CircleSectionConfigDto.fromMap(map);
      expect(restored.sectionType, 'works');
      expect(restored.customTitle, 'My Works');
      expect(restored.visible, true);
      expect(restored.order, 0);
    });

    test('copyWith 正确修改部分字段', () {
      final original = CircleSectionConfigDto(
        sectionType: 'chat',
        visible: true,
        order: 1,
      );
      final updated = original.copyWith(visible: false, order: 3);
      expect(updated.sectionType, 'chat');
      expect(updated.visible, false);
      expect(updated.order, 3);
    });
  });

  group('CircleSectionConfigDto — 兼容性契约', () {
    test('toMap 中 customTitle 为空时不输出', () {
      final config = CircleSectionConfigDto(
        sectionType: 'storage',
        visible: true,
        order: 2,
      );
      final map = config.toMap();
      expect(map.containsKey('customTitle'), isFalse);
      expect(map['sectionType'], 'storage');
      expect(map['visible'], true);
      expect(map['order'], 2);
    });
  });

  group('CircleSectionConfigDto — 异常/边界契约', () {
    test('fromMap 缺失字段降级为默认值', () {
      final config =
          CircleSectionConfigDto.fromMap(const <String, dynamic>{});
      expect(config.sectionType, 'works');
      expect(config.visible, true);
      expect(config.order, 0);
      expect(config.customTitle, isNull);
    });

    test('fromMap order 为 null 时降级为 0', () {
      final config = CircleSectionConfigDto.fromMap({
        'sectionType': 'works',
        'order': null,
      });
      expect(config.order, 0);
    });
  });
}
