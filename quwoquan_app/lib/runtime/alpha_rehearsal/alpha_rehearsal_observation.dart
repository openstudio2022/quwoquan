import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/config/generated/app_launch_contract.g.dart';

/// 当前 isolated startup scope 唯一的脱敏 UAT 观察器；不持 payload/identity/key/path。
final class AlphaRehearsalObservation {
  AlphaRehearsalObservation._({
    required this.caseId,
    required this.attemptId,
    required this.generation,
    required this.binding,
    required this.snapshotDigest,
    required Future<Object?> Function(String method, [dynamic arguments]) invoke,
  }) : _invoke = invoke;

  static const MethodChannel channel = MethodChannel(
    'quwoquan/alpha_rehearsal/native_evidence',
  );
  static AlphaRehearsalObservation? _current;
  static AlphaRehearsalObservation? get current => _current;

  static final Map<String, dynamic> _relay =
      (jsonDecode(appLaunchManifestJson)
              as Map<String, dynamic>)['external_uat_observation_relay']
          as Map<String, dynamic>;
  static final Map<String, dynamic> _rendezvous =
      _relay['native_rendezvous'] as Map<String, dynamic>;
  static final Map<String, dynamic> _catalog =
      _relay['expected_observations'] as Map<String, dynamic>;
  static const Set<String> _sensitive = {
    'phone',
    'otp',
    'identity',
    'account',
    'challenge',
    'payload',
    'secret',
    'mac',
    'capability',
  };

  final String caseId;
  final String attemptId;
  final String generation;
  final String binding;
  final String snapshotDigest;
  final Future<Object?> Function(String method, [dynamic arguments]) _invoke;
  final List<Map<String, Object?>> _rows = <Map<String, Object?>>[];
  bool _valid = true;
  bool _sealed = false;

  static AlphaRehearsalObservation install({
    required String attemptId,
    Future<Object?> Function(String method, [dynamic arguments])? invoke,
  }) {
    final space = CloudRuntimeConfig.rehearsalSpace;
    if (space == null || !space.isIsolated || attemptId.isEmpty) {
      throw StateError('isolated observation requires a verified space');
    }
    return _install(
      caseId: space.caseId,
      attemptId: attemptId,
      generation: space.lifecycleGeneration,
      binding: space.observationBinding,
      snapshotDigest: space.snapshotDigest,
      invoke: invoke ?? channel.invokeMethod,
    );
  }

  @visibleForTesting
  static AlphaRehearsalObservation installForTest({
    required String caseId,
    required String attemptId,
    required String generation,
    required String binding,
    required String snapshotDigest,
    required Future<Object?> Function(String method, [dynamic arguments])
    invoke,
  }) {
    return _install(
      caseId: caseId,
      attemptId: attemptId,
      generation: generation,
      binding: binding,
      snapshotDigest: snapshotDigest,
      invoke: invoke,
    );
  }

  static AlphaRehearsalObservation _install({
    required String caseId,
    required String attemptId,
    required String generation,
    required String binding,
    required String snapshotDigest,
    required Future<Object?> Function(String method, [dynamic arguments])
    invoke,
  }) {
    if (!RegExp(r'^[1-9][0-9]{0,15}$').hasMatch(generation)) {
      throw StateError('observation generation is not canonical');
    }
    final observation = AlphaRehearsalObservation._(
      caseId: caseId,
      attemptId: attemptId,
      generation: generation,
      binding: binding,
      snapshotDigest: snapshotDigest,
      invoke: invoke,
    );
    _current?.invalidate();
    _current = observation;
    return observation;
  }

  Future<void> requireAdmission() async {
    _requireLive();
    await _invoke(_rendezvous['startup_binding_method'] as String, {
      'launchAttemptId': attemptId,
    });
    await _invoke(_rendezvous['observation_admission_method'] as String, {
      'launchAttemptId': attemptId,
      'caseId': caseId,
      'generation': int.parse(generation),
      'observationBinding': binding,
    });
    if (caseId == 'login-success' || caseId == 'login-error') {
      await _invoke('recordRedactedInput', <String, Object?>{
        'caseId': caseId,
        'selector': 'rehearsal-confirm-input',
        'sourceSelector': 'alpha-rehearsal-confirm',
        'mode': 'correct',
      });
      _append({
        'source': 'ui-control',
        'status': 'observed',
        'detail': 'unique-editable-control',
      });
    }
  }

  Future<void> recordSessionEstablished({
    required bool includeEditableControl,
  }) async {
    _requireLive();
    if (includeEditableControl) {
      _append({
        'source': 'ui-control',
        'status': 'observed',
        'detail': 'unique-editable-control',
      });
    }
    _append({
      'source': 'rehearsal-session-readback',
      'status': 'observed',
      'detail': 'session-established',
    });
    await _seal();
  }

  Future<void> recordRecoverableAuthError() async {
    _requireLive();
    _append({
      'source': 'rehearsal-auth-error-readback',
      'status': 'observed',
      'detail': 'recoverable-error-observed',
    });
    await _seal();
  }

  Future<void> recordLikeCommandQueryReadback() async {
    _requireLive();
    if (caseId == 'local-write') {
      _append({
        'source': 'local-command-query-readback',
        'status': 'observed',
        'detail': 'command-query-readback',
      });
    } else if (caseId == 'private-continuation') {
      _append({
        'source': 'continuation-query-readback',
        'status': 'observed',
        'detail': 'continued-once-readback',
      });
    } else {
      throw StateError('like readback is not owned by $caseId');
    }
    await _seal();
  }

  void recordRefusal(String source) {
    _requireLive();
    _append({
      'source': source,
      'status': 'observed',
      'detail': 'refused-at-side-effect-boundary',
      'attemptCount': 1,
    });
    unawaited(_seal());
  }

  void invalidate() {
    if (!_valid) return;
    _valid = false;
    _rows.clear();
    if (identical(_current, this)) {
      _current = null;
    }
  }

  void _requireLive() {
    if (!_valid || _sealed) {
      throw StateError('stale observation');
    }
  }

  void _append(Map<String, Object?> row) {
    if (row.keys.any((key) => _sensitive.contains(key.toLowerCase()))) {
      throw StateError('APP.UAT.relay_sensitive_field');
    }
    if (_rows.any((existing) => mapEquals(existing, row))) {
      return;
    }
    _rows.add(Map<String, Object?>.from(row));
  }

  Future<void> _seal() async {
    _requireLive();
    final expected =
        ((_catalog[caseId] as Map<String, dynamic>?)?['observations'] as List?)
            ?.map((row) => Map<String, Object?>.from(row as Map))
            .toList();
    if (expected != null &&
        (expected.length != _rows.length ||
            !List.generate(
              expected.length,
              (index) => mapEquals(_rows[index], expected[index]),
            ).every((matched) => matched))) {
      throw StateError('observation rows drifted from catalog');
    }
    await _invoke('sealObservation', <String, Object?>{
      'schema': runtimeDocumentSchemaValues['external_uat_sealed_snapshot'],
      'caseId': caseId,
      'launchAttemptId': attemptId,
      'generation': int.parse(generation),
      'observationBinding': binding,
      'observations': List<Map<String, Object?>>.from(_rows),
    });
    _sealed = true;
  }
}
