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

List<String> _projectionFieldNames(YamlMap yaml) {
  final rawFields = (yaml['client_projection'] as YamlMap?)?['fields'];
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
    test('UserProfile cache policy 把 avatarVersion 作为头像资源版本键', () {
      final policy = _loadYamlFile(
        'specs/feature-tree/runtime/runtime-client-foundation/local-cache-architecture/object-cache-policy.yaml',
      );
      final userProfile =
          (policy['objects'] as YamlMap)['UserProfile'] as YamlMap;
      final resourceRefs = userProfile['resource_refs'] as YamlMap;
      final avatar = resourceRefs['avatar'] as YamlMap;
      final tests = (userProfile['tests'] as YamlList).cast<Object?>();

      expect(avatar['version_key'], 'avatarVersion');
      expect(tests, contains('avatar_version_invalidation'));
    });

    test('核心用户头像投影显式暴露 URL 字段与对应版本字段', () {
      const projectionFieldPairs = <String, List<List<String>>>{
        'quwoquan_service/contracts/metadata/user/user_profile/projections/sub_account_profile_wire.yaml':
            <List<String>>[
              <String>['avatarUrl', 'avatarVersion'],
            ],
        'quwoquan_service/contracts/metadata/user/user_profile/projections/active_persona_context_wire.yaml':
            <List<String>>[
              <String>['avatarUrl', 'avatarVersion'],
            ],
        'quwoquan_service/contracts/metadata/user/user_profile/projections/profile_social_relation_row_wire.yaml':
            <List<String>>[
              <String>['avatarUrl', 'avatarVersion'],
            ],
        'quwoquan_service/contracts/metadata/user/user_profile/projections/social_relation_search_item_wire.yaml':
            <List<String>>[
              <String>['avatarUrl', 'avatarVersion'],
            ],
        'quwoquan_service/contracts/metadata/user/user_profile/projections/profile_user_like_row_wire.yaml':
            <List<String>>[
              <String>['likerAvatarUrl', 'likerAvatarVersion'],
            ],
        'quwoquan_service/contracts/metadata/user/user_profile/projections/profile_interaction_activity_wire.yaml':
            <List<String>>[
              <String>['actorAvatarUrl', 'actorAvatarVersion'],
              <String>['displayAvatarUrl', 'displayAvatarVersion'],
            ],
        'quwoquan_service/contracts/metadata/user/user_profile/projections/persona_management_item_wire.yaml':
            <List<String>>[
              <String>['avatarUrl', 'avatarVersion'],
            ],
      };

      for (final entry in projectionFieldPairs.entries) {
        final yaml = _loadYamlFile(entry.key);
        final fields = _projectionFieldNames(yaml);
        for (final pair in entry.value) {
          expect(fields, contains(pair.first), reason: entry.key);
          expect(fields, contains(pair.last), reason: entry.key);
        }
      }
    });
  });
}
