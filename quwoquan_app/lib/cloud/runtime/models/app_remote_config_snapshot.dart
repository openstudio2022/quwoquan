import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

enum AppRemoteConfigSource { defaults, diskCache, networkFresh, staleDiskCache }

class AppRemoteConfigSnapshot {
  const AppRemoteConfigSnapshot._({
    required this.schema,
    required this.configHash,
    required this.fetchedAt,
    required this.maxAge,
    required this.wire,
    required this.source,
  });

  static const String canonicalSchema = 'app_remote_config';
  static const Duration fallbackMaxAge = Duration(hours: 6);

  final String schema;
  final String configHash;
  final DateTime fetchedAt;
  final Duration maxAge;
  final AppConfigSlice wire;
  final AppRemoteConfigSource source;

  bool get isExpired => DateTime.now().toUtc().isAfter(expiresAt);

  DateTime get expiresAt => fetchedAt.toUtc().add(maxAge);

  ContentAppConfig get content => wire.content;

  String get defaultActivation => wire.activationPolicy.defaultActivation;

  factory AppRemoteConfigSnapshot.fromWire(
    AppConfigSlice wire, {
    AppRemoteConfigSource source = AppRemoteConfigSource.networkFresh,
  }) {
    if (wire.schema != canonicalSchema) {
      throw FormatException('unsupported app config schema: ${wire.schema}');
    }
    final root = wire.toWire();
    final expectedHash = calculateConfigHash(root);
    if (!_sha256Pattern.hasMatch(wire.configHash) ||
        wire.configHash != expectedHash) {
      throw const FormatException('configHash mismatch');
    }
    return AppRemoteConfigSnapshot._(
      schema: wire.schema,
      configHash: wire.configHash,
      fetchedAt: wire.fetchedAt,
      maxAge: Duration(seconds: wire.maxAgeSec),
      wire: wire,
      source: source,
    );
  }

  factory AppRemoteConfigSnapshot.fromRoot(
    Map<String, Object?> root, {
    AppRemoteConfigSource source = AppRemoteConfigSource.networkFresh,
  }) {
    return AppRemoteConfigSnapshot.fromWire(
      AppConfigSlice.fromWire(root),
      source: source,
    );
  }

  Map<String, dynamic> toPersistedMap() {
    return Map<String, dynamic>.from(wire.toWire());
  }

  factory AppRemoteConfigSnapshot.fromPersistedMap(
    Map<String, dynamic> map, {
    AppRemoteConfigSource source = AppRemoteConfigSource.diskCache,
  }) {
    return AppRemoteConfigSnapshot.fromRoot(
      Map<String, Object?>.from(map),
      source: source,
    );
  }

  static final RegExp _sha256Pattern = RegExp(r'^sha256:[0-9a-f]{64}$');

  static String calculateConfigHash(Map<String, Object?> root) {
    final canonicalRoot = <String, Object?>{
      for (final entry in root.entries)
        if (entry.key != 'configHash' && entry.key != 'fetchedAt')
          entry.key: entry.value,
    };
    final payload = jsonEncode(_normalizeJson(canonicalRoot));
    return 'sha256:${sha256.convert(utf8.encode(payload))}';
  }

  static Object? _normalizeJson(Object? value) {
    if (value is Map) {
      final entries = value.entries.toList()
        ..sort((a, b) => a.key.toString().compareTo(b.key.toString()));
      return <String, Object?>{
        for (final entry in entries)
          entry.key.toString(): _normalizeJson(entry.value),
      };
    }
    if (value is List) {
      return value.map(_normalizeJson).toList(growable: false);
    }
    return value;
  }
}
