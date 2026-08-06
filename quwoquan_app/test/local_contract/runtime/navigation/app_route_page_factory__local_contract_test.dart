import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  group('AppRoutePageFactory static contract', () {
    test('app_router routes ordinary pages through appRoutePage', () {
      final source = File(
        'lib/runtime/di/navigation/app_router.dart',
      ).readAsStringSync();

      expect(source, contains("native_back_navigation.dart"));
      expect(source, contains("AppNativeBackScope"));
      expect(source, isNot(contains("builder: (context, state)")));
      expect(source, isNot(contains("MaterialPage<")));
      expect(
        "appRoutePage<".allMatches(source).length,
        greaterThanOrEqualTo(30),
      );
    });
  });
}
