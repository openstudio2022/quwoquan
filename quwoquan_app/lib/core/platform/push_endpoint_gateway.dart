import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:uuid/uuid.dart';

enum PushEndpointKind {
  apnsVoip('apns_voip'),
  fcm('fcm');

  const PushEndpointKind(this.wireName);

  final String wireName;

  static PushEndpointKind? fromWire(String value) {
    for (final candidate in values) {
      if (candidate.wireName == value) {
        return candidate;
      }
    }
    return null;
  }
}

enum PushEndpointMutationKind {
  upsert('upsert'),
  remove('remove');

  const PushEndpointMutationKind(this.wireName);

  final String wireName;

  static PushEndpointMutationKind? fromWire(String value) {
    for (final candidate in values) {
      if (candidate.wireName == value) {
        return candidate;
      }
    }
    return null;
  }
}

@immutable
final class DevicePushEndpoint {
  DevicePushEndpoint({required this.kind, required String token})
    : token = _validateToken(token);

  final PushEndpointKind kind;
  final String token;

  static String _validateToken(String value) {
    final normalized = value.trim();
    if (normalized.isEmpty || normalized.length > 4096) {
      throw const FormatException('push endpoint token is invalid');
    }
    return normalized;
  }

  @override
  bool operator ==(Object other) =>
      other is DevicePushEndpoint && other.kind == kind && other.token == token;

  @override
  int get hashCode => Object.hash(kind, token);
}

@immutable
final class PushEndpointMutation {
  const PushEndpointMutation({
    required this.mutationId,
    required this.kind,
    required this.endpoint,
    required this.occurredAt,
  });

  final String mutationId;
  final PushEndpointMutationKind kind;
  final DevicePushEndpoint endpoint;
  final DateTime occurredAt;

  Map<String, Object> toMap() => <String, Object>{
    'mutationId': mutationId,
    'action': kind.wireName,
    'endpointKind': endpoint.kind.wireName,
    'token': endpoint.token,
    'occurredAt': occurredAt.toUtc().toIso8601String(),
  };

  static PushEndpointMutation? tryParse(Object? raw) {
    if (raw is! Map) {
      return null;
    }
    final mutationId = raw['mutationId']?.toString().trim() ?? '';
    final kind = PushEndpointMutationKind.fromWire(
      raw['action']?.toString().trim() ?? '',
    );
    final endpointKind = PushEndpointKind.fromWire(
      raw['endpointKind']?.toString().trim() ?? '',
    );
    final token = raw['token']?.toString().trim() ?? '';
    final occurredAt = DateTime.tryParse(
      raw['occurredAt']?.toString() ?? '',
    )?.toUtc();
    if (mutationId.isEmpty ||
        kind == null ||
        endpointKind == null ||
        token.isEmpty ||
        occurredAt == null) {
      return null;
    }
    try {
      return PushEndpointMutation(
        mutationId: mutationId,
        kind: kind,
        endpoint: DevicePushEndpoint(kind: endpointKind, token: token),
        occurredAt: occurredAt,
      );
    } on FormatException {
      return null;
    }
  }
}

abstract interface class PushEndpointGateway {
  Future<void> recordUpsert(DevicePushEndpoint endpoint);

  Future<List<PushEndpointMutation>> readPendingMutations();

  Future<void> acknowledgeMutation(String mutationId);

  /// 登出前把全部当前 endpoint 转为 remove mutation；远端成功前不得丢弃。
  Future<void> queueActiveEndpointRemovals();

  /// 云侧账号 closed 后物理清除本地与原生 push/来电身份残留。
  Future<void> purgeForTerminalAccountClosure();
}

abstract interface class PushEndpointSecretStore {
  Future<String?> read(String key);

  Future<void> write(String key, String value);

  Future<void> delete(String key);
}

