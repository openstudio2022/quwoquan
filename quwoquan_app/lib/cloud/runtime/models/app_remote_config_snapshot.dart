import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_app_config_wire.dart';

enum AppRemoteConfigSource { defaults, diskCache, networkFresh, staleDiskCache }

class AppRemoteConfigSnapshot {
  const AppRemoteConfigSnapshot._({
    required this.schema,
    required this.configHash,
    required this.fetchedAt,
    required this.maxAge,
    required this.activationPolicy,
    required this.wireRoot,
    required this.source,
  });

  static const String canonicalSchema = 'app_remote_config';
  static const Duration fallbackMaxAge = Duration(hours: 6);

  final String schema;
  final String configHash;
  final DateTime fetchedAt;
  final Duration maxAge;
  final Map<String, String> activationPolicy;
  final ContentAppConfigWireRoot wireRoot;
  final AppRemoteConfigSource source;

  bool get isExpired => DateTime.now().toUtc().isAfter(expiresAt);

  DateTime get expiresAt => fetchedAt.toUtc().add(maxAge);

  ContentAppConfigWire get contentWire =>
      ContentAppConfigWire.fromWireRoot(wireRoot);

  factory AppRemoteConfigSnapshot.defaults(ContentAppConfigWire wire) {
    final fetchedAt = DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);
    final root = <String, Object?>{
      ...wire.wireRoot,
      'schema': canonicalSchema,
      'fetchedAt': fetchedAt.toIso8601String(),
      'maxAgeSec': fallbackMaxAge.inSeconds,
      'activationPolicy': const <String, String>{
        'default': 'next_session',
        'kill_switches': 'immediate',
      },
    };
    final configHash = calculateConfigHash(root);
    root['configHash'] = configHash;
    return AppRemoteConfigSnapshot._(
      schema: canonicalSchema,
      configHash: configHash,
      fetchedAt: fetchedAt,
      maxAge: fallbackMaxAge,
      activationPolicy: const <String, String>{
        'default': 'next_session',
        'kill_switches': 'immediate',
      },
      wireRoot: root,
      source: AppRemoteConfigSource.defaults,
    );
  }

  factory AppRemoteConfigSnapshot.fromWire(
    ContentAppConfigWire wire, {
    AppRemoteConfigSource source = AppRemoteConfigSource.networkFresh,
  }) {
    return AppRemoteConfigSnapshot.fromRoot(wire.wireRoot, source: source);
  }

  factory AppRemoteConfigSnapshot.fromRoot(
    ContentAppConfigWireRoot root, {
    AppRemoteConfigSource source = AppRemoteConfigSource.networkFresh,
  }) {
    if (root.containsKey('packageVersion')) {
      throw const FormatException('packageVersion is retired');
    }
    final schema = _requiredString(root, 'schema');
    if (schema != canonicalSchema) {
      throw FormatException('unsupported app config schema: $schema');
    }
    final rawFetchedAt = root['fetchedAt'];
    final fetchedAt = rawFetchedAt is String
        ? DateTime.tryParse(rawFetchedAt)?.toUtc()
        : null;
    if (fetchedAt == null) {
      throw const FormatException('invalid fetchedAt');
    }
    final maxAgeSec = root['maxAgeSec'];
    if (maxAgeSec is! int || maxAgeSec <= 0) {
      throw const FormatException('invalid maxAgeSec');
    }
    final configHash = _requiredString(root, 'configHash');
    final expectedHash = calculateConfigHash(root);
    if (!_sha256Pattern.hasMatch(configHash) || configHash != expectedHash) {
      throw const FormatException('configHash mismatch');
    }
    return AppRemoteConfigSnapshot._(
      schema: schema,
      configHash: configHash,
      fetchedAt: fetchedAt,
      maxAge: Duration(seconds: maxAgeSec),
      activationPolicy: _parseActivationPolicy(root['activationPolicy']),
      wireRoot: Map<String, Object?>.from(root),
      source: source,
    );
  }

  Map<String, dynamic> toPersistedMap() {
    return Map<String, dynamic>.from(wireRoot);
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

  static String _requiredString(ContentAppConfigWireRoot root, String key) {
    final value = root[key];
    if (value is! String || value.isEmpty || value != value.trim()) {
      throw FormatException('missing $key');
    }
    return value;
  }

  static Map<String, String> _parseActivationPolicy(Object? raw) {
    if (raw is! Map) {
      throw const FormatException('invalid activationPolicy');
    }
    final result = <String, String>{};
    raw.forEach((key, value) {
      if (key is! String ||
          key.isEmpty ||
          key != key.trim() ||
          value is! String ||
          value.isEmpty ||
          value != value.trim()) {
        throw const FormatException('invalid activationPolicy entry');
      }
      result[key] = value;
    });
    if (!result.containsKey('default')) {
      throw const FormatException('missing activationPolicy.default');
    }
    return result;
  }

  static String calculateConfigHash(ContentAppConfigWireRoot root) {
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
