import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../object_scenario_seed_reader.dart';

/// Alpha/test-only FilterCatalogRelease reader。
///
/// 默认实例只在 local_contract 中按需读取 canonical release；环境 App 与 UAT 不可达。
final class AlphaFilterCatalogQuery implements ContentFilterCatalogQuery {
  AlphaFilterCatalogQuery({FilterCatalogSnapshot? snapshot})
    : _snapshot = snapshot ?? _snapshotFromCanonicalRelease();

  final FilterCatalogSnapshot _snapshot;

  @override
  Future<FilterCatalogSnapshot> getActiveFilterCatalog() async => _snapshot;
}

FilterCatalogSnapshot _snapshotFromCanonicalRelease() {
  final envelope = objectScenarioSeedReader.releaseObject(
    'quwoquan_data/reference/filter_catalog/releases/'
    'filter-catalog-20260720-001/filter_catalog_release.json',
  );
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
