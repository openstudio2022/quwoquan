import 'package:quwoquan_app/assistant/retrieval/domain/retrieval_broker.dart';
import 'package:quwoquan_app/assistant/tool/impl/web/web_fetch_tool.dart';
import 'package:quwoquan_app/assistant/tool/impl/web/websearch_tool.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

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
    final result = await _searchTool.execute(
      AssistantToolArguments.fromJson(request.toToolArguments()),
    );
    return RetrievalSearchResult(
      success: result.success,
      message: result.message,
      errorCode: result.errorCode,
      degraded: result.degraded,
      data: AssistantToolResultData(<String, Object?>{
        ...?result.data,
        'broker': 'tool_runtime',
        'query': request.query,
        if (request.queryPlans.isNotEmpty)
          'taskGraphSearchPlan': request.queryPlans
              .map((item) => item.toJson())
              .toList(growable: false),
      }),
    );
  }

  @override
  Future<RetrievalFetchResult> fetch(RetrievalFetchRequest request) async {
    final result = await _fetchTool.execute(
      AssistantToolArguments.fromJson(request.toToolArguments()),
    );
    final brokerResult = RetrievalFetchResult.fromToolResult(result);
    final payload = brokerResult.payloadOrNull;
    if (payload == null) {
      return brokerResult;
    }
    return RetrievalFetchResult(
      success: brokerResult.success,
      message: brokerResult.message,
      errorCode: brokerResult.errorCode,
      degraded: brokerResult.degraded,
      payload: payload.copyWith(
        url: payload.url.trim().isNotEmpty ? payload.url : request.url,
        searchPlanId: payload.searchPlanId.trim().isNotEmpty
            ? payload.searchPlanId
            : request.searchPlanId,
        dimension: payload.dimension.trim().isNotEmpty
            ? payload.dimension
            : request.dimension,
      ),
      data: brokerResult.data,
    );
  }
}
