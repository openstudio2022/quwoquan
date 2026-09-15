import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/runtime/config/generated/app_launch_contract.g.dart';
import 'package:quwoquan_app/runtime/config/rehearsal_storage_namespace.dart';
import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';

/// 纯内存观察器；所有 current 回调必须是实际 owner 的无 I/O 查询。
/// 不签发资格，不发送日志。未接实际启动 attempt/generation 时保持 unavailable。
final class RehearsalStorageObserver {
  RehearsalStorageObserver({
    required this.space,
    required this.currentSpace,
    required this.startupAttemptId,
    required this.generation,
    required this.currentStartupAttemptId,
    required this.currentGeneration,
  }) : _namespace = RehearsalStorageNamespace(space) {
    if (startupAttemptId != null && generation != null) {
      _bindingDigest = _digest([
        _domains['binding'],
        startupAttemptId,
        generation,
        space.snapshotDigest,
        space.instanceId,
      ]);
      // 输入语法及跨字段关系只由正式 generated validator 校验。
      _snapshot(available: true);
    }
  }

  final VerifiedRehearsalSpace space;
  final VerifiedRehearsalSpace? Function() currentSpace;
  final String? startupAttemptId;
  final String? generation;
  final String? Function() currentStartupAttemptId;
  final String? Function() currentGeneration;
  final RehearsalStorageNamespace _namespace;
  String _bindingDigest = '';
  bool _invalidated = false;
  final Map<String, RehearsalConsumerObserver> _consumers = {};
  static final Map<String, dynamic> _contract =
      jsonDecode(appLaunchManifestJson) as Map<String, dynamic>;
  static Map get _observationContract =>
      _contract['rehearsal_storage_readback'] as Map;
  static Map get _domains => _observationContract['digest_domains'] as Map;
  static Iterable<String> get _names =>
      (((_contract['schemas'] as Map)['rehearsal_storage_observation']
                  as Map)['fields']
              as Map)['consumers']['required_fields']
          .cast<String>();
  static String _digest(List<Object?> input) =>
      'sha256:${sha256.convert(utf8.encode(canonicalJsonEncode(input)))}';

  void requireCurrent() {
    try {
      if (_invalidated) throw StateError('invalidated');
      _namespace.requireCurrent(currentSpace());
      if (currentStartupAttemptId() != startupAttemptId ||
          currentGeneration() != generation) {
        throw StateError('generation changed');
      }
    } catch (_) {
      invalidate();
      throw contentCapabilityUnavailable('rehearsal_observation_invalidated');
    }
  }

  /// consumer owner 构造实际 namespace 后调用；重复同名实例必须先失效旧实例。
  RehearsalConsumerObserver attach(
    String consumer,
    RehearsalStorageNamespace actualNamespace,
  ) {
    requireCurrent();
    actualNamespace.requireCurrent(space);
    if (!_names.contains(consumer)) {
      throw ArgumentError('Unknown storage consumer');
    }
    if (_consumers[consumer] case final previous?) {
      if (!previous._invalidated) {
        throw StateError('Storage consumer already attached');
      }
    }
    final result = RehearsalConsumerObserver._(this, consumer);
    _consumers[consumer] = result;
    return result;
  }

  void invalidate() {
    _invalidated = true;
    _bindingDigest = '';
    for (final consumer in _consumers.values) {
      consumer.invalidate();
    }
  }

  RehearsalStorageObservation read() {
    try {
      requireCurrent();
    } catch (_) {
      /* 只返回失效投影，不触发恢复。 */
    }
    return _snapshot(available: !_invalidated && _bindingDigest.isNotEmpty);
  }

  RehearsalStorageObservation _snapshot({required bool available}) =>
      RehearsalStorageObservation.fromWire({
        'schema': runtimeDocumentSchemaValues['rehearsal_storage_observation'],
        'status':
            (available
                    ? RehearsalObservationStatus.available
                    : RehearsalObservationStatus.unavailable)
                .wireName,
        'configurationState':
            (_invalidated
                    ? RehearsalConfigurationObservationState.invalidated
                    : RehearsalConfigurationObservationState.verified)
                .wireName,
        'startupAttemptId': available ? startupAttemptId : '',
        'generation': available ? generation : '',
        'bindingDigest': available ? _bindingDigest : '',
        'consumers': {
          for (final name in _names) name: _consumer(name, available).toWire(),
        },
      });

  RehearsalConsumerObservation _consumer(String name, bool available) {
    final consumer = _consumers[name];
    final invalid = _invalidated || consumer?._invalidated == true;
    final live = available && consumer != null && !invalid;
    final operations = live
        ? consumer._operations.toList()
        : <RehearsalSuccessfulOperation>[];
    return RehearsalConsumerObservation.fromWire({
      'state':
          (invalid
                  ? RehearsalConsumerObservationState.invalidated
                  : !live
                  ? RehearsalConsumerObservationState.notObserved
                  : operations.isEmpty
                  ? RehearsalConsumerObservationState.constructed
                  : RehearsalConsumerObservationState.ioObserved)
              .wireName,
      'namespaceDigest': live
          ? _digest([_domains['namespace'], _bindingDigest, name])
          : '',
      'successfulOperations': operations.map((o) => o.wireName).toList(),
    });
  }
}

/// 真实 consumer 实例的记录句柄，不保存任何 key/path/payload。
final class RehearsalConsumerObserver {
  RehearsalConsumerObserver._(this._owner, this.consumer);
  final RehearsalStorageObserver _owner;
  final String consumer;
  bool _invalidated = false;
  final Set<RehearsalSuccessfulOperation> _operations = {};
  void requireCurrent() {
    _owner.requireCurrent();
    if (_invalidated) {
      throw contentCapabilityUnavailable('rehearsal_consumer_invalidated');
    }
  }

  void requireNamespace(String snapshot, String instance) {
    requireCurrent();
    if (snapshot != _owner.space.snapshotDigest ||
        instance != _owner.space.instanceId) {
      throw contentCapabilityUnavailable('rehearsal_space_binding');
    }
  }

  /// 只可在真实操作完成后调用；调用方额外 fence 必须无 I/O。
  void recordSuccess(
    RehearsalSuccessfulOperation operation, {
    void Function()? fence,
  }) {
    fence?.call();
    requireCurrent();
    _operations.add(operation);
  }

  void invalidate() {
    _invalidated = true;
    _operations.clear();
  }

  RehearsalConsumerObservation read() {
    if (_invalidated) {
      return RehearsalConsumerObservation.fromWire({
        'state': RehearsalConsumerObservationState.invalidated.wireName,
        'namespaceDigest': '',
        'successfulOperations': <String>[],
      });
    }
    final observation = _owner.read();
    return RehearsalConsumerObservation.fromWire(
      (observation.toWire()['consumers'] as Map)[consumer],
    );
  }
}
