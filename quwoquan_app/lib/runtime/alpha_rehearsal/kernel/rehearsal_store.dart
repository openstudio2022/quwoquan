import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:quwoquan_app/runtime/config/generated/offline_content_bundle_identity.g.dart';
import 'package:quwoquan_app/runtime/config/generated/app_launch_contract.g.dart';
import 'package:quwoquan_app/runtime/config/rehearsal_storage_observer.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_space_binding.dart';
import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';
import 'package:quwoquan_app/runtime/errors/local_domain_failure.dart';
import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const int rehearsalStoreFormatVersion = 1;
const String rehearsalDefaultInstanceId = 'default';

abstract interface class RehearsalPersistence {
  Future<String?> read();

  /// 必须在唯一原子提交点之前执行 fence，不得先改变 active 字节。
  Future<void> write(String contents, {void Function()? beforeCommit});
}

final class MemoryRehearsalPersistence implements RehearsalPersistence {
  String? value;
  @override
  Future<String?> read() async => value;
  @override
  Future<void> write(String contents, {void Function()? beforeCommit}) async {
    beforeCommit?.call();
    value = contents;
  }
}

final class FileRehearsalPersistence implements RehearsalPersistence {
  FileRehearsalPersistence({
    required this.gateway,
    required this.snapshotDigest,
    this.instanceId = rehearsalDefaultInstanceId,
  }) : observation = null;
  FileRehearsalPersistence.bound({
    required this.gateway,
    required RehearsalSpaceBinding binding,
    this.observation,
  }) : snapshotDigest = binding.snapshotDigest,
       instanceId = binding.instanceId {
    observation?.requireNamespace(snapshotDigest, instanceId);
    if (observation != null && observation!.consumer != 'rehearsal') {
      throw contentCapabilityUnavailable('rehearsal_observation_consumer');
    }
  }

  final RehearsalConsumerObserver? observation;

  final FileStorageGateway gateway;
  final String snapshotDigest;
  final String instanceId;
  Future<String> _filePath() async {
    if (!RegExp(r'^[a-zA-Z0-9_-]+$').hasMatch(instanceId) ||
        !RegExp(r'^[a-zA-Z0-9:_-]+$').hasMatch(snapshotDigest)) {
      throw const FormatException('Invalid rehearsal namespace');
    }
    observation?.requireCurrent();
    final root = await gateway.applicationSupportPath();
    observation?.requireCurrent();
    final dir = '$root/alpha_rehearsal';
    await gateway.ensureDirectory(dir);
    observation?.requireCurrent();
    return '$dir/${snapshotDigest.replaceAll(':', '_')}_$instanceId.json';
  }

  @override
  Future<String?> read() async {
    final path = await _filePath();
    final exists = await gateway.exists(path);
    observation?.requireCurrent();
    // 本实现缺文件只有 exists 观察，不冒充 payload read；secure read(null)由其owner记录。
    if (!exists) return null;
    final contents = await gateway.readAsString(path);
    observation?.recordSuccess(RehearsalSuccessfulOperation.read);
    return contents;
  }

  @override
  Future<void> write(String contents, {void Function()? beforeCommit}) async {
    final atomic = gateway;
    if (atomic is! AtomicFileStorageGateway) {
      throw localDomainCloudException('CONTENT.SYSTEM.storage_write_failed');
    }
    await (atomic as AtomicFileStorageGateway).writeAsStringAtomically(
      await _filePath(),
      contents,
      beforeCommit: () {
        beforeCommit?.call();
        observation?.requireCurrent();
      },
    );
    observation?.recordSuccess(
      RehearsalSuccessfulOperation.write,
      fence: beforeCommit,
    );
  }
}

final class AlphaRehearsalStore {
  AlphaRehearsalStore({
    RehearsalPersistence? persistence,
    this.snapshotDigest = offlineContentManifestDigest,
    this.instanceId = rehearsalDefaultInstanceId,
    DateTime Function()? now,
    this.idFactory,
  }) : persistence = persistence ?? MemoryRehearsalPersistence() {
    final selected = this.persistence;
    if (selected is FileRehearsalPersistence &&
        (selected.snapshotDigest != snapshotDigest ||
            selected.instanceId != instanceId)) {
      throw contentCapabilityUnavailable('rehearsal_space_binding');
    }
    _committed = _empty();
  }

