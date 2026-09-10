import 'dart:convert';

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

  static Future<OfflineContentBundle> load({
    AssetBundle? assets,
    String expectedDigest = offlineContentManifestDigest,
  }) => _load(
    assets: assets ?? rootBundle,
    expectedDigest: expectedDigest,
  ).timeout(const Duration(seconds: 6));

  static Future<OfflineContentBundle> _load({
    required AssetBundle assets,
    required String expectedDigest,
  }) async {
    final bundle = assets;
    final data = await bundle
        .load(offlineContentManifestAssetPath)
        .timeout(const Duration(seconds: 6));
    final bytes = data.buffer.asUint8List(
      data.offsetInBytes,
      data.lengthInBytes,
    );
    if ('sha256:${sha256.convert(bytes)}' != expectedDigest) {
      throw const OfflineContentFailure('bundle_manifest_integrity_invalid');
    }
    final raw = jsonDecode(utf8.decode(bytes)) as Map<String, Object?>;
    final identityBody = Map<String, Object?>.of(raw)..remove('bundleId');
    if (raw['schema'] != 'quwoquan.offline_content_bundle' ||
        raw['version'] != 1 ||
        raw['sourceOwner'] != 'qwq_data' ||
        raw['bundleId'] !=
            'alpha-${sha256.convert(utf8.encode(canonicalJsonEncode(identityBody)))}') {
      throw const OfflineContentFailure('bundle_manifest_identity_invalid');
    }
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
        width: row['width'] as int?,
        height: row['height'] as int?,
        durationMs: row['durationMs'] as int?,
      );
      // 只有完整闭包通过才向任何领域发布快照；坏媒体不能以首屏成功掩盖。
      await asset.readVerifiedBytes();
      media.add(asset);
    }
    return OfflineContentBundle._(
      _freeze(raw) as Map<String, Object?>,
      BundledMediaCatalog(media),
      expectedDigest,
      _BundledAppContentConfigSnapshot.fromWire(raw),
    );
  }

  static Object? _freeze(Object? value) => switch (value) {
    Map<String, Object?> map => Map<String, Object?>.unmodifiable(
      map.map((key, item) => MapEntry(key, _freeze(item))),
    ),
    List<Object?> list => List<Object?>.unmodifiable(list.map(_freeze)),
    _ => value,
  };
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
