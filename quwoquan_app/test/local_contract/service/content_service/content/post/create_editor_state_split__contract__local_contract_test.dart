import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  const groups = <String, List<String>>{
    'create_editor_provider': <String>[
      'lib/service/content_service/content/post/application/create_editor_provider.dart',
      'lib/service/content_service/content/post/application/create_editor_provider_document_operations.dart',
      'lib/service/content_service/content/post/application/create_editor_provider_media_operations.dart',
      'lib/service/content_service/content/post/application/create_editor_provider_node_editing_operations.dart',
      'lib/service/content_service/content/post/application/create_editor_provider_node_structure_operations.dart',
    ],
    'create_editor_models': <String>[
      'lib/service/content_service/content/post/domain/create_editor_models.dart',
      'lib/service/content_service/content/post/domain/create_editor_models_draft.dart',
    ],
    'create_media_picker': <String>[
      'lib/service/content_service/media/media_upload_session/presentation/create_media_picker_page.dart',
      'lib/service/content_service/media/media_upload_session/presentation/create_media_picker_page_state.dart',
      'lib/service/content_service/media/media_upload_session/presentation/create_media_picker_page_state_helpers.dart',
      'lib/service/content_service/media/media_upload_session/presentation/create_media_picker_page_chrome.dart',
    ],
    'image_editor_operation_panel': <String>[
      'lib/service/content_service/media/filter_catalog_release/presentation/image_editor_operation_panel.dart',
      'lib/service/content_service/media/filter_catalog_release/presentation/image_editor_operation_panel_pro.dart',
      'lib/service/content_service/media/filter_catalog_release/presentation/image_editor_operation_panel_controls.dart',
      'lib/service/content_service/media/filter_catalog_release/presentation/image_editor_operation_panel_filter.dart',
    ],
  };

  test('创作状态专项手写文件均低于 R03 千行红线', () {
    for (final group in groups.entries) {
      for (final path in group.value) {
        final lineCount = const LineSplitter()
            .convert(_readAppFile(path))
            .length;
        expect(
          lineCount,
          lessThan(1000),
          reason: '${group.key}: $path 有 $lineCount 行，必须继续按职责拆分',
        );
      }
    }
  });

  test('companion 只扩展父 library，状态与组件各保留一个真相源', () {
    for (final files in groups.values) {
      final parentSource = _readAppFile(files.first);
      final parentName = files.first.split('/').last;
      for (final companion in files.skip(1)) {
        final companionName = companion.split('/').last;
        expect(parentSource, contains("part '$companionName';"));
        expect(_readAppFile(companion), contains("part of '$parentName';"));
      }
    }

    final providerSources = _joinSources(groups['create_editor_provider']!);
    final modelSources = _joinSources(groups['create_editor_models']!);
    final pickerSources = _joinSources(groups['create_media_picker']!);
    final panelSources = _joinSources(groups['image_editor_operation_panel']!);

    expect(
      RegExp(
        r'class\s+CreateEditorNotifier\s+extends',
      ).allMatches(providerSources),
      hasLength(1),
    );
    expect(
      RegExp(r'class\s+CreateEditorState\b').allMatches(modelSources),
      hasLength(1),
    );
    expect(
      RegExp(r'class\s+CreateDraft\b').allMatches(modelSources),
      hasLength(1),
    );
    expect(
      RegExp(
        r'class\s+_CreateMediaPickerPageState\s+extends',
      ).allMatches(pickerSources),
      hasLength(1),
    );
    expect(
      RegExp(
        r'class\s+ImageEditorOperationPanel\s+extends',
      ).allMatches(panelSources),
      hasLength(1),
    );
  });

  test('测试注入与语义 token 保持在同一生产链路', () {
    final pickerSources = _joinSources(groups['create_media_picker']!);
    final panelSources = _joinSources(groups['image_editor_operation_panel']!);

    expect(pickerSources, contains('required this.mediaPickerPort'));
    expect(pickerSources, contains('final MediaPickerPort mediaPickerPort'));
    expect(pickerSources, contains('this.imageEditorBuilder'));
    expect(pickerSources, contains('this.cameraBuilder'));
    expect(panelSources, contains('AppSpacing.'));
    expect(panelSources, contains('MediaText.'));
    expect(panelSources, contains('ContentText.'));
  });

  test('四个已达标原文件不再进入 file_line_budget allowlist', () {
    final allowlist = _readRepoFile(
      'quwoquan_ops/policies/gates/file_line_budget_allowlist.yaml',
    );
    for (final files in groups.values) {
      expect(
        allowlist,
        isNot(contains('quwoquan_app/${files.first}')),
        reason: '${files.first} 已低于阈值，不得保留 allowlist 豁免',
      );
    }
  });
}

String _joinSources(List<String> paths) {
  return paths.map(_readAppFile).join('\n');
}

String _readAppFile(String relativePath) {
  final direct = File(relativePath);
  if (direct.existsSync()) {
    return direct.readAsStringSync();
  }
  return File('quwoquan_app/$relativePath').readAsStringSync();
}

String _readRepoFile(String relativePath) {
  final direct = File(relativePath);
  if (direct.existsSync()) {
    return direct.readAsStringSync();
  }
  return File('../$relativePath').readAsStringSync();
}
