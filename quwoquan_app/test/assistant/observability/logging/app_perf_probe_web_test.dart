import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_perf_probe.dart';

void main() {
  test('snapshot does not read ProcessInfo RSS on web', () {
    final payload = AppPerfProbe.snapshot(event: 'open', route: '/');
    final memory = payload['memory'] as Map<String, dynamic>;

    expect(memory, contains('rssMb'));
    if (kIsWeb) {
      expect(memory['rssMb'], isNull);
    }
  });
}
