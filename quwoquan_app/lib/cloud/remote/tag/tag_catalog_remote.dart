import 'package:quwoquan_app/cloud/runtime/generated/tag/tag_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef TagCatalogInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// App 商用页面使用的 TagCatalog generated-client adapter。
///
/// 只有 ContractGraph 暴露给 App 的 operation 经 generated client；其余目录/图谱查询
/// 继续由同一对象 Facet 的非 App 商用查询面承接，不在失败时互相回退。
final class RemoteGeneratedTagCatalogQuery implements TagCatalogQuery {
  const RemoteGeneratedTagCatalogQuery({
    required this.client,
    required this.invocationContext,
    required this.nonAppCommercialQuery,
  });

  final GeneratedCloudOperationClient client;
  final TagCatalogInvocationContextFactory invocationContext;
  final TagCatalogQuery nonAppCommercialQuery;

  @override
  Future<List<TagChild>> listChildren(
    String parentTagRef, {
    int limit = TagApiDefaults.childrenLimit,
  }) async {
    final slice = await client.tagTagListTagChildren(
      ListTagChildrenQuery(parentTagRef: parentTagRef, limit: limit),
      context: invocationContext(TagRequestPageIds.listTagChildren),
    );
    return slice.items;
  }

  @override
  Future<TagResolve> resolveTag(String tagRef) {
    return client.tagTagResolveTag(
      ResolveTagQuery(tagRef: tagRef),
      context: invocationContext(TagRequestPageIds.resolveTag),
    );
  }

  @override
  Future<TagValidationResult> validateRefs(List<String> tagRefs) {
    return client.tagTagValidateTagRefs(
      ValidateTagRefsQuery(tagRefs: tagRefs),
      context: invocationContext(TagRequestPageIds.validateTagRefs),
    );
  }

  @override
  Future<List<TagDimension>> listDimensions() {
    return nonAppCommercialQuery.listDimensions();
  }

  @override
  Future<List<RelatedTag>> related(
    String tagRef, {
    int limit = TagApiDefaults.relatedLimit,
  }) {
    return nonAppCommercialQuery.related(tagRef, limit: limit);
  }

  @override
  Future<List<TagSearchResult>> search(
    String query, {
    String? group,
    int limit = TagApiDefaults.searchLimit,
  }) {
    return nonAppCommercialQuery.search(query, group: group, limit: limit);
  }

  @override
  Future<List<TagSuggestion>> suggest(
    String query, {
    String? group,
    int limit = TagApiDefaults.suggestLimit,
  }) {
    return nonAppCommercialQuery.suggest(query, group: group, limit: limit);
  }
}
