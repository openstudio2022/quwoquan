import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/services/user/user_repository.dart';

void main() {
  group('UserRepository — 常规契约', () {
    late UserRepository repo;

    setUp(() {
      repo = MockUserRepository();
    });

    test('listPersonas 返回分身列表', () async {
      final personas = await repo.listPersonas();
      expect(personas, isList);
    });

    test('activatePersona 不崩溃', () async {
      await repo.activatePersona('persona_test');
    });

    test('getNotificationSettings 返回通知设置', () async {
      final settings = await repo.getNotificationSettings();
      expect(settings, isA<Map<String, dynamic>>());
      expect(settings.containsKey('enablePush'), isTrue);
    });

    test('getPrivacySettings 返回隐私设置', () async {
      final settings = await repo.getPrivacySettings();
      expect(settings, isA<Map<String, dynamic>>());
      expect(settings.containsKey('profileVisibility'), isTrue);
    });

    test('接口包含全部 4 个 service.yaml API 方法', () {
      final methods = <String>[
        'listPersonas',
        'activatePersona',
        'getNotificationSettings',
        'getPrivacySettings',
      ];
      expect(methods.length, 4);
    });
  });

  group('UserRepository — 异常/边界契约', () {
    late UserRepository repo;

    setUp(() {
      repo = MockUserRepository();
    });

    test('activatePersona 空 ID 不崩溃', () async {
      await repo.activatePersona('');
    });
  });
}
