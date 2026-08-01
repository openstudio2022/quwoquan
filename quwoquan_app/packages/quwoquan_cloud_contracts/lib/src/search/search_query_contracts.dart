import '../operation_cancellation.dart';
import '../operation_request_payload.dart';
import '../generated/search/canonical_search_mode.g.dart';
import '../generated/search/search_response_view.g.dart';
export '../generated/search/canonical_search_citation.g.dart';
export '../generated/search/canonical_search_content_hit.g.dart';
export '../generated/search/canonical_search_degrade_signal.g.dart';
export '../generated/search/canonical_search_evidence.g.dart';
export '../generated/search/canonical_search_facet.g.dart';
export '../generated/search/canonical_search_geo_point.g.dart';
export '../generated/search/canonical_search_hit.g.dart';
export '../generated/search/canonical_search_intersection_reason.g.dart';
export '../generated/search/canonical_search_mode.g.dart';
export '../generated/search/canonical_search_payload.g.dart';
export '../generated/search/canonical_search_provenance.g.dart';
export '../generated/search/canonical_search_rank_reason.g.dart';
export '../generated/search/search_response_view.g.dart';
part '../generated/requests/search/search_query_contracts.requests.g.dart';

/// App 的 SearchIndexView 查询能力；request/response wire 均由 contracts 生成。
abstract interface class CanonicalSearchQueryFacet {
  Future<SearchResponseView> search(
    CanonicalSearchQuery query, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  });
}
