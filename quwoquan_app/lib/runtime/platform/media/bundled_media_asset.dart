import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/runtime/config/offline_content_failure.dart';
import 'package:quwoquan_app/runtime/platform/media/bundled_media_materializer_stub.dart'
    if (dart.library.io) 'package:quwoquan_app/runtime/platform/media/bundled_media_materializer_io.dart' as materializer;

/// 已绑定制品摘要的媒体行。构造不意味着字节通过验证；消费前仍核验长度/hash。
final class BundledMediaAsset {
  BundledMediaAsset({
    required this.assetId,
    required this.version,
    required this.kind,
    required this.canonicalReference,
    required this.assetPath,
    required this.digest,
    required this.byteLength,
    required this.mimeType,
    required this.bundleDigest,
    required AssetBundle assets,
    this.width,
    this.height,
    this.durationMs,
  }) : _assets = assets;

  final String assetId;
  final int version;
  final String kind;
  final String canonicalReference;
  final String assetPath;
  final String digest;
  final int byteLength;
  final String mimeType;
  final String bundleDigest;
  final int? width;
  final int? height;
  final int? durationMs;
  final AssetBundle _assets;
  Future<Uint8List>? _reading;
  Future<String>? _materializing;

  String get cacheIdentity => 'bundled|$bundleDigest|$assetId|$version|$digest';

  /// single-flight 仅保留进行中读取；完整视频不长期驻留 Dart heap。
  Future<Uint8List> readVerifiedBytes() => _reading ??= _read().whenComplete(() => _reading = null);

  Future<Uint8List> _read() async {
    final data = await _assets.load(assetPath).timeout(const Duration(seconds: 6));
    final bytes = data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
    if (bytes.length != byteLength || 'sha256:${sha256.convert(bytes)}' != digest) {
      throw const OfflineContentFailure('bundle_media_integrity_invalid');
    }
    return bytes;
  }

  Future<String> materializeVideo() => _materializing ??= materializer.materializeBundledVideo(
    this,
  ).catchError((Object error) {
    _materializing = null;
    throw error;
  });
}

/// 只含已验证 manifest 的目录；缺条目永不转网络。
final class BundledMediaCatalog {
  BundledMediaCatalog(Iterable<BundledMediaAsset> assets)
    : byReference = Map.unmodifiable({for (final asset in assets) asset.canonicalReference: asset}),
      byAssetId = Map.unmodifiable({for (final asset in assets) asset.assetId: asset});

  final Map<String, BundledMediaAsset> byReference;
  final Map<String, BundledMediaAsset> byAssetId;

  BundledMediaAsset? lookup(String reference, {String assetId = ''}) {
    final asset = byReference[reference.trim()];
    if (asset == null || (assetId.isNotEmpty && asset.assetId != assetId)) return null;
    return asset;
  }
}
