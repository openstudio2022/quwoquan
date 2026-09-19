import 'dart:async';
import 'dart:collection';
import 'dart:math' as math;
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/runtime/config/app_remote_config_snapshot.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentAppConfig;
import 'package:quwoquan_app/runtime/config/generated/offline_content_bundle_identity.g.dart';
import 'package:quwoquan_app/runtime/config/offline_content_failure.dart';
import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_app/runtime/platform/media/bundled_media_asset.dart';

/// Data canonical export 的读取边界；领域投影仍由各领域 generated decoder 解码。
final class OfflineContentBundle {
  OfflineContentBundle._(
    this.document,
    this.media,
    this.digest,
    this.configuration,
  );

  final Map<String, Object?> document;
  final BundledMediaCatalog media;
  final String digest;
  final AppContentConfigSnapshot configuration;

  List<Map<String, Object?>> rows(String name) =>
      (document[name]! as List).cast<Map<String, Object?>>();

  static final _flights =
      HashMap<AssetBundle, Map<Object, _BundleFlight>>.identity();
  static Object _generation = Object();

  /// 组合根重建即隔离旧在途任务；不持有成功快照或媒体字节。
  static void invalidateSourceScope() {
    _generation = Object();
    for (final flights in _flights.values) {
      for (final flight in flights.values) {
        flight.invalidate();
      }
    }
    _flights.clear();
  }

  static Future<OfflineContentBundle> load({
    AssetBundle? assets,
    String expectedDigest = offlineContentManifestDigest,
    Object? sourceGeneration,
    bool Function()? isSourceCurrent,
  }) {
    final source = assets ?? rootBundle;
    final generation = _generation;
    final runtimeIdentity = CloudRuntimeConfig.isHydrated
        ? CloudRuntimeConfig.runtimeConfigPackageDigest
        : null;
    final key = (runtimeIdentity, expectedDigest, sourceGeneration);
    final flights = _flights.putIfAbsent(source, () => {});
    final existing = flights[key];
    if (existing != null) return existing.future;
    final flight = _BundleFlight(
      () =>
          identical(generation, _generation) &&
          (isSourceCurrent?.call() ?? true) &&
          runtimeIdentity ==
              (CloudRuntimeConfig.isHydrated
                  ? CloudRuntimeConfig.runtimeConfigPackageDigest
                  : null),
    );
    flights[key] = flight;
    flight.future =
        _load(
              assets: source,
              expectedDigest: expectedDigest,
              flight: flight,
              checkSource: () {
                if (!identical(generation, _generation) ||
                    !(isSourceCurrent?.call() ?? true) ||
                    runtimeIdentity !=
                        (CloudRuntimeConfig.isHydrated
                            ? CloudRuntimeConfig.runtimeConfigPackageDigest
                            : null)) {
                  throw const OfflineContentFailure(
                    'bundle_source_invalidated',
                  );
                }
              },
            )
            .timeout(
              const Duration(seconds: 6),
              onTimeout: () {
                flight.invalidate();
                throw TimeoutException(
                  'Offline bundle verification exceeded budget',
                  const Duration(seconds: 6),
                );
              },
            )
            .whenComplete(() {
              flight.invalidate();
              if (identical(flights[key], flight)) flights.remove(key);
              if (flights.isEmpty && identical(_flights[source], flights)) {
                _flights.remove(source);
              }
            });
    return flight.future;
  }

  static Future<OfflineContentBundle> _load({
    required AssetBundle assets,
    required String expectedDigest,
    required _BundleFlight flight,
    required void Function() checkSource,
  }) async {
    final bundle = assets;
    final data = await bundle
        .load(offlineContentManifestAssetPath)
        .timeout(const Duration(seconds: 6));
    final bytes = data.buffer.asUint8List(
      data.offsetInBytes,
      data.lengthInBytes,
    );
    flight.check();
    if (await compute(_bundleByteDigest, bytes) != expectedDigest) {
      throw const OfflineContentFailure('bundle_manifest_integrity_invalid');
    }
    flight.check();
    final raw = await compute(_decodeVerifiedManifest, bytes);
    flight.check();
    final media = <BundledMediaAsset>[];
    final references = <String>{};
    final assetIds = <String>{};
    for (final row in (raw['media']! as List).cast<Map<String, Object?>>()) {
      final path = row['assetPath']! as String;
      final reference = row['canonicalReference']! as String;
      final assetId = row['assetId']! as String;
      if (!RegExp(r'^assets/content/alpha/media/[A-Za-z0-9._-]+$')
              .hasMatch(path) ||
          !references.add(reference) ||
          !assetIds.add(assetId)) {
        throw const OfflineContentFailure('bundle_media_reference_invalid');
      }
      final asset = BundledMediaAsset(
        assetId: assetId,
        version: row['version']! as int,
        kind: row['kind']! as String,
        canonicalReference: reference,
        assetPath: path,
        digest: row['sha256']! as String,
        byteLength: row['byteLength']! as int,
        mimeType: row['mimeType']! as String,
        bundleDigest: expectedDigest,
        assets: bundle,
        checkSource: checkSource,
        width: row['width'] as int?,
        height: row['height'] as int?,
        durationMs: row['durationMs'] as int?,
      );
      media.add(asset);
    }
    // 所有媒体仍逐项完整 hash；彼此独立的读取与摘要计算有界并行，并
    // 共用同一 read-generation fence 和剩余 6 秒总预算。
    const verificationParallelism = 4;
    var nextMediaIndex = 0;
    Future<void> verifyMediaWorker() async {
      while (true) {
        flight.check();
        final index = nextMediaIndex++;
        if (index >= media.length) return;
        final asset = media[index];
        final data = await bundle
            .load(asset.assetPath)
            .timeout(flight.remaining);
        flight.check();
        final bytes = data.buffer.asUint8List(
          data.offsetInBytes,
          data.lengthInBytes,
        );
        if (bytes.length != asset.byteLength ||
            await compute(_bundleByteDigest, bytes) != asset.digest) {
          throw const OfflineContentFailure('bundle_media_integrity_invalid');
        }
      }
    }

    await Future.wait(
      List<Future<void>>.generate(
        math.min(verificationParallelism, media.length),
        (_) => verifyMediaWorker(),
      ),
    );
    flight.check();
    final result = OfflineContentBundle._(
      _freeze(raw) as Map<String, Object?>,
      BundledMediaCatalog(media),
      expectedDigest,
      _BundledAppContentConfigSnapshot.fromWire(raw),
    );
    flight.check();
    return result;
  }

