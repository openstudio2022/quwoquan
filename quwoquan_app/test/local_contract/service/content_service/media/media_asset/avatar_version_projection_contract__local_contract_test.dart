import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:yaml/yaml.dart';

File _repoFile(String relativePath) {
  final fromApp = File('${Directory.current.path}/../$relativePath');
  if (fromApp.existsSync()) {
    return fromApp;
  }
  return File('${Directory.current.path}/$relativePath');
}

YamlMap _loadYamlFile(String relativePath) {
  return loadYaml(_repoFile(relativePath).readAsStringSync()) as YamlMap;
}

YamlMap _contractTypes(String relativePath) {
  return (_loadYamlFile(relativePath)['types'] as YamlMap?) ?? YamlMap();
}

List<String> _typeFieldNames(YamlMap types, String typeName) {
  final body = types[typeName];
  if (body is! YamlMap) {
    return const <String>[];
  }
  final fields = body['fields'];
  if (fields is! YamlList) {
    return const <String>[];
  }
  return fields
      .whereType<YamlMap>()
      .map((field) => field['name']?.toString() ?? '')
      .where((name) => name.isNotEmpty)
      .toList(growable: false);
}

List<String> _projectionFieldNames(YamlMap yaml) {
  final rawFields =
      (yaml['client_projection'] as YamlMap?)?['fields'] ?? yaml['fields'];
  if (rawFields is! YamlList) {
    return const <String>[];
  }
  return rawFields
      .whereType<YamlMap>()
      .map((field) => field['name']?.toString() ?? '')
      .where((name) => name.isNotEmpty)
      .toList(growable: false);
}

void main() {
  group('avatarVersion 缓存契约', () {
    test('UserProfile contract 与头像解析器共用 avatarVersion 版本键', () {
      final userFields = _projectionFieldNames(
        _loadYamlFile(
          'quwoquan_service/services/user-service/contracts/account/user_account/fields.yaml',
        ),
      );
      final resolver = _repoFile(
        'quwoquan_app/lib/runtime/transport/media/avatar_image_url.dart',
      ).readAsStringSync();

      expect(userFields, containsAll(<String>['avatarUrl', 'avatarVersion']));
      expect(resolver, contains('version: avatarVersion ?? 0'));
    });

    test('自持头像的投影显式暴露 URL 字段与对应版本字段', () {
      // 用户身份 wire 已从 `projections/*_wire.yaml` 收敛进 fields.yaml 的
      // `types:`：本用例跟随真相源迁移，断言的仍是「谁自己持有头像版本，谁就
      // 必须同时暴露 URL 与版本」。
      const userAccountFields =
          'quwoquan_service/services/user-service/contracts/account/user_account/fields.yaml';
      const selfOwnedAvatarTypes = <String, List<String>>{
        // 当前登录人上下文：App 侧据此构造并失效自己的头像缓存。
        'ActivePersonaContextView': <String>['avatarUrl', 'avatarVersion'],
        // 资料编辑快照：提交后要靠版本判定本地缓存是否过期。
        'ProfileEditSnapshotWire': <String>['avatarUrl', 'avatarVersion'],
        // 头像同步补丁：版本是补丁能否覆盖既有缓存的唯一判据。
        'UserAvatarSyncPatchPayload': <String>['avatarUrl', 'avatarVersion'],
      };
      final declaredTypes = _contractTypes(userAccountFields);
      for (final entry in selfOwnedAvatarTypes.entries) {
        final fields = _typeFieldNames(declaredTypes, entry.key);
        expect(
          fields,
          isNotEmpty,
          reason: '$userAccountFields 缺少 type ${entry.key}',
        );
        expect(fields, containsAll(entry.value), reason: entry.key);
      }

      const activityView =
          'quwoquan_service/services/content-service/contracts/content/profile_interaction_activity_view/projections/profile_interaction_activity_view.yaml';
      final activityFields = _projectionFieldNames(_loadYamlFile(activityView));
      expect(
        activityFields,
        containsAll(<String>[
          'actorAvatarUrl',
          'actorAvatarVersion',
          'displayAvatarUrl',
          'displayAvatarVersion',
        ]),
        reason: activityView,
      );
    });

    test('头像版本字段不得脱离对应 URL 字段单独存在', () {
      const contractFiles = <String>[
        'quwoquan_service/services/user-service/contracts/account/user_account/fields.yaml',
        'quwoquan_service/services/user-service/contracts/persona_management/persona/fields.yaml',
      ];
      for (final path in contractFiles) {
        for (final entry in _contractTypes(path).entries) {
          final fields = _typeFieldNames(_contractTypes(path), entry.key);
          for (final field in fields.where(
            (name) => name.endsWith('AvatarVersion') || name == 'avatarVersion',
          )) {
            // 同前缀 URL（actorAvatarUrl/actorAvatarVersion）与单头像类型的
            // 裸 avatarUrl 都算成对；只有版本孤悬才是契约缺陷。
            final prefixed = field == 'avatarVersion'
                ? 'avatarUrl'
                : '${field.substring(0, field.length - 'AvatarVersion'.length)}AvatarUrl';
            expect(
              fields.any(
                (name) => name == prefixed || name == 'avatarUrl',
              ),
              isTrue,
              reason: '$path ${entry.key}.$field 缺少配对的头像 URL 字段',
            );
          }
        }
      }
    });

    test('未自带版本字段的对端头像投影由 canonical 版本化路径兜底', () {
      // 只读对端投影（他人资料、身份管理项、社交搜索项）不再重复下发版本：
      // 版本已内嵌在 canonical 媒体路径 `/v<N>/` 段里，解析器 fail-closed。
      final resolver = _repoFile(
        'quwoquan_app/lib/runtime/transport/media/media_delivery_reference.dart',
      ).readAsStringSync();
      expect(resolver, contains(r"RegExp(r'^v([1-9][0-9]*)$')"));
      expect(resolver, contains('公开媒体路径必须且只能包含一个正整数版本段'));
      expect(resolver, contains('请求版本与媒体路径版本不一致'));

      for (final mapper in <String>[
        'quwoquan_app/lib/service/user_service/persona_management/persona/adapters/persona_management_view_data_mapper.dart',
        'quwoquan_app/lib/service/user_service/persona_management/persona/adapters/social_relation_search_item_view_mapper.dart',
      ]) {
        expect(
          _repoFile(mapper).readAsStringSync(),
          contains('avatarVersion: 0'),
          reason: '$mapper 必须显式交由路径版本裁决，不得自造版本号',
        );
      }
    });
  });
}
