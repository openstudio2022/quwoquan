// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('生产闭包除 Alpha composition 外不导入 alpha_rehearsal', () {
    final allowed = <String>{
      'lib/runtime/di/alpha_dependencies.dart',
    };
    final violations = <String>[];
    for (final entity in Directory('lib').listSync(recursive: true)) {
      if (entity is! File || !entity.path.endsWith('.dart')) {
        continue;
      }
      final path = entity.path.replaceAll('\\', '/');
      if (path.startsWith('lib/runtime/alpha_rehearsal/')) {
        continue;
      }
      if (allowed.contains(path)) {
        continue;
      }
      final source = entity.readAsStringSync();
      if (source.contains('package:quwoquan_app/runtime/alpha_rehearsal/')) {
        violations.add(path);
      }
    }
    expect(violations, isEmpty, reason: violations.join('\n'));
  });
}
