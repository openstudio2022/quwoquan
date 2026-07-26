import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../generated/alpha_fixture_bundle.g.dart';

/// Alpha/test-only FilterCatalogRelease reader。
///
/// 默认实例只消费 alpha seed manifest 打包进 kernel 的 canonical release；设备运行时
/// 不读取仓库路径，也不访问云服务。
final class AlphaFilterCatalogQuery implements ContentFilterCatalogQuery {
  AlphaFilterCatalogQuery({FilterCatalogSnapshot? snapshot})
    : _snapshot = snapshot ?? _snapshotFromBundle();

  final FilterCatalogSnapshot _snapshot;

  @override
  Future<FilterCatalogSnapshot> getActiveFilterCatalog() async => _snapshot;
}

FilterCatalogSnapshot _snapshotFromBundle() {
  const objectId = 'content.filter_catalog_release';
  final asset = alphaFixtureBundle.releaseAssets[objectId];
  if (asset == null) {
    throw StateError('$objectId is absent from alpha fixture bundle');
  }
  final actualSourceHash = sha256
      .convert(utf8.encode(asset.sourceJson))
      .toString();
  if (actualSourceHash != asset.sourceSha256) {
    throw StateError('$objectId alpha fixture source hash mismatch');
  }
  final decoded = jsonDecode(asset.sourceJson);
  if (decoded is! Map) {
    throw const FormatException('alpha filter catalog must be an object');
  }
  final envelope = decoded.cast<String, Object?>();
  final categories = envelope['categories'];
  final presets = envelope['presets'];
  if (categories is! List || presets is! List) {
    throw const FormatException('alpha filter catalog members are invalid');
  }
  envelope
    ..['status'] = FilterCatalogReleaseStatus.active.name
    ..['categoryCount'] = categories.length
    ..['presetCount'] = presets.length
    ..['importedAt'] = '2026-07-20T00:00:00.000Z'
    ..['activatedAt'] = '2026-07-20T00:00:00.000Z';
  return decodeFilterCatalogSnapshot(envelope);
}