final class FlutterSecurePushEndpointSecretStore
    implements PushEndpointSecretStore {
  const FlutterSecurePushEndpointSecretStore({
    this.storage = const FlutterSecureStorage(),
  });

  final FlutterSecureStorage storage;

  @override
  Future<String?> read(String key) => storage.read(key: key);

  @override
  Future<void> write(String key, String value) =>
      storage.write(key: key, value: value);

  @override
  Future<void> delete(String key) => storage.delete(key: key);
}

/// FCM token 与待同步 mutation 只进入平台安全存储；iOS VoIP token mutation
/// 由同一 MethodChannel 从原生 Keychain 合并读取。两侧都只在远端 writer 成功后 ack。
final class PersistentPushEndpointGateway implements PushEndpointGateway {
  PersistentPushEndpointGateway({
    PushEndpointSecretStore secretStore =
        const FlutterSecurePushEndpointSecretStore(),
    MethodChannel channel = const MethodChannel('quwoquan/rtc/incoming_call'),
  }) : this._withDependencies(secretStore, channel);

  PersistentPushEndpointGateway._withDependencies(
    this._secretStore,
    this.channel,
  );

  static const _pendingKey = 'rtc.push_endpoint.pending_mutations';
  static const _activeKey = 'rtc.push_endpoint.active_tokens';
  static const _maxPendingMutations = 32;

  final PushEndpointSecretStore _secretStore;
  final MethodChannel channel;
  Future<void> _operationTail = Future<void>.value();

  @override
  Future<void> recordUpsert(DevicePushEndpoint endpoint) =>
      _serial<void>(() async {
        final active = await _readActive();
        if (active[endpoint.kind.wireName] == endpoint.token) {
          return;
        }
        active[endpoint.kind.wireName] = endpoint.token;
        await _secretStore.write(_activeKey, jsonEncode(active));
        await _appendLocalMutation(
          PushEndpointMutation(
            mutationId: const Uuid().v4(),
            kind: PushEndpointMutationKind.upsert,
            endpoint: endpoint,
            occurredAt: DateTime.now().toUtc(),
          ),
        );
      });

  @override
  Future<List<PushEndpointMutation>> readPendingMutations() =>
      _serial<List<PushEndpointMutation>>(() async {
        final merged = <String, PushEndpointMutation>{};
        for (final mutation in await _readLocalMutations()) {
          merged[mutation.mutationId] = mutation;
        }
        try {
          final raw = await channel.invokeMethod<Object?>(
            'readPushEndpointMutations',
          );
          if (raw is List) {
            for (final item in raw) {
              final mutation = PushEndpointMutation.tryParse(item);
              if (mutation != null) {
                merged[mutation.mutationId] = mutation;
              }
            }
          }
        } on MissingPluginException {
          // Android 的 FCM queue 已由本地安全存储覆盖。
        } on PlatformException {
          // 保留本地 mutation，下一次登录继续重试。
        }
        final mutations = merged.values.toList(growable: false)
          ..sort((left, right) => left.occurredAt.compareTo(right.occurredAt));
        return List<PushEndpointMutation>.unmodifiable(mutations);
      });

  @override
  Future<void> acknowledgeMutation(String mutationId) =>
      _serial<void>(() async {
        final normalized = mutationId.trim();
        if (normalized.isEmpty) {
          return;
        }
        final remaining = (await _readLocalMutations())
            .where((entry) => entry.mutationId != normalized)
            .toList(growable: false);
        await _writeLocalMutations(remaining);
        try {
          await channel.invokeMethod<void>(
            'ackPushEndpointMutation',
            <String, Object>{'mutationId': normalized},
          );
        } on MissingPluginException {
          return;
        } on PlatformException {
          return;
        }
      });

