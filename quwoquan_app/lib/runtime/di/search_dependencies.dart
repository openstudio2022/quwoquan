import 'package:quwoquan_app/service/api_edge/graphql_read/persisted_query_execution/adapters/persisted_search_page_query_remote.dart';
import 'package:quwoquan_app/service/search_service/search/recent_search_state/adapters/recent_search_remote.dart';
import 'package:quwoquan_app/service/search_service/search/recent_search_state/application/recent_search_ports.dart';
import 'package:quwoquan_app/service/search_service/search/search_feedback_fact/adapters/search_feedback_remote.dart';
import 'package:quwoquan_app/service/search_service/search/search_feedback_fact/application/public/search_feedback_fact_appender.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/remote_search_page_repository.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/search_repository.dart';
import 'package:quwoquan_app/service/search_service/search/search_request_fact/adapters/hot_query_remote.dart';
import 'package:quwoquan_app/service/search_service/search/search_request_fact/application/search_hot_query_reader.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/runtime/transport/graphql_read/generated/search_page.g.dart';

/// 共享同一 RecentSearchState Remote 实例的 public ports。
final class AppProductionRecentSearchFacets {
  const AppProductionRecentSearchFacets({
    required this.query,
    required this.commandWriter,
  });

  final RecentSearchQuery query;
  final RecentSearchCommandWriter commandWriter;
}

/// search domain 的唯一 production 装配入口。
final class SearchProductionComposition {
  const SearchProductionComposition._();

  static SearchRepository searchRepository({
    required GeneratedSearchPageGraphQLClient searchPageClient,
    required PersistedQueryInvocationContextFactory invocationContext,
  }) {
    return RemoteSearchPageRepository(
      remoteQuery: RemotePersistedSearchPageQuery(
        client: searchPageClient,
        invocationContext: invocationContext,
      ),
    );
  }

  static SearchHotQueryReader hotQueryReader({
    required GeneratedCloudOperationClient client,
    required SearchHotQueryInvocationContextFactory invocationContext,
  }) {
    return RemoteSearchHotQueryReader(
      client: client,
      invocationContext: invocationContext,
    );
  }

  static AppProductionRecentSearchFacets recentSearchFacets({
    required GeneratedCloudOperationClient client,
    required SearchInvocationContextFactory invocationContext,
  }) {
    final remote = RemoteRecentSearchAdapter(
      client: client,
      invocationContext: invocationContext,
    );
    return AppProductionRecentSearchFacets(
      query: remote,
      commandWriter: remote,
    );
  }

  static SearchFeedbackFactAppender feedbackFactAppender({
    required GeneratedCloudOperationClient client,
    required SearchFeedbackInvocationContextFactory invocationContext,
  }) {
    return RemoteSearchFeedbackAdapter(
      client: client,
      invocationContext: invocationContext,
    );
  }
}
