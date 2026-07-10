import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_profile_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_setting_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_full_snapshot_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_work_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_life_item_dto.g.dart';

void main() {
  group('UserProfileDto — 常规契约', () {
    test('全字段解析正确', () {
      final dto = UserProfileDto.fromJson({
        'userId': 'u001',
        'nickname': 'alice',
        'avatarUrl': 'https://cdn.example.com/avatar.jpg',
        'bio': 'Hello world',
        'gender': 'female',
        'birthDate': '1995-06-15',
        'region': '北京',
        'status': 'active',
        'profileVersion': 3,
        'followerCount': 100,
        'followingCount': 50,
        'postCount': 42,
        'circleCount': 5,
        'likeCount': 200,
        'createdAt': '2024-01-01T00:00:00Z',
        'updatedAt': '2024-06-01T00:00:00Z',
      });
      expect(dto.userId, 'u001');
      expect(dto.nickname, 'alice');
      expect(dto.avatarUrl, contains('avatar'));
      expect(dto.status, 'active');
      expect(dto.profileVersion, 3);
      expect(dto.followerCount, 100);
      expect(dto.followingCount, 50);
      expect(dto.postCount, 42);
      expect(dto.circleCount, 5);
      expect(dto.likeCount, 200);
    });

    test('toJson round-trip 稳定', () {
      final original = UserProfileDto.fromJson({
        'userId': 'u002',
        'nickname': 'bob',
        'status': 'active',
        'profileVersion': 1,
        'followerCount': 0,
        'followingCount': 0,
        'postCount': 0,
        'circleCount': 0,
        'likeCount': 0,
        'createdAt': '2024-01-01T00:00:00Z',
        'updatedAt': '2024-01-01T00:00:00Z',
      });
      final json = original.toJson();
      final restored = UserProfileDto.fromJson(json);
      expect(restored.userId, original.userId);
      expect(restored.nickname, original.nickname);
      expect(restored.followerCount, original.followerCount);
    });
  });

  group('UserProfileDto — 兼容性契约', () {
    test('可选字段缺失使用默认值', () {
      final dto = UserProfileDto.fromJson({
        'userId': 'u003',
        'nickname': 'charlie',
      });
      expect(dto.status, 'active');
      expect(dto.profileVersion, 1);
      expect(dto.followerCount, 0);
      expect(dto.avatarUrl, isNull);
      expect(dto.bio, isNull);
    });

    test('PII 字段 phone 不在 DTO 中', () {
      final json = UserProfileDto.fromJson({
        'userId': 'u004',
        'nickname': 'dave',
      }).toJson();
      expect(json.containsKey('phone'), isFalse);
    });
  });

  group('UserProfileDto — 异常/边界契约', () {
    test('全字段缺失不崩溃', () {
      expect(
        () => UserProfileDto.fromJson(<String, dynamic>{}),
        throwsA(isA<TypeError>()),
      );
    });
  });

  group('PersonaDto — 常规契约', () {
    test('全字段解析正确', () {
      final dto = PersonaDto.fromJson({
        'id': 'p001',
        'userId': 'u001',
        'displayName': 'Shadow',
        'avatarUrl': 'https://cdn.example.com/shadow.jpg',
        'isPrimary': true,
        'isPrivate': false,
        'isActive': true,
        'createdAt': '2024-01-01T00:00:00Z',
        'updatedAt': '2024-06-01T00:00:00Z',
      });
      expect(dto.id, 'p001');
      expect(dto.displayName, 'Shadow');
      expect(dto.isPrimary, true);
      expect(dto.isActive, true);
    });

    test('boolean 字段缺失默认 false', () {
      final dto = PersonaDto.fromJson({
        'id': 'p002',
        'userId': 'u002',
        'displayName': 'Anon',
      });
      expect(dto.isPrimary, false);
      expect(dto.isPrivate, false);
      expect(dto.isActive, false);
    });
  });

  group('UserSettingDto — 常规契约', () {
    test('全字段解析正确', () {
      final dto = UserSettingDto.fromJson({
        'userId': 'u001',
        'enablePush': true,
        'enableMarketing': false,
        'quietHoursStart': '22:00',
        'quietHoursEnd': '07:00',
        'allowStrangerMsg': true,
        'profileVisibility': 'public',
        'assistantEnabled': true,
        'updatedAt': '2024-06-01T00:00:00Z',
      });
      expect(dto.enablePush, true);
      expect(dto.allowStrangerMsg, true);
      expect(dto.profileVisibility, 'public');
      expect(dto.assistantEnabled, true);
    });

    test('默认值正确', () {
      final dto = UserSettingDto.fromJson({'userId': 'u002'});
      expect(dto.enablePush, true);
      expect(dto.enableMarketing, false);
      expect(dto.allowStrangerMsg, true);
      expect(dto.profileVisibility, 'public');
      expect(dto.assistantEnabled, true);
    });
  });

  group('UserFullSnapshotDto — 常规契约', () {
    test('完整快照解析含嵌套对象', () {
      final dto = UserFullSnapshotDto.fromJson({
        'profile': {
          'userId': 'u001',
          'nickname': 'alice',
          'status': 'active',
          'profileVersion': 1,
          'followerCount': 10,
          'followingCount': 5,
          'postCount': 3,
          'circleCount': 1,
          'likeCount': 20,
          'createdAt': '2024-01-01T00:00:00Z',
          'updatedAt': '2024-01-01T00:00:00Z',
        },
        'activePersona': {
          'id': 'p001',
          'userId': 'u001',
          'displayName': 'Alice',
          'isPrimary': true,
          'isActive': true,
        },
        'settings': {
          'userId': 'u001',
          'enablePush': true,
          'profileVisibility': 'public',
        },
      });
      expect(dto.profile.userId, 'u001');
      expect(dto.activePersona?.displayName, 'Alice');
      expect(dto.settings?.enablePush, true);
    });

    test('可选嵌套对象为 null', () {
      final dto = UserFullSnapshotDto.fromJson({
        'profile': {
          'userId': 'u002',
          'nickname': 'bob',
          'status': 'active',
          'profileVersion': 1,
          'followerCount': 0,
          'followingCount': 0,
          'postCount': 0,
          'circleCount': 0,
          'likeCount': 0,
          'createdAt': '',
          'updatedAt': '',
        },
      });
      expect(dto.activePersona, isNull);
      expect(dto.settings, isNull);
    });
  });

  group('UserWorkDto — 常规契约', () {
    test('全字段解析正确', () {
      final dto = UserWorkDto.fromJson({
        'id': 'w001',
        'userId': 'u001',
        'title': '摄影作品集',
        'coverUrl': 'https://cdn.example.com/cover.jpg',
        'workType': 'photography',
        'refId': 'ref_001',
        'sortOrder': 1,
        'createdAt': '2024-01-01T00:00:00Z',
        'updatedAt': '2024-06-01T00:00:00Z',
      });
      expect(dto.id, 'w001');
      expect(dto.title, '摄影作品集');
      expect(dto.workType, 'photography');
    });
  });

  group('UserLifeItemDto — 常规契约', () {
    test('全字段解析正确', () {
      final dto = UserLifeItemDto.fromJson({
        'id': 'li001',
        'userId': 'u001',
        'category': 'travel',
        'title': '日本之旅',
        'subtitle': '东京/京都',
        'imageUrl': 'https://cdn.example.com/japan.jpg',
        'sortOrder': 0,
        'createdAt': '2024-01-01T00:00:00Z',
        'updatedAt': '2024-06-01T00:00:00Z',
      });
      expect(dto.id, 'li001');
      expect(dto.category, 'travel');
      expect(dto.title, '日本之旅');
    });
  });
}
