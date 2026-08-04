import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../cloud_services/object_doubles/object_scenario_seed_reader.dart';

/// Alpha/test-only FilterCatalogRelease reader。
///
/// 默认实例只在 local_contract 中按需读取 canonical release；环境 App 与 UAT 不可达。
final class AlphaFilterCatalogQuery implements ContentFilterCatalogQuery {
  AlphaFilterCatalogQuery({FilterCatalogSlice? snapshot})
    : _snapshot = snapshot ?? _snapshotFromCanonicalRelease();

  final FilterCatalogSlice _snapshot;

  @override
  Future<FilterCatalogSlice> getActiveFilterCatalog() async => _snapshot;
}

FilterCatalogSlice _snapshotFromCanonicalRelease() {
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
    ..remove('sourceOwner')
    ..['status'] = FilterCatalogReleaseStatus.active.name
    ..['categoryCount'] = categories.length
    ..['presetCount'] = presets.length
    ..['importedAt'] = '2026-07-20T00:00:00.000Z'
    ..['activatedAt'] = '2026-07-20T00:00:00.000Z';
  return decodeFilterCatalogSlice(envelope);
}