  static Object? _freeze(Object? value) => switch (value) {
    Map<String, Object?> map => Map<String, Object?>.unmodifiable(
      map.map((key, item) => MapEntry(key, _freeze(item))),
    ),
    List<Object?> list => List<Object?>.unmodifiable(list.map(_freeze)),
    _ => value,
  };
}

/// 每个read-generation独占；成功仅保留目录，媒体消费仍重新验字节。
final class OfflineContentReadScope {
  OfflineContentReadScope({
    AssetBundle? assets,
    this.expectedDigest = offlineContentManifestDigest,
  }) : assets = assets ?? rootBundle,
       _runtimeIdentity = CloudRuntimeConfig.isHydrated
           ? CloudRuntimeConfig.runtimeConfigPackageDigest
           : null;
  final AssetBundle assets;
  final String expectedDigest;
  final String? _runtimeIdentity;
  final Object generation = Object();
  bool _disposed = false;
  Future<OfflineContentBundle>? _reading;
  void check() {
    if (_disposed ||
        _runtimeIdentity !=
            (CloudRuntimeConfig.isHydrated
                ? CloudRuntimeConfig.runtimeConfigPackageDigest
                : null)) {
      throw const OfflineContentFailure('bundle_source_invalidated');
    }
  }

  Future<OfflineContentBundle> load() async {
    check();
    final flight = _reading ??= OfflineContentBundle.load(
      assets: assets,
      expectedDigest: expectedDigest,
      sourceGeneration: generation,
      isSourceCurrent: () => !_disposed,
    );
    try {
      final result = await flight;
      check();
      return result;
    } catch (_) {
      if (identical(_reading, flight)) _reading = null;
      rethrow;
    }
  }

  void dispose() {
    _disposed = true;
    _reading = null;
  }
}

String _bundleByteDigest(Uint8List bytes) => 'sha256:${sha256.convert(bytes)}';

Map<String, Object?> _decodeVerifiedManifest(Uint8List bytes) {
  final raw = jsonDecode(utf8.decode(bytes)) as Map<String, Object?>;
  final body = Map<String, Object?>.of(raw)..remove('bundleId');
  if (raw['schema'] != 'quwoquan.offline_content_bundle' ||
      raw['version'] != 1 ||
      raw['sourceOwner'] != 'qwq_data' ||
      raw['bundleId'] !=
          'alpha-${sha256.convert(utf8.encode(canonicalJsonEncode(body)))}') {
    throw const OfflineContentFailure('bundle_manifest_identity_invalid');
  }
  return raw;
}

final class _BundleFlight {
  _BundleFlight(this.isCurrent);
  final bool Function() isCurrent;
  final Stopwatch clock = Stopwatch()..start();
  late Future<OfflineContentBundle> future;
  bool active = true;
  void invalidate() => active = false;
  Duration get remaining {
    check();
    return const Duration(seconds: 6) - clock.elapsed;
  }

  void check() {
    if (!active || !isCurrent()) {
      throw const OfflineContentFailure('bundle_source_invalidated');
    }
    if (clock.elapsed >= const Duration(seconds: 6)) {
      throw TimeoutException(
        'Offline bundle verification exceeded budget',
        const Duration(seconds: 6),
      );
    }
  }
}

final class _BundledAppContentConfigSnapshot
    implements AppContentConfigSnapshot {
  const _BundledAppContentConfigSnapshot(this.content, this.configHash);

  factory _BundledAppContentConfigSnapshot.fromWire(Map<String, Object?> raw) {
    final configuration = raw['configuration']! as Map<String, Object?>;
    final digest = raw['configurationDigest']! as String;
    if (digest !=
        'sha256:${sha256.convert(utf8.encode(canonicalJsonEncode(configuration)))}') {
      throw const OfflineContentFailure(
        'bundle_configuration_integrity_invalid',
      );
    }
    return _BundledAppContentConfigSnapshot(
      ContentAppConfig.fromWire(
        configuration['content']! as Map<String, Object?>,
      ),
      digest,
    );
  }

  @override
  final ContentAppConfig content;
  @override
  final String configHash;
  @override
  AppRemoteConfigSource get source => AppRemoteConfigSource.bundledSnapshot;
  @override
  String get defaultActivation => 'immediate';
}
