import 'package:quwoquan_app/service/search_service/search/search_index_view/application/search_page_query_facet.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/search_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_contracts/generated/gateway_contracts.dart';

/// 正式 Search result 的 persisted GraphQL 仓库。
///
/// SearchPage flat card 保持独立 typed 结果；禁止把 opaque objectRef 解释为旧
/// objectId，也禁止构造 SearchResponseView/CanonicalSearchHit 的缺省字段。
final class RemoteSearchPageRepository implements SearchRepository {
  const RemoteSearchPageRepository({required this.remoteQuery});

  static const int _maximumPageItems = 20;

  final SearchPageQueryFacet remoteQuery;

  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final normalized = request.normalized();
    if (normalized.mode != CanonicalSearchMode.result) {
      throw StateError('SearchPage remote accepts result mode only');
    }
    if (normalized.query.isEmpty) {
      return SearchResponse(
        request: normalized,
        sections: const <SearchSection>[],
      );
    }
    final objectTypes = _searchPageObjectTypes(normalized.objectTypes);
    if (normalized.objectTypes.isNotEmpty && objectTypes.isEmpty) {
      return SearchResponse(
        request: normalized,
        sections: const <SearchSection>[],
      );
    }
    final result = await remoteQuery.searchPage(
      SearchPageInput(
        query: normalized.query,
        first: normalized.limit.clamp(1, _maximumPageItems),
        objectTypes: objectTypes.isEmpty ? null : objectTypes,
      ),
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
    return SearchResponse(
      request: normalized,
      sections: const <SearchSection>[],
      relatedTerms: List<String>.unmodifiable(result.suggestions),
      pageItems: List<SearchPageResultItem>.unmodifiable(
        result.items.map(SearchPageResultItem.fromWireSlice),
      ),
      pageFacets: List<SearchPageResultFacet>.unmodifiable(
        result.facets.map(SearchPageResultFacet.fromWireSlice),
      ),
      nextCursor: result.nextCursor,
    );
  }

  List<String> _searchPageObjectTypes(Set<SearchObjectType> requested) {
    final values = <String>{};
    for (final objectType in requested) {
      final value = switch (objectType) {
        SearchObjectType.contentPost => SearchPageObjectType.contentPost,
        SearchObjectType.userProfile => SearchPageObjectType.userProfile,
        SearchObjectType.entityHomepage => SearchPageObjectType.entityHomepage,
        SearchObjectType.circleCircle => SearchPageObjectType.circle,
        SearchObjectType.circleGroup => SearchPageObjectType.circleGroup,
        SearchObjectType.locationPlace => SearchPageObjectType.locationPlace,
        _ => null,
      };
      if (value != null) values.add(value.wireName);
    }
    final sorted = values.toList()..sort();
    return List<String>.unmodifiable(sorted);
  }
}
