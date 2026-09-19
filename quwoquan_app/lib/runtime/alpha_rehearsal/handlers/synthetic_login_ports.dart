import 'dart:convert';
import 'dart:math';

import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_space_binding.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_identity.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';
import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/application/public/synthetic_challenge_port.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/application/public/synthetic_session_port.dart';
import 'package:quwoquan_cloud_contracts/generated/values/user/account/authentication_challenge.values.dart';
import 'package:quwoquan_cloud_contracts/generated/values/user/account/account_session.values.dart';

/// 未自动安装。组合根还须在首次 auth/pending 访问前完成同 binding 接线。
/// 所有请求/结果不写日志；此对象本身不授予 native 输入或证据采集权。
final class AlphaSyntheticLoginPorts
    implements SyntheticChallengePort, SyntheticSessionPort {
  AlphaSyntheticLoginPorts({
    required VerifiedRehearsalSpace space,
    required this.currentSpace,
    required FileStorageGateway gateway,
    AlphaRehearsalStore? store,
    AlphaRehearsalIdentityOwner? identityOwner,
    DateTime Function()? now,
    this.randomHex,
  }) : _space = space,
       _now = now ?? DateTime.now {
    _checkRuntime();
    binding = RehearsalSpaceBinding.verified(space);
    if (store != null) {
      binding.verifyStorage(
        snapshot: store.snapshotDigest,
        instance: store.instanceId,
      );
    }
    _store =
        store ?? AlphaRehearsalStore.bound(binding: binding, gateway: gateway);
    _identityOwner = identityOwner ?? AlphaRehearsalIdentityOwner(_store);
    if (!identical(_identityOwner.store, _store)) {
      throw StateError('Synthetic login identity owner/store mismatch');
    }
  }

  final VerifiedRehearsalSpace _space;
  final VerifiedRehearsalSpace? Function() currentSpace;
  final DateTime Function() _now;
  final String Function()? randomHex;
  final Random _random = Random.secure();
  late final RehearsalSpaceBinding binding;
  late final AlphaRehearsalStore _store;
  late final AlphaRehearsalIdentityOwner _identityOwner;
  bool _disposed = false;

  void dispose() {
    _disposed = true;
  }

  void _checkRuntime() {
    final VerifiedRehearsalSpace? current;
    try {
      current = currentSpace();
    } catch (_) {
      _fail(SyntheticLoginFailureReason.unavailable);
    }
    if (_disposed ||
        !identical(current, _space) ||
        !_space.isIsolated ||
        _space.instanceId == 'default') {
      _fail(SyntheticLoginFailureReason.unavailable);
    }
  }

  String _hex() =>
      randomHex?.call() ??
      List.generate(
        16,
        (_) => _random.nextInt(256).toRadixString(16).padLeft(2, '0'),
      ).join();

  SyntheticIdentityLabel createIdentityLabel() {
    _checkRuntime();
    return SyntheticIdentityLabel(value: 'alpha-synthetic:${_hex()}');
  }

  String createRequestKey() {
    _checkRuntime();
    final key = _hex();
    // 由正式 validator 校验，不持第二套语法。
    BeginSyntheticChallenge(identity: createIdentityLabel(), requestKey: key);
    return key;
  }

  Map<String, Map<String, Object?>> _rows(String table) =>
      _store.records.putIfAbsent(table, () => <String, Map<String, Object?>>{});

  Future<T> _transaction<T>(Future<T> Function() action) async {
    _checkRuntime();
    final fence = _store.captureFence('synthetic');
    void check() {
      _checkRuntime();
      fence();
    }

    try {
      return await _store.commit(action, beforeCommit: check);
    } on SyntheticLoginFailure {
      rethrow;
    } catch (_) {
      _checkRuntime();
      _fail(SyntheticLoginFailureReason.storageunavailable);
    }
  }

  @override
  Future<SyntheticChallengeView> begin(BeginSyntheticChallenge command) =>
      _transaction(() async {
        final input = BeginSyntheticChallenge.fromWire(command.toWire());
        final requests = _rows('synthetic.begin');
        final challenges = _rows('synthetic.challenges');
        final existing = requests[input.requestKey];
        if (existing != null) {
          if (existing['identity'] != input.identity.value) {
            _fail(SyntheticLoginFailureReason.conflict);
          }
          final row = challenges[existing['challengeId']];
          if (row == null) {
            _fail(SyntheticLoginFailureReason.storageunavailable);
          }
          _active(row);
          return _view(row);
        }
        final view = SyntheticChallengeView(
          challengeId: 'alpha-challenge:${_hex()}',
          confirmationHint: 'alpha-rehearsal-confirm',
          expiresInSeconds: 300,
        );
        if (challenges.containsKey(view.challengeId)) {
          _fail(SyntheticLoginFailureReason.conflict);
        }
        final row = <String, Object?>{
          'identity': input.identity.value,
          'challengeId': view.challengeId,
          'confirmationHint': view.confirmationHint,
          'expiresAt': _now()
              .toUtc()
              .add(const Duration(seconds: 300))
              .toIso8601String(),
          'attempts': 0,
          'used': false,
        };
        challenges[view.challengeId] = row;
        requests[input.requestKey] = {
          'identity': input.identity.value,
          'challengeId': view.challengeId,
        };
        _event('synthetic.begin');
        return SyntheticChallengeView.fromWire(view.toWire());
      });

  @override
  Future<SyntheticSessionResult> complete(
    CompleteSyntheticChallenge command,
  ) async {
    final outcome = await _transaction<Object>(() async {
      final input = CompleteSyntheticChallenge.fromWire(command.toWire());
      final fingerprint = jsonEncode(input.toWire());
      final requests = _rows('synthetic.complete');
      final prior = requests[input.requestKey];
      if (prior != null) {
        if (prior['input'] != fingerprint) {
          _fail(SyntheticLoginFailureReason.conflict);
        }
        if (prior['failure'] != null) {
          return SyntheticLoginFailure.fromWire(
            Map<String, Object?>.from(prior['failure'] as Map),
          );
        }
        return SyntheticSessionResult.fromWire(
          Map<String, Object?>.from(prior['result'] as Map),
        );
      }
      final row = _rows('synthetic.challenges')[input.challengeId];
      if (row == null) _fail(SyntheticLoginFailureReason.mismatch);
      _active(row);
      // 格式校验不等于挑战匹配；即使生成器允许合法 reject 也必须走失败事务。
      if (row['identity'] != input.identityLabel ||
          row['confirmationHint'] != input.confirmationHint) {
        row['attempts'] = (row['attempts'] as int) + 1;
        final failure = SyntheticLoginFailure(
          reason: (row['attempts'] as int) >= 5
              ? SyntheticLoginFailureReason.attemptsexceeded
              : SyntheticLoginFailureReason.mismatch,
        );
        requests[input.requestKey] = {
          'input': fingerprint,
          'failure': failure.toWire(),
        };
        return failure;
      }
      final existing = _identityOwner.syntheticSession(input.identityLabel);
      final result =
          existing ??
          SyntheticSessionResult(
            accountId: 'alpha-account:${_hex()}',
            personaId: 'alpha-persona:${_hex()}',
          );
      final validated = SyntheticSessionResult.fromWire(result.toWire());
      _identityOwner.recordSyntheticSession(input.identityLabel, validated);
      row['used'] = true;
      requests[input.requestKey] = {
        'input': fingerprint,
        'result': validated.toWire(),
      };
      _rows('synthetic.session')['active'] = validated.toWire();
      _event('synthetic.complete');
      return validated;
    });
    if (outcome is SyntheticLoginFailure) throw outcome;
    return outcome as SyntheticSessionResult;
  }

  Future<SyntheticSessionResult?> restore() => _transaction(() async {
    final active = _store.records['synthetic.session']?['active'];
    return active == null ? null : SyntheticSessionResult.fromWire(active);
  });

  void _active(Map<String, Object?> row) {
    if (!_now().isBefore(DateTime.parse(row['expiresAt'] as String))) {
      _fail(SyntheticLoginFailureReason.expired);
    }
    if ((row['attempts'] as int) >= 5) {
      _fail(SyntheticLoginFailureReason.attemptsexceeded);
    }
    if (row['used'] == true) _fail(SyntheticLoginFailureReason.conflict);
  }

  SyntheticChallengeView _view(Map<String, Object?> row) {
    final remaining = DateTime.parse(row['expiresAt'] as String)
        .difference(_now())
        .inMilliseconds;
    return SyntheticChallengeView(
      challengeId: row['challengeId'] as String,
      confirmationHint: row['confirmationHint'] as String,
      expiresInSeconds: ((remaining + 999) ~/ 1000).clamp(1, 300),
    );
  }

  void _event(String operation) => _store.events.add({
    'eventId': _store.nextId('event_'),
    'operation': operation,
    'spaceGeneration': _store.spaceGeneration,
  });

  Never _fail(SyntheticLoginFailureReason reason) =>
      throw SyntheticLoginFailure(reason: reason);
}
