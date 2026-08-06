import 'package:quwoquan_app/runtime/transport/generated/tag/tag_request_page_ids.g.dart';
import 'package:quwoquan_app/service/tag_service/tag/tag_node_view/application/public/tag_catalog_query.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef TagCatalogInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// App 商用页面使用的 TagCatalog generated-client adapter。
final class RemoteGeneratedTagCatalogQuery implements TagCatalogQuery {
  const RemoteGeneratedTagCatalogQuery({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final TagCatalogInvocationContextFactory invocationContext;

  @override
  Future<List<TagChildView>> listChildren(
    String parentTagRef, {
    int limit = TagApiDefaults.childrenLimit,
  }) async {
    final slice = await client.tagTagNodeViewListTagChildren(
      ListTagChildrenQuery(parentTagRef: parentTagRef, limit: limit),
      context: invocationContext(TagRequestPageIds.listTagChildren),
    );
    return slice.items;
  }

  @override
  Future<TagResolveView> resolveTag(String tagRef) {
    return client.tagTagNodeViewResolveTag(
      ResolveTagQuery(tagRef: tagRef),
      context: invocationContext(TagRequestPageIds.resolveTag),
    );
  }

  @override
  Future<TagValidationResultView> validateRefs({
    required String expectedTaxonomyReleaseId,
    required List<String> tagRefs,
  }) {
    return client.tagTagNodeViewValidateTagRefs(
      ValidateTagRefsQuery(
        expectedTaxonomyReleaseId: expectedTaxonomyReleaseId,
        tagRefs: tagRefs,
      ),
      context: invocationContext(TagRequestPageIds.validateTagRefs),
    );
  }
}
