import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

const _reportPath = String.fromEnvironment('QWQ_STARTUP_WEB_REPORT');

void main() {
  test(
    'Web release 20 次启动满足 3/6 秒合同',
    () {
      final reportFile = File(_reportPath);
      expect(
        reportFile.existsSync(),
        isTrue,
        reason: 'QWQ_STARTUP_WEB_REPORT 必须指向真实探针报告',
      );

      final report = jsonDecode(reportFile.readAsStringSync());
      expect(report, isA<Map<String, dynamic>>());
      final payload = report as Map<String, dynamic>;
      expect(payload['platform'], 'web');
      expect(payload['motionSpec'], 'petal_bloom');
      expect(payload['motionSpecCurrent'], isTrue);
      expect(payload['passed'], isTrue);
      expect(payload['runs'], greaterThanOrEqualTo(20));
      expect(_metric(payload, 'p95', 'ttidMs'), lessThanOrEqualTo(2000));
      expect(
        _metric(payload, 'p95', 'shellFirstPaintMs'),
        lessThanOrEqualTo(3000),
      );
      expect(
        _metric(payload, 'p95', 'overlayRemovedMs'),
        lessThanOrEqualTo(6000),
      );
      expect(payload['welcomeExitOverHardCount'], 0);
      expect(payload['overlayRemovalOverHardCount'], 0);

      final samples = payload['samples'] as List<dynamic>;
      expect(samples, hasLength(greaterThanOrEqualTo(20)));
      for (final sampleValue in samples) {
        final sample = sampleValue as Map<String, dynamic>;
        expect(sample['welcomeExitMs'] as num, lessThanOrEqualTo(6000));
        expect(sample['shellFirstPaintMs'] as num, lessThanOrEqualTo(3000));
        expect(sample['overlayRemovedMs'] as num, lessThanOrEqualTo(6000));
        expect(sample['replayCount'] as num, lessThanOrEqualTo(2));
        expect(sample['exitReason'], isNotEmpty);
        expect(sample['motionSpec'], 'petal_bloom');
      }
    },
    skip: _reportPath.isEmpty
        ? '通过 --dart-define=QWQ_STARTUP_WEB_REPORT=<report.json> 注入真实报告'
        : false,
  );
}

num _metric(Map<String, dynamic> payload, String percentile, String key) {
  final group = payload[percentile] as Map<String, dynamic>;
  return group[key] as num;
}
