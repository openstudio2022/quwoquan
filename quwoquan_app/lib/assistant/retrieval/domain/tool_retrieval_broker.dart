import 'package:quwoquan_app/assistant/retrieval/domain/retrieval_broker.dart';
import 'package:quwoquan_app/assistant/tool/impl/web/web_fetch_tool.dart';
import 'package:quwoquan_app/assistant/tool/impl/web/websearch_tool.dart';

/// M3 bootstrap adapter.
///
/// Keeps the existing `web_search` / `web_fetch` implementations as the
/// execution backend, while letting runtime and tools converge on a single
/// broker interface.
class ToolRetrievalBroker implements RetrievalBroker {
  ToolRetrievalBroker({
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
        'broker': 'tool_runtime',
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
        'broker': 'tool_runtime',
        'url': request.url,
      },
    );
  }
}
