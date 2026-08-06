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

    test('核心用户头像投影显式暴露 URL 字段与对应版本字段', () {
      const projectionFieldPairs = <String, List<List<String>>>{
        'quwoquan_service/services/user-service/contracts/account/user_account/projections/persona_profile_wire.yaml':
            <List<String>>[
              <String>['avatarUrl', 'avatarVersion'],
            ],
        'quwoquan_service/services/user-service/contracts/account/user_account/projections/active_persona_context_wire.yaml':
            <List<String>>[
              <String>['avatarUrl', 'avatarVersion'],
            ],
        'quwoquan_service/services/user-service/contracts/account/user_account/projections/profile_social_relation_row_wire.yaml':
            <List<String>>[
              <String>['avatarUrl', 'avatarVersion'],
            ],
        'quwoquan_service/services/user-service/contracts/account/user_account/projections/social_relation_search_item_wire.yaml':
            <List<String>>[
              <String>['avatarUrl', 'avatarVersion'],
            ],
        'quwoquan_service/services/content-service/contracts/content/profile_interaction_activity_view/projections/profile_interaction_activity_view.yaml':
            <List<String>>[
              <String>['actorAvatarUrl', 'actorAvatarVersion'],
              <String>['displayAvatarUrl', 'displayAvatarVersion'],
            ],
        'quwoquan_service/services/user-service/contracts/account/user_account/projections/persona_management_item_wire.yaml':
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
