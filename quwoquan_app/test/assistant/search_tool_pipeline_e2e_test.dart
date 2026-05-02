import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/session/assistant_session_manager.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_engine.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/tool/impl/search/search_tool.dart';
import 'package:quwoquan_app/assistant/tool/impl/web/websearch_tool.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_registry.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/core/models/search_hit_payload.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';

class _SearchFirstLlm implements AssistantLlmProvider {
  int planCallCount = 0;

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    final isPlannerCall = templateId == 'planner.global_plan';
    final isSynthesisCall = templateId == 'synthesizer.final_answer';

    if (!isPlannerCall && !isSynthesisCall) {
      return const AssistantModelOutput(text: '{"summary":"用户希望了解摄影入门。"}');
    }

    if (isPlannerCall) {
      planCallCount += 1;
      onDelta?.call('第 $planCallCount 轮推理中...');
      final hasSearch = _hasExecutedTool(messages, 'search');
      if (!hasSearch && availableTools.contains('search')) {
        return AssistantModelOutput(
          text: jsonEncode(<String, dynamic>{
            'contractId': 'assistant_turn',
            'decision': {'nextAction': 'tool_call'},
            'toolCalls': [
              {
                'tool': 'search',
                'arguments': {
                  'query': '摄影 入门',
                  'objectTypes': ['web.document', 'content.post'],
                  'limit': 4,
                },
              },
            ],
            'reasonShort': '先用统一检索同时拉取网页与站内资料。',
          }),
          toolCalls: <AssistantToolCall>[
            AssistantToolCall(
              name: 'search',
              arguments: <String, dynamic>{
                'query': '摄影 入门',
                'objectTypes': <String>['web.document', 'content.post'],
                'limit': 4,
              },
            ),
          ],
        );
      }
    }

    onDelta?.call('整理最终答案...');
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'contractId': 'assistant_turn',
        'decision': {'nextAction': 'answer'},
        'messageKind': 'answer',
        'userMarkdown': '## 摄影入门\n\n我已为你统一检索了网页与站内内容，并整理出入门路线。',
        'result': {
          'text': '摄影入门建议从曝光三要素、构图与光线开始练习。',
          'interpretation': '摄影入门路线建议',
        },
        'selfCheck': {
          'goalSatisfied': true,
          'constraintSatisfied': true,
          'safetyBoundarySatisfied': true,
          'failedItems': <String>[],
        },
        'toolCalls': <dynamic>[],
      }),
    );
  }
}

