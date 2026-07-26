import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef FilterCatalogInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// Production read adapter. Path、operation、重试和 decoder 均来自 generated
/// operation contract；本类只绑定 typed Facet。
final class RemoteFilterCatalogQuery implements ContentFilterCatalogQuery {
  const RemoteFilterCatalogQuery({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final FilterCatalogInvocationContextFactory invocationContext;

  @override
  Future<FilterCatalogSnapshot> getActiveFilterCatalog() {
    return client.contentFilterCatalogReleaseGetActiveFilterCatalog(
      const FilterCatalogQuery(),
      context: invocationContext(
        ContentRequestPageIds.getActiveFilterCatalog,
      ),
    );
  }
}

