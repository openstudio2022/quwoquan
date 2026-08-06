// spec_ref: specs/feature-tree/spec.md#uat-003
// spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-004
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

const _reportPath = String.fromEnvironment('QWQ_STARTUP_MATRIX_REPORT');
const _specRefs = <String>{
  'specs/feature-tree/spec.md#uat-003',
  'specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001',
  'specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-004',
  'specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001',
  'specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002',
};

void main() {
  test('四环境必需设备 profile 各 20 次启动与 telemetry readback 满足 GWT-004', () {
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
    expect(payload['required'], greaterThan(0));
    expect(payload['executed'], payload['required']);
    expect(payload['skipped'], 0);
    expect(payload['failed'], 0);
    expect(payload['baselineId'], isNotEmpty);
    expect(payload['releaseId'], isNotEmpty);
    expect(payload['releaseDigest'], matches(RegExp(r'^sha256:[0-9a-f]{64}$')));
    expect(
      (payload['specRefs'] as List<dynamic>).cast<String>().toSet(),
      containsAll(_specRefs),
    );
    final cases = (payload['cases'] as List<dynamic>)
        .cast<Map<String, dynamic>>();
    expect(cases, isNotEmpty);
    expect(
      cases.where((caseResult) => caseResult['required'] == true),
      everyElement(containsPair('status', 'passed')),
    );

    final packages = payload['packages'] as Map<String, dynamic>;
    expect(packages.keys.toSet(), {'alpha', 'beta', 'gamma', 'prod'});
    for (final package in packages.values.cast<Map<String, dynamic>>()) {
      expect(package['status'], 'component_ready');
      expect(
        package['effectiveLaunchManifestDigest'],
        matches(RegExp(r'^sha256:[0-9a-f]{64}$')),
      );
    }

    final evidence = payload['runtimeEvidence'] as Map<String, dynamic>;
    final readbackEvidence =
        payload['readbackEvidence'] as Map<String, dynamic>;
    final observabilityEvidence =
        payload['observabilityEvidence'] as Map<String, dynamic>;
    const requiredProfiles = {
      'alpha-local': {
        'android-simulator': ('android', 'simulator'),
        'android-physical': ('android', 'true_device'),
        'ios-simulator': ('ios', 'simulator'),
      },
      'beta-local': {
        'android-simulator': ('android', 'simulator'),
        'android-physical': ('android', 'true_device'),
        'ios-simulator': ('ios', 'simulator'),
      },
      'gamma-local': {
        'android-simulator': ('android', 'simulator'),
        'android-physical': ('android', 'true_device'),
        'ios-simulator': ('ios', 'simulator'),
      },
      'prod-hosted': {
        'android-physical': ('android', 'true_device'),
        'ios-physical': ('ios', 'physical'),
      },
    };
    expect(evidence.keys.toSet(), {
      for (final entry in requiredProfiles.entries)
        for (final profile in entry.value.keys) '${entry.key}/$profile',
    });
    expect(readbackEvidence.keys.toSet(), evidence.keys.toSet());
    expect(observabilityEvidence.keys.toSet(), requiredProfiles.keys.toSet());
    const targetEnvironments = {
      'alpha-local': 'alpha',
      'beta-local': 'beta',
      'gamma-local': 'gamma',
      'prod-hosted': 'prod',
    };
    for (final targetEntry in requiredProfiles.entries) {
      final target = targetEntry.key;
      final environment = targetEnvironments[target]!;
      final package = packages[environment] as Map<String, dynamic>;
      for (final profileEntry in targetEntry.value.entries) {
        final profile = profileEntry.key;
        final (platform, deviceKind) = profileEntry.value;
        final key = '$target/$profile';
        final caseResult = evidence[key] as Map<String, dynamic>;
        expect(caseResult['status'], 'passed', reason: key);
        final runtime = caseResult['evidence'] as Map<String, dynamic>;
        expect(runtime['baselineId'], payload['baselineId'], reason: key);
        expect(runtime['releaseId'], payload['releaseId'], reason: key);
        expect(runtime['releaseDigest'], payload['releaseDigest'], reason: key);
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
          expect(sample['deviceKind'], deviceKind, reason: key);
          expect(
            sample['deviceId'],
            isNot(anyOf(isEmpty, 'unknown')),
            reason: key,
          );
          if (platform == 'ios') {
            expect(sample['sceneLaunchUsed'], isTrue, reason: key);
            expect(sample['sceneStarted'], isTrue, reason: key);
            expect(
              sample['sceneLauncher'],
              anyOf('xcrun_simctl', 'xcrun_devicectl'),
              reason: key,
            );
          }
          expect(sample['canonicalTerminal'], 'routerShell', reason: key);
          expect(sample['startupSequenceMotionCurrent'], isTrue, reason: key);
          expect(sample['telemetryAcknowledged'], isTrue, reason: key);
          expect(
            sample['effectiveLaunchManifestDigest'],
            package['effectiveLaunchManifestDigest'],
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

        final readbackCase = readbackEvidence[key] as Map<String, dynamic>;
        expect(readbackCase['status'], 'passed', reason: key);
        final readback = readbackCase['evidence'] as Map<String, dynamic>;
        expect(readback['baselineId'], payload['baselineId'], reason: key);
        expect(readback['releaseId'], payload['releaseId'], reason: key);
        expect(
          readback['releaseDigest'],
          payload['releaseDigest'],
          reason: key,
        );
        expect(readback['executed'], greaterThan(0), reason: key);
        expect(readback['skipped'], 0, reason: key);
        expect(readback['failed'], 0, reason: key);
      }

      final observabilityCase =
          observabilityEvidence[target] as Map<String, dynamic>;
      expect(observabilityCase['status'], 'passed', reason: target);
      final observability =
          observabilityCase['evidence'] as Map<String, dynamic>;
      expect(
        observability['baselineId'],
        payload['baselineId'],
        reason: target,
      );
      expect(observability['releaseId'], payload['releaseId'], reason: target);
      expect(
        observability['releaseDigest'],
        payload['releaseDigest'],
        reason: target,
      );
      expect(observability['telemetryBackend'], isNotEmpty, reason: target);
      expect(observability['backendReceiptRef'], isNotEmpty, reason: target);
      expect(
        observability['executed'],
        observability['required'],
        reason: target,
      );
      expect(observability['skipped'], 0, reason: target);
      expect(observability['failed'], 0, reason: target);
    }
  });
}