  factory AlphaRehearsalStore.bound({
    required RehearsalSpaceBinding binding,
    required FileStorageGateway gateway,
    RehearsalConsumerObserver? observation,
  }) => AlphaRehearsalStore(
    snapshotDigest: binding.snapshotDigest,
    instanceId: binding.instanceId,
    persistence: FileRehearsalPersistence.bound(
      gateway: gateway,
      binding: binding,
      observation: observation,
    ),
  );

  final RehearsalPersistence persistence;
  final String snapshotDigest;
  final String instanceId;
  // 工厂供确定性回归使用，持久身份默认使用安全随机 ID。
  final String Function()? idFactory;
  final Random _random = Random.secure();
  bool _loaded = false;
  Future<void> _queue = Future<void>.value();
  late Map<String, dynamic> _committed;
  int _spaceFence = 0;
  final Map<String, int> _actorFences = {};
  Map<String, dynamic> get _state =>
      (Zone.current[this] as Map<String, dynamic>?) ?? _committed;
  static const _tables = [
    'follows',
    'blocks',
    'reactions',
    'comments',
    'conversations',
    'messages',
    'identities',
    'otpChallenges',
    'assistantSessions',
    'assistantRuns',
    'searchHistory',
    'callSessions',
    'idempotency',
  ];
  Map<String, dynamic> _empty() => {
    'formatVersion': rehearsalStoreFormatVersion,
    'snapshotDigest': snapshotDigest,
    'instanceId': instanceId,
    'spaceGeneration': 0,
    'currentOwnerId': null,
    'currentPersonaId': null,
    'lastIssuedOtp': null,
    'records': <String, Map<String, Map<String, Object?>>>{},
    for (final key in _tables) key: <String, Map<String, Object?>>{},
    'events': <Map<String, Object?>>[],
    'actorGenerations': <String, int>{},
  };
  Map<String, Map<String, Object?>> _table(String key) =>
      _state[key] as Map<String, Map<String, Object?>>;
  Map<String, Map<String, Map<String, Object?>>> get records =>
      _state['records'] as Map<String, Map<String, Map<String, Object?>>>;
  Map<String, Map<String, Object?>> get follows => _table('follows');
  Map<String, Map<String, Object?>> get blocks => _table('blocks');
  Map<String, Map<String, Object?>> get reactions => _table('reactions');
  Map<String, Map<String, Object?>> get comments => _table('comments');
  Map<String, Map<String, Object?>> get conversations =>
      _table('conversations');
  Map<String, Map<String, Object?>> get messages => _table('messages');
  Map<String, Map<String, Object?>> get identities => _table('identities');
  Map<String, Map<String, Object?>> get otpChallenges =>
      _table('otpChallenges');
  Map<String, Map<String, Object?>> get assistantSessions =>
      _table('assistantSessions');
  Map<String, Map<String, Object?>> get assistantRuns =>
      _table('assistantRuns');
  Map<String, Map<String, Object?>> get searchHistory =>
      _table('searchHistory');
  Map<String, Map<String, Object?>> get callSessions => _table('callSessions');
  Map<String, Map<String, Object?>> get idempotency => _table('idempotency');
  List<Map<String, Object?>> get events =>
      _state['events'] as List<Map<String, Object?>>;
  Map<String, int> get actorGenerations =>
      _state['actorGenerations'] as Map<String, int>;
  int get spaceGeneration => _state['spaceGeneration'] as int;
  set spaceGeneration(int value) => _state['spaceGeneration'] = value;
  String? get currentOwnerId => _state['currentOwnerId'] as String?;
  set currentOwnerId(String? value) => _state['currentOwnerId'] = value;
  String? get currentPersonaId => _state['currentPersonaId'] as String?;
  set currentPersonaId(String? value) => _state['currentPersonaId'] = value;
  String? get lastIssuedOtp => _state['lastIssuedOtp'] as String?;
  set lastIssuedOtp(String? value) => _state['lastIssuedOtp'] = value;

  Future<void> ensureLoaded() => _serialized(_loadIfNeeded);
  Future<void> _loadIfNeeded() async {
    if (_loaded) return;
    try {
      final raw = await persistence.read();
      if (raw != null) _committed = _decode(raw);
      _loaded = true;
    } catch (_) {
      throw localDomainCloudException('CONTENT.SYSTEM.storage_write_failed');
    }
  }

