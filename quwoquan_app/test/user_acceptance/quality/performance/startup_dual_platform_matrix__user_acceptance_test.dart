// spec_ref: specs/feature-tree/spec.md#uat-003
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-004
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

const _reportPath = String.fromEnvironment('QWQ_STARTUP_MATRIX_REPORT');

void main() {
  test('双端五目标各 20 次启动与 telemetry readback 满足 UAT-003', () {
    expect(
      _reportPath,
      isNotEmpty,
      reason: '必须注入 verify_startup_environment_matrix.py 的真实报告',
    );
    final reportFile = File(_reportPath);
    expect(reportFile.existsSync(), isTrue);
    final report = jsonDecode(reportFile.readAsStringSync());
    expect(report, isA<Map<String, dynamic>>());
    final payload = report as Map<String, dynamic>;
    expect(payload['status'], 'passed');
    expect(payload['issues'], isEmpty);

    final packages = payload['packages'] as Map<String, dynamic>;
    expect(packages.keys.toSet(), {'alpha', 'beta', 'gamma', 'prod'});
    for (final package in packages.values.cast<Map<String, dynamic>>()) {
      expect(package['status'], 'passed');
      expect(
        package['effectiveLaunchManifestDigest'],
        matches(RegExp(r'^sha256:[0-9a-f]{64}$')),
      );
    }

    final evidence = payload['runtimeEvidence'] as Map<String, dynamic>;
    const targets = {
      'alpha-local',
      'beta-local',
      'gamma-local',
      'prod-sim',
      'prod-hosted',
    };
    for (final target in targets) {
      for (final platform in const ['android', 'ios']) {
        final key = '$target/$platform';
        final caseResult = evidence[key] as Map<String, dynamic>;
        expect(caseResult['status'], 'passed', reason: key);
        final runtime = caseResult['evidence'] as Map<String, dynamic>;
        expect(runtime['runs'], greaterThanOrEqualTo(20), reason: key);
        expect(runtime['passed'], isTrue, reason: key);
        final samples = runtime['samples'] as List<dynamic>;
        expect(samples.length, greaterThanOrEqualTo(20), reason: key);
        final attemptIds = <String>{};
        for (final value in samples) {
          final sample = value as Map<String, dynamic>;
          expect(sample['passed'], isTrue, reason: key);
          expect(sample['runtimeTarget'], target, reason: key);
          expect(sample['platform'], platform, reason: key);
          if (target == 'prod-hosted') {
            expect(sample['deviceKind'], 'physical', reason: key);
          }
          expect(sample['canonicalTerminal'], 'routerShell', reason: key);
          expect(sample['startupSequenceMotionCurrent'], isTrue, reason: key);
          expect(sample['telemetryAcknowledged'], isTrue, reason: key);
          expect(
            sample['effectiveLaunchManifestDigest'],
            matches(RegExp(r'^sha256:[0-9a-f]{64}$')),
            reason: key,
          );
          final attemptId = sample['attemptId'] as String;
          expect(attemptId, isNot(anyOf(isEmpty, 'unknown')), reason: key);
          expect(
            attemptIds.add(attemptId),
            isTrue,
            reason: '$key 重复 attemptId',
          );
        }
      }
    }
  });
}
