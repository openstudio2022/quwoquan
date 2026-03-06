import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/personal_assistant/memory/memory_repository.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

/// Tool that exposes long-term memory semantic search to the LLM.
///
/// Wraps [AssistantMemoryRepository.recallByText] as an agent-callable tool,
/// enabling the model to proactively query user preferences, past conversation
/// highlights, and important context stored in the vector store.
class MemorySearchTool implements AssistantTool {
  MemorySearchTool({required AssistantMemoryRepository memoryRepository})
      : _memory = memoryRepository;

  final AssistantMemoryRepository _memory;
  static const int _defaultMaxResults = 5;
  static const int _absoluteMaxResults = 20;

  @override
  String get name => 'memory_search';

  @override
  String get description =>
      'Search user long-term memory for preferences, past conversations, and important dates.';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    final query = (arguments['query'] as String?)?.trim() ?? '';
    if (query.isEmpty) {
      return const AssistantToolResult(
        success: false,
        message: 'Missing required parameter: query',
        errorCode: AssistantErrorCode.invalidArguments,
      );
    }

    final maxResults = (arguments['maxResults'] as int?)
            ?.clamp(1, _absoluteMaxResults) ??
        _defaultMaxResults;

    try {
      final results = await _memory.recallByText(
        query: query,
        limit: maxResults,
      );

      final items = results
          .map((item) => <String, dynamic>{
                'id': item.id,
                'text': item.text,
                if (item.metadata.isNotEmpty) 'metadata': item.metadata,
              })
          .toList(growable: false);

      final resultCount = items.length;

      if (kDebugMode) {
        debugPrint('[MemorySearchTool] "$query" → $resultCount results');
      }

      if (resultCount == 0) {
        return AssistantToolResult(
          success: true,
          message: '未找到相关记忆',
          data: <String, dynamic>{
            'query': query,
            'resultCount': 0,
            'results': <Map<String, dynamic>>[],
          },
        );
      }

      return AssistantToolResult(
        success: true,
        message: '回忆起 $resultCount 条相关信息',
        data: <String, dynamic>{
          'query': query,
          'resultCount': resultCount,
          'results': items,
        },
      );
    } catch (e) {
      if (kDebugMode) {
        debugPrint('[MemorySearchTool] error: $e');
      }
      return AssistantToolResult(
        success: false,
        message: '记忆检索失败: $e',
        errorCode: AssistantErrorCode.executionFailed,
        degraded: true,
      );
    }
  }
}
