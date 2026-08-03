import 'content_operation_contracts.g.dart';

abstract interface class ContentFilterCatalogQuery {
  Future<FilterCatalogSlice> getActiveFilterCatalog();
}
