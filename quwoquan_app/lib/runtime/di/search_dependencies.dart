import 'package:quwoquan_app/service/search_service/search/recent_search_state/adapters/recent_search_remote.dart';
import 'package:quwoquan_app/service/search_service/search/recent_search_state/application/recent_search_ports.dart';
import 'package:quwoquan_app/service/search_service/search/search_feedback_fact/adapters/search_feedback_remote.dart';
import 'package:quwoquan_app/service/search_service/search/search_feedback_fact/application/public/search_feedback_command_writer.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/remote_search_repository.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/search_query_remote.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/search_repository.dart';
import 'package:quwoquan_app/service/search_service/search/search_request_fact/adapters/hot_query_remote.dart';
import 'package:quwoquan_app/service/search_service/search/search_request_fact/application/search_hot_query_reader.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

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
    required GeneratedCloudOperationClient client,
    required SearchQueryInvocationContextFactory invocationContext,
    required String Function() sessionIdProvider,
  }) {
    return RemoteSearchRepository(
      remoteQuery: RemoteCanonicalSearchQuery(
        client: client,
        invocationContext: invocationContext,
      ),
      sessionIdProvider: sessionIdProvider,
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

  static SearchFeedbackCommandWriter feedbackCommandWriter({
    required GeneratedCloudOperationClient client,
    required SearchFeedbackInvocationContextFactory invocationContext,
  }) {
    return RemoteSearchFeedbackAdapter(
      client: client,
      invocationContext: invocationContext,
    );
  }
}
