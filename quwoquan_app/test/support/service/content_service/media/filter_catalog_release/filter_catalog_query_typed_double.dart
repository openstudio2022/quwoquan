import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/adapters/verified_filter_catalog_store.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Alpha/test-only FilterCatalogRelease reader。
///
/// 默认实例只在 local_contract 中按需读取 canonical release；环境 App 与 UAT 不可达。
final class InMemoryFilterCatalogQuery implements ContentFilterCatalogQuery {
  InMemoryFilterCatalogQuery({this.snapshot});

  final FilterCatalogSlice? snapshot;

  @override
  Future<FilterCatalogSlice> getActiveFilterCatalog() async {
    return snapshot ?? const AssetFilterCatalogBootstrapReader().read();
  }
}
