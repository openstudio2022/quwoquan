import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  const appFiles = <String>[
    'lib/service/entity_service/entity_homepage/homepage_status_report/presentation/homepage_status_report_page.dart',
    'lib/service/entity_service/entity_homepage/homepage_status_report/presentation/homepage_status_report_page_state.dart',
  ];

  test('主页状态上报手写文件均低于 R03 千行红线', () {
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

    expect(
      sources[appFiles[0]],
      contains("part 'homepage_status_report_page_state.dart';"),
    );
    expect(
      sources[appFiles[1]],
      contains("part of 'homepage_status_report_page.dart';"),
    );
  });

  test('主页状态上报只保留一个页面与 State 真相源', () {
    final combined = <String>[
      for (final path in appFiles) _readAppFile(path),
    ].join('\n');

    expect(
      RegExp(
        r'class\s+HomepageStatusReportPage\s+extends',
      ).allMatches(combined),
      hasLength(1),
    );
    expect(
      RegExp(
        r'class\s+_HomepageStatusReportPageState\s+extends',
      ).allMatches(combined),
      hasLength(1),
    );
  });

  test('已达标 HomepageStatusReport 文件不得进入 code health policy', () {
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