bool _hasExecutedTool(List<Map<String, dynamic>> messages, String toolName) {
  for (final message in messages) {
    if ((message['role'] as String?) == 'assistant') {
      final toolCalls = message['tool_calls'];
      if (toolCalls is List) {
        for (final item in toolCalls.whereType<Map>()) {
          final function =
              (item['function'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{};
          final name = (function['name'] as String?)?.trim() ?? '';
          if (name == toolName) {
            return true;
          }
        }
      }
    }
    if ((message['role'] as String?) == 'tool') {
      final content = (message['content'] as String?) ?? '';
      if (content.contains('"toolName":"$toolName"') ||
          content.contains('"toolName": "$toolName"')) {
        return true;
      }
    }
  }
  return false;
}

class _FakeSearchRepository implements SearchRepository {
  @override
  Future<SearchResponse> search(SearchRequest request) async {
    return SearchResponse(
      request: request.normalized(),
      sections: <SearchSection>[
        SearchSection(
          id: 'content',
          title: '内容',
          objectTypes: const <SearchObjectType>[SearchObjectType.contentPost],
          hits: const <SearchHit>[
            SearchHit(
              objectType: SearchObjectType.contentPost,
              objectId: 'post_1',
              title: '摄影入门：曝光三要素',
              subtitle: '站内内容',
              resolvedFrom: SearchResolvedFrom.remote,
              payload: SearchHitPayloadWireMap(<String, dynamic>{
                'postId': 'post_1',
                'contentType': 'article',
                'title': '摄影入门：曝光三要素',
                'summary': '站内内容',
              }),
            ),
          ],
          resolvedFrom: SearchResolvedFrom.remote,
        ),
      ],
    );
  }
}

class _FakeWebSearchTool extends WebSearchTool {
  _FakeWebSearchTool();

  @override
  Future<AssistantToolResult> execute(AssistantToolArguments arguments) async {
    return AssistantToolResult(
      success: true,
      message: 'ok',
      data: AssistantToolResultData.fromJson(<String, dynamic>{
        'provider': 'duckduckgo',
        'summary': '摄影入门资料',
        'references': <Map<String, dynamic>>[
          <String, dynamic>{
            'title': '摄影入门指南',
            'url': 'https://example.com/photo',
            'source': 'example.com',
            'snippet': '网页资料',
          },
        ],
      }),
    );
  }
}

void main() {
  group('Phase 8 — search tool 端到端', () {
    late LocalPhaseExecutionOwner loop;
    late _SearchFirstLlm mockLlm;
    late ToolMetadataRegistry toolMetadata;
    late Directory tempDir;

    setUpAll(() async {
      final binding = TestWidgetsFlutterBinding.ensureInitialized();
      const channel = MethodChannel('plugins.flutter.io/path_provider');
      binding.defaultBinaryMessenger.setMockMethodCallHandler(channel, (
        MethodCall call,
      ) async {
        if (call.method == 'getApplicationDocumentsDirectory') {
          return Directory.systemTemp.path;
        }
        return null;
      });
    });

    setUp(() async {
      tempDir = await Directory.systemTemp.createTemp('pa_search_tool_e2e_');
      mockLlm = _SearchFirstLlm();
      toolMetadata = ToolMetadataRegistry();
      await toolMetadata.ensureLoaded();

      final toolRegistry = AssistantToolRegistry(metadataRegistry: toolMetadata)
        ..register(
          SearchTool(
            searchRepository: _FakeSearchRepository(),
            webSearchTool: _FakeWebSearchTool(),
          ),
        );
      final runtime = ReactRuntime(
        llmProvider: mockLlm,
        toolRegistry: toolRegistry,
        toolMetadataRegistry: toolMetadata,
      );
      loop = LocalPhaseExecutionOwner(
        runtime,
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
        ),
        toolMetadataRegistry: toolMetadata,
      );
    });

    tearDown(() async {
      await tempDir.delete(recursive: true);
    });

    test('assistant pipeline 执行 search tool 并返回 web+站内统一结果', () async {
      final traces = <AssistantTraceEvent>[];
      final response = await loop.run(
        const AssistantRunRequest(
          sessionId: 'search_tool_e2e',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '想学摄影入门，有什么建议？'),
          ],
        ),
        onTraceEvent: traces.add,
      );

      expect(response.finalText, isNotEmpty);
      expect(response.degraded, isFalse);
      expect(mockLlm.planCallCount, greaterThanOrEqualTo(1));

      final toolStarts = traces
          .where((t) => t.type == AssistantTraceEventType.toolStart)
          .toList();
      final toolResults = traces
          .where((t) => t.type == AssistantTraceEventType.toolResult)
          .toList();

      expect(
        toolStarts.any((t) => (t.data?['toolName'] as String?) == 'search'),
        isTrue,
        reason: 'trace 应包含 search toolStart',
      );
      final searchResult = toolResults.firstWhere(
        (t) => (t.data?['toolName'] as String?) == 'search',
        orElse: () => throw StateError('missing search toolResult'),
      );
      expect(searchResult.data?['mode'], equals('result'));
      expect((searchResult.data?['sections'] as List?)?.length, equals(2));
      expect((searchResult.data?['hits'] as List?)?.length, equals(2));
      expect((searchResult.data?['references'] as List?)?.length, equals(1));
    });
  });
}
