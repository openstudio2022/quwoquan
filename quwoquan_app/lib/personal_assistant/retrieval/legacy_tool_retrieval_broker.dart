import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_broker.dart';
import 'package:quwoquan_app/personal_assistant/tools/web_fetch_tool.dart';
import 'package:quwoquan_app/personal_assistant/tools/websearch_tool.dart';

/// M3 bootstrap adapter.
///
/// Keeps the existing `web_search` / `web_fetch` implementations as the
/// execution backend, while letting runtime and tools converge on a single
/// broker interface.
class LegacyToolRetrievalBroker implements RetrievalBroker {
  LegacyToolRetrievalBroker({
    WebSearchTool? searchTool,
    WebFetchTool? fetchTool,
  }) : _searchTool = searchTool ?? WebSearchTool(),
       _fetchTool = fetchTool ?? WebFetchTool();

  final WebSearchTool _searchTool;
  final WebFetchTool _fetchTool;

  @override
  Future<RetrievalSearchResult> search(RetrievalSearchRequest request) async {
    final result = await _searchTool.execute(request.toToolArguments());
    return RetrievalSearchResult(
      success: result.success,
      message: result.message,
      errorCode: result.errorCode,
      degraded: result.degraded,
      data: <String, dynamic>{
        ...?result.data,
        'broker': 'legacy_tool',
        'query': request.query,
        'queryTasks': request.queryTasks,
      },
    );
  }

  @override
  Future<RetrievalFetchResult> fetch(RetrievalFetchRequest request) async {
    final result = await _fetchTool.execute(request.toToolArguments());
    return RetrievalFetchResult(
      success: result.success,
      message: result.message,
      errorCode: result.errorCode,
      degraded: result.degraded,
      data: <String, dynamic>{
        ...?result.data,
        'broker': 'legacy_tool',
        'url': request.url,
      },
    );
  }
}
