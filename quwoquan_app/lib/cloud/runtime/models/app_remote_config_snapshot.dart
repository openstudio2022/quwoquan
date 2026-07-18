import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_app_config_wire.dart';

enum AppRemoteConfigSource { defaults, diskCache, networkFresh, staleDiskCache }

class AppRemoteConfigSnapshot {
  const AppRemoteConfigSnapshot({
    required this.schema,
    required this.packageVersion,
    required this.configHash,
    required this.fetchedAt,
    required this.maxAge,
    required this.activationPolicy,
    required this.wireRoot,
    required this.source,
  });

  static const String fallbackSchema = 'app_remote_config';
  static const String fallbackPackageVersion = 'embedded-defaults';
  static const Duration fallbackMaxAge = Duration(hours: 6);

  final String schema;
  final String packageVersion;
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

  AppRemoteConfigSnapshot copyWith({
    AppRemoteConfigSource? source,
    ContentAppConfigWireRoot? wireRoot,
  }) {
    final nextRoot = wireRoot ?? this.wireRoot;
    return AppRemoteConfigSnapshot(
      schema: schema,
      packageVersion: packageVersion,
      configHash: configHash,
      fetchedAt: fetchedAt,
      maxAge: maxAge,
      activationPolicy: activationPolicy,
      wireRoot: nextRoot,
      source: source ?? this.source,
    );
  }

  factory AppRemoteConfigSnapshot.defaults(ContentAppConfigWire wire) {
    final root = wire.wireRoot;
    return AppRemoteConfigSnapshot(
      schema: fallbackSchema,
      packageVersion: fallbackPackageVersion,
      configHash: _hashRoot(root),
      fetchedAt: DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
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
    final metadata = _metadataFromRoot(root);
    final fetchedAt =
        _parseDate(metadata['fetchedAt']) ?? DateTime.now().toUtc();
    final maxAgeSec = _parsePositiveInt(metadata['maxAgeSec']);
    final hash = (metadata['configHash'] ?? '').toString().trim();
    return AppRemoteConfigSnapshot(
      schema: (metadata['schema'] ?? fallbackSchema)
          .toString()
          .trim(),
      packageVersion: (metadata['packageVersion'] ?? fallbackPackageVersion)
          .toString()
          .trim(),
      configHash: hash.isEmpty ? _hashRoot(root) : hash,
      fetchedAt: fetchedAt,
      maxAge: Duration(seconds: maxAgeSec ?? fallbackMaxAge.inSeconds),
      activationPolicy: _parseActivationPolicy(metadata['activationPolicy']),
      wireRoot: root,
      source: source,
    );
  }

  Map<String, dynamic> toPersistedMap() {
    return <String, dynamic>{
      'schema': schema,
      'packageVersion': packageVersion,
      'configHash': configHash,
      'fetchedAt': fetchedAt.toUtc().toIso8601String(),
      'maxAgeSec': maxAge.inSeconds,
      'activationPolicy': activationPolicy,
      'wireRoot': wireRoot,
    };
  }

  factory AppRemoteConfigSnapshot.fromPersistedMap(
    Map<String, dynamic> map, {
    AppRemoteConfigSource source = AppRemoteConfigSource.diskCache,
  }) {
    final root = (map['wireRoot'] as Map?)?.cast<String, Object?>();
    if (root == null || root.isEmpty) {
      throw const FormatException('missing wireRoot');
    }
    return AppRemoteConfigSnapshot(
      schema: (map['schema'] ?? fallbackSchema)
          .toString()
          .trim(),
      packageVersion: (map['packageVersion'] ?? fallbackPackageVersion)
          .toString()
          .trim(),
      configHash: (map['configHash'] ?? '').toString().trim().isEmpty
          ? _hashRoot(root)
          : (map['configHash'] ?? '').toString().trim(),
      fetchedAt: _parseDate(map['fetchedAt']) ?? DateTime.now().toUtc(),
      maxAge: Duration(
        seconds:
            _parsePositiveInt(map['maxAgeSec']) ?? fallbackMaxAge.inSeconds,
      ),
      activationPolicy: _parseActivationPolicy(map['activationPolicy']),
      wireRoot: root,
      source: source,
    );
  }

  static Map<String, Object?> _metadataFromRoot(ContentAppConfigWireRoot root) {
    final bootstrap = (root['app_bootstrap'] as Map?)?.cast<String, Object?>();
    if (bootstrap != null) {
      return <String, Object?>{
        ...bootstrap,
        if (root['schema'] != null)
          'schema': root['schema'],
        if (root['packageVersion'] != null)
          'packageVersion': root['packageVersion'],
        if (root['configHash'] != null) 'configHash': root['configHash'],
      };
    }
    return root;
  }

  static Map<String, String> _parseActivationPolicy(Object? raw) {
    if (raw is! Map) {
      return const <String, String>{
        'default': 'next_session',
        'kill_switches': 'immediate',
      };
    }
    final result = <String, String>{};
    raw.forEach((key, value) {
      result[key.toString()] = value.toString();
    });
    return result;
  }

  static DateTime? _parseDate(Object? raw) {
    if (raw == null) return null;
    return DateTime.tryParse(raw.toString())?.toUtc();
  }

  static int? _parsePositiveInt(Object? raw) {
    final parsed = switch (raw) {
      final int value => value,
      final num value => value.toInt(),
      final String value => int.tryParse(value.trim()),
      _ => null,
    };
    if (parsed == null || parsed <= 0) return null;
    return parsed;
  }

  static String _hashRoot(ContentAppConfigWireRoot root) {
    final payload = jsonEncode(_normalizeJson(root));
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
