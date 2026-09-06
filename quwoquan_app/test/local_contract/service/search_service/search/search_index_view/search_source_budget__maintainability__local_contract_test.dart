import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  const appFiles = <String>[
    'lib/service/circle_service/circle_management/circle/application/public/circle_search_hit_views.dart',
    'lib/service/integration_service/external_integration/location/application/public/search_location_place_hit_view.dart',
    'lib/service/entity_service/entity_homepage/homepage_search_item_view/application/public/search_entity_homepage_hit_view.dart',
    'lib/service/integration_service/external_integration/location/application/public/search_location_suggestion_view.dart',
    'lib/service/search_service/search/search_index_view/application/post_search_item_view.dart',
    'lib/service/search_service/search/search_index_view/application/search_hit_payload.dart',
    'lib/service/search_service/search/search_index_view/application/public/search_launch_contract.dart',
    'lib/service/search_service/search/search_index_view/application/public/search_query_contract.dart',
    'lib/service/search_service/search/search_index_view/presentation/search_inspiration_models.dart',
    'lib/service/search_service/search/search_index_view/presentation/search_session_state.dart',
    'lib/service/search_service/search/search_index_view/presentation/search_suggestion_models.dart',
    'lib/service/user_service/account/user_account/application/public/search_user_profile_hit_view.dart',
    'lib/service/user_service/account/user_account/application/public/social_relation_search_item_view_data.dart',
  ];
  const publicSeams = <String>[
    'lib/service/circle_service/circle_management/circle/application/public/circle_search_hit_views.dart',
    'lib/service/integration_service/external_integration/location/application/public/search_location_place_hit_view.dart',
    'lib/service/entity_service/entity_homepage/homepage_search_item_view/application/public/search_entity_homepage_hit_view.dart',
    'lib/service/integration_service/external_integration/location/application/public/search_location_suggestion_view.dart',
    'lib/service/user_service/account/user_account/application/public/search_user_profile_hit_view.dart',
    'lib/service/user_service/account/user_account/application/public/social_relation_search_item_view_data.dart',
  ];
  const retiredCoreFiles = <String>[
    'lib/core/models/search_models.dart',
    'lib/core/models/search_models_presentation.dart',
    'lib/core/models/search_hit_payload.dart',
  ];

  test('搜索模型手写文件均低于 R03 千行红线', () {
    final sources = <String, String>{
      for (final path in appFiles) path: _readAppFile(path),
    };

    for (final entry in sources.entries) {
      final lineCount = const LineSplitter().convert(entry.value).length;
      expect(
        lineCount,
        lessThan(1000),
        reason: '${entry.key} 有 $lineCount 行，必须继续按职责拆分',
      );
    }
  });

  test('owner application public seams 不反向依赖 UI、adapter、runtime 或 core', () {
    const forbiddenImports = <String>[
      'package:flutter/',
      '/adapters/',
      '/presentation/',
      '/runtime/',
      '/core/',
    ];
    for (final path in publicSeams) {
      final source = _readAppFile(path);
      for (final forbidden in forbiddenImports) {
        expect(
          source,
          isNot(contains(forbidden)),
          reason: '$path public seam 不得依赖 $forbidden',
        );
      }
    }
  });

  test('旧 core Search model 文件与 directive 已清零', () {
    for (final path in retiredCoreFiles) {
      expect(_appFile(path).existsSync(), isFalse, reason: '$path 必须删除');
    }

    final retiredDirective = RegExp(
      r'''^(?:(?:import|export)\s+['"][^'"]*core/models/(?:search_models|search_models_presentation|search_hit_payload)\.dart['"];|part\s+['"]search_models_presentation\.dart['"];|part\s+of\s+['"]search_models\.dart['"];)$''',
      multiLine: true,
    );
    for (final root in <String>['lib', 'test']) {
      final directory = _appDirectory(root);
      for (final entity in directory.listSync(recursive: true)) {
        if (entity is! File || !entity.path.endsWith('.dart')) {
          continue;
        }
        expect(
          entity.readAsStringSync(),
          isNot(matches(retiredDirective)),
          reason: '${entity.path} 不得继续引用旧 core Search model',
        );
      }
    }
  });

  test('已达标 Search 文件不得进入 code health policy', () {
    final allowlist = _readRepoFile(
      'quwoquan_ops/policies/code_health_policy.yaml',
    );

    for (final path in appFiles) {
      expect(
        allowlist,
        isNot(contains('quwoquan_app/$path')),
        reason: '$path 已低于阈值，不得新增 路径豁免',
      );
    }
  });
}

String _readAppFile(String relativePath) {
  return _appFile(relativePath).readAsStringSync();
}

File _appFile(String relativePath) => File(_appPath(relativePath));

Directory _appDirectory(String relativePath) =>
    Directory(_appPath(relativePath));

String _appPath(String relativePath) {
  final directFile = File(relativePath);
  final directDirectory = Directory(relativePath);
  if (directFile.existsSync() || directDirectory.existsSync()) {
    return relativePath;
  }
  return 'quwoquan_app/$relativePath';
}

String _readRepoFile(String relativePath) {
  final direct = File(relativePath);
  if (direct.existsSync()) {
    return direct.readAsStringSync();
  }
  return File('../$relativePath').readAsStringSync();
}
