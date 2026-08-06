import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/create_page_provider_bridge.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

void main() {
  const createPageFiles = <String>[
    'lib/service/content_service/content/post/presentation/create_page.dart',
    'lib/service/content_service/content/post/presentation/create_page_state.dart',
    'lib/service/content_service/content/post/presentation/create_page_state_helpers.dart',
    'lib/service/content_service/content/post/presentation/create_page_state_media_helpers.dart',
    'lib/service/content_service/content/post/presentation/create_page_state_chrome_helpers.dart',
    'lib/service/content_service/content/post/presentation/create_page_state_draft_helpers.dart',
    'lib/service/content_service/content/post/presentation/create_page_state_surface_helpers.dart',
  ];

  test('CreatePage 手写文件均低于 R03 千行红线，且只有一个 State 真相源', () {
    final sources = <String, String>{
      for (final path in createPageFiles) path: _readAppFile(path),
    };

    for (final entry in sources.entries) {
      final lineCount = const LineSplitter().convert(entry.value).length;
      expect(
        lineCount,
        lessThan(1000),
        reason: '${entry.key} 有 $lineCount 行，必须继续按职责拆分',
      );
    }

    final combined = sources.values.join('\n');
    expect(
      RegExp(r'class\s+_CreatePageState\s+extends').allMatches(combined),
      hasLength(1),
    );
    for (final path in createPageFiles.skip(1)) {
      expect(sources[path], contains("part of 'create_page.dart';"));
      expect(
        sources[createPageFiles.first],
        contains("part '${path.split('/').last}';"),
      );
    }
  });

  test('active persona 不可用使用 typed RuntimeFailure 与可恢复语义', () {
    final failure = ActivePersonaContextUnavailableFailure();

    expect(failure, isA<RuntimeFailure>());
    expect(failure.code, ContentErrorCode.requiredDependencyUnavailable.code);
    expect(failure.semanticReason, 'active_persona_context_unavailable');
    expect(failure.kind, RuntimeFailureKind.unavailable);
    expect(failure.recovery.action, 'retry');
    expect(failure.recovery.disruptionLevel, 'surface');
  });

  test('发布失败恢复在上一轮 finally 清理后串行重新进入', () {
    final source = _readAppFile(
      'lib/service/content_service/content/post/presentation/create_page_state_media_helpers.dart',
    );
    final actionBody = RegExp(
      r'onAction: \(action\) async \{(?<body>.*?)\n\s+\},',
      dotAll: true,
    ).firstMatch(source)?.namedGroup('body');

    expect(actionBody, isNotNull);
    expect(actionBody, contains('retryRequested = true;'));
    expect(actionBody, isNot(contains('_publish()')));
    expect(
      source.indexOf('if (retryRequested && mounted)'),
      greaterThan(source.indexOf('} finally {')),
      reason: '重试必须等上一轮发布 finally 完成，禁止两个 _publish 共享并覆盖上传状态。',
    );
  });

  test('文章编辑器不暴露未实现的列表与层级假入口', () {
    final stylePanel = _readAppFile(
      'lib/service/content_service/content/post/presentation/article_editor_accessory_style_panels.dart',
    );
    final selectionPanel = _readAppFile(
      'lib/service/content_service/content/post/presentation/article_editor_accessory_selection_panels.dart',
    );

    expect(stylePanel, isNot(contains('_CnListIcon')));
    expect(stylePanel, isNot(contains('onTap: () {}')));
    expect(selectionPanel, isNot(contains('onTap: () {}')));
    expect(selectionPanel, isNot(contains('CreatePageText.hierarchy')));
  });
}

String _readAppFile(String relativePath) {
  final direct = File(relativePath);
  if (direct.existsSync()) {
    return direct.readAsStringSync();
  }
  return File('quwoquan_app/$relativePath').readAsStringSync();
}
