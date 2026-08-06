import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('production bootstrap 直接进入唯一 Remote composition', () {
    final source = File('lib/main_prod.dart').readAsStringSync();
    expect(source, contains('await runQuwoquanApp();'));
    expect(source, isNot(contains('providerScopeOverrides')));
    expect(source, isNot(contains('AppDataSourceMode')));
    expect(source, isNot(contains('appDataSourceModeProvider')));
  });
}