  @override
  Future<void> queueActiveEndpointRemovals() => _serial<void>(() async {
    final active = await _readActive();
    for (final entry in active.entries) {
      final kind = PushEndpointKind.fromWire(entry.key);
      if (kind == null || entry.value.trim().isEmpty) {
        continue;
      }
      await _appendLocalMutation(
        PushEndpointMutation(
          mutationId: const Uuid().v4(),
          kind: PushEndpointMutationKind.remove,
          endpoint: DevicePushEndpoint(kind: kind, token: entry.value),
          occurredAt: DateTime.now().toUtc(),
        ),
      );
    }
    await _secretStore.delete(_activeKey);
    try {
      await channel.invokeMethod<void>('queueActivePushEndpointRemovals');
    } on MissingPluginException {
      return;
    } on PlatformException {
      return;
    }
  });

  @override
  Future<void> purgeForTerminalAccountClosure() => _serial<void>(() async {
    await _secretStore.delete(_pendingKey);
    await _secretStore.delete(_activeKey);
    try {
      final purged = await channel.invokeMethod<bool>(
        'purgePushEndpointStateForTerminalAccountClosure',
      );
      if (purged != true) {
        throw StateError('native push endpoint cleanup was not acknowledged');
      }
    } on MissingPluginException {
      // 当前平台没有原生来电状态；安全存储仍必须完成清理。
    }
    if (await _secretStore.read(_pendingKey) != null ||
        await _secretStore.read(_activeKey) != null) {
      throw StateError('push endpoint cleanup verification failed');
    }
  });

  Future<void> _appendLocalMutation(PushEndpointMutation mutation) async {
    final pending = (await _readLocalMutations())
      ..removeWhere(
        (entry) =>
            entry.kind == mutation.kind && entry.endpoint == mutation.endpoint,
      )
      ..add(mutation);
    if (pending.length > _maxPendingMutations) {
      pending.removeRange(0, pending.length - _maxPendingMutations);
    }
    await _writeLocalMutations(pending);
  }

  Future<List<PushEndpointMutation>> _readLocalMutations() async {
    return _decodeMutations(await _secretStore.read(_pendingKey));
  }

  List<PushEndpointMutation> _decodeMutations(String? encoded) {
    if (encoded == null || encoded.isEmpty) {
      return <PushEndpointMutation>[];
    }
    try {
      final raw = jsonDecode(encoded);
      if (raw is! List) {
        return <PushEndpointMutation>[];
      }
      final parsed = <PushEndpointMutation>[];
      for (final item in raw) {
        final mutation = PushEndpointMutation.tryParse(item);
        if (mutation != null) {
          parsed.add(mutation);
        }
      }
      return parsed;
    } on FormatException {
      return <PushEndpointMutation>[];
    }
  }

  Future<void> _writeLocalMutations(
    List<PushEndpointMutation> mutations,
  ) async {
    if (mutations.isEmpty) {
      await _secretStore.delete(_pendingKey);
      return;
    }
    await _secretStore.write(
      _pendingKey,
      jsonEncode(mutations.map((entry) => entry.toMap()).toList()),
    );
  }

  Future<Map<String, String>> _readActive() async {
    return _decodeActive(await _secretStore.read(_activeKey));
  }

  Map<String, String> _decodeActive(String? encoded) {
    if (encoded == null || encoded.isEmpty) {
      return <String, String>{};
    }
    try {
      final raw = jsonDecode(encoded);
      if (raw is! Map) {
        return <String, String>{};
      }
      return raw.map(
        (key, value) => MapEntry(key.toString(), value.toString()),
      );
    } on FormatException {
      return <String, String>{};
    }
  }

  Future<T> _serial<T>(Future<T> Function() action) {
    final operation = _operationTail.then<T>((_) => action());
    _operationTail = operation.then<void>(
      (_) {},
      onError: (Object error, StackTrace stackTrace) {
        FlutterError.reportError(
          FlutterErrorDetails(
            exception: error,
            stack: stackTrace,
            library: 'push endpoint gateway',
            context: ErrorDescription(
              'while completing a serialized secure-storage operation',
            ),
          ),
        );
      },
    );
    return operation;
  }
}