  Map<String, dynamic> _decode(String raw) {
    final json = jsonDecode(raw) as Map<String, dynamic>;
    final expected = _empty().keys.toSet();
    if (json.keys.toSet().difference(expected).isNotEmpty ||
        expected.difference(json.keys.toSet()).isNotEmpty ||
        json['formatVersion'] != rehearsalStoreFormatVersion ||
        json['snapshotDigest'] != snapshotDigest ||
        json['instanceId'] != instanceId ||
        json['spaceGeneration'] is! int ||
        (json['spaceGeneration'] as int) < 0) {
      throw const FormatException('Invalid rehearsal envelope');
    }
    for (final key in ['currentOwnerId', 'currentPersonaId', 'lastIssuedOtp']) {
      if (json[key] != null && json[key] is! String) {
        throw const FormatException('Invalid identity');
      }
    }
    for (final key in _tables) {
      json[key] = (json[key] as Map).map(
        (k, v) => MapEntry(k as String, Map<String, Object?>.from(v as Map)),
      );
    }
    json['records'] = (json['records'] as Map).map(
      (k, v) => MapEntry(
        k as String,
        (v as Map).map(
          (a, b) => MapEntry(a as String, Map<String, Object?>.from(b as Map)),
        ),
      ),
    );
    json['events'] = (json['events'] as List)
        .map((e) => Map<String, Object?>.from(e as Map))
        .toList();
    json['actorGenerations'] = (json['actorGenerations'] as Map).map(
      (k, v) => MapEntry(k as String, v as int),
    );
    return json;
  }

  String nextId(String prefix) =>
      '$prefix${idFactory?.call() ?? List.generate(16, (_) => _random.nextInt(256).toRadixString(16).padLeft(2, '0')).join()}';
  Map<String, Object?>? idempotentResponse(String? key) =>
      key == null ? null : idempotency[key];

  void Function() captureFence(String actor) {
    final space = _spaceFence;
    final generation = _actorFences[actor] ?? 0;
    return () {
      if (space != _spaceFence || generation != (_actorFences[actor] ?? 0)) {
        throw const CloudOperationCancelledException();
      }
    };
  }

  Future<T> commit<T>(
    FutureOr<T> Function() mutate, {
    void Function()? beforeCommit,
  }) {
    if (Zone.current[this] != null) return Future<T>.sync(mutate);
    return _serialized(() async {
      await _loadIfNeeded();
      beforeCommit?.call();
      final draft = _decode(jsonEncode(_committed));
      return runZoned(() async {
        final result = await mutate();
        final encoded = jsonEncode(draft);
        final validated = _decode(encoded);
        if (encoded != jsonEncode(_committed)) {
          try {
            await persistence.write(encoded, beforeCommit: beforeCommit);
          } on CloudOperationCancelledException {
            rethrow;
          } on TimeoutException {
            rethrow;
          } catch (_) {
            throw localDomainCloudException(
              'CONTENT.SYSTEM.storage_write_failed',
            );
          }
          _committed = validated;
        } else {
          beforeCommit?.call();
        }
        return result;
      }, zoneValues: {this: draft});
    });
  }

  Future<void> resetActor(String actorId) {
    final identity = identities[actorId];
    final actors = {
      actorId,
      if (identity?['personaId'] is String) identity!['personaId'] as String,
    };
    for (final actor in actors) {
      _actorFences[actor] = (_actorFences[actor] ?? 0) + 1;
    }
    return commit(() {
      for (final actor in actors) {
        actorGenerations[actor] = (actorGenerations[actor] ?? 0) + 1;
        searchHistory.removeWhere((_, row) => row['actorId'] == actor);
        idempotency.removeWhere(
          (key, _) => (jsonDecode(key) as List).first == actor,
        );
        assistantRuns.removeWhere((_, row) => row['userId'] == actor);
        assistantSessions.removeWhere((_, row) => row['userId'] == actor);
      }
      identities.remove(actorId);
      otpChallenges.removeWhere((_, row) => actors.contains(row['owner']));
      if (actors.contains(currentOwnerId) ||
          actors.contains(currentPersonaId)) {
        currentOwnerId = null;
        currentPersonaId = null;
      }
    });
  }

  Future<void> resetSpace() {
    _spaceFence += 1;
    return commit(() {
      final next = spaceGeneration + 1;
      _state
        ..clear()
        ..addAll(_empty());
      spaceGeneration = next;
    });
  }

  String followKey(String actor, String target) => '$actor::$target';
  String reactionKey(String actor, String postId) => '$actor::$postId';
  List<String> followingOf(String actor) => follows.values
      .where((row) => row['actorPersonaId'] == actor && row['active'] == true)
      .map((row) => '${row['targetPersonaId']}')
      .toList();
  Future<T> _serialized<T>(Future<T> Function() action) {
    final next = _queue.then((_) => action());
    _queue = next.then<void>((_) {}, onError: (_) {});
    return next;
  }
}
