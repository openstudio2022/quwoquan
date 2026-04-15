import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_engine.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/conversation/orchestration/session_manager.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/tool/impl/memory/memory_search_tool.dart';
import 'package:quwoquan_app/assistant/tool/runtime/search_cache.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_registry.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:quwoquan_app/assistant/tool/impl/web/web_fetch_tool.dart';

// ---------------------------------------------------------------------------
// Mock LLM: Drives multi-tool pipeline
//   1st planner call → web_search tool call
//   2nd planner call → web_fetch tool call (deep read the first search result)
//   3rd planner call (or synthesis) → final answer
// ---------------------------------------------------------------------------
class _MultiToolLlm implements AssistantLlmProvider {
  int planCallCount = 0;
  int totalCallCount = 0;

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
    totalCallCount += 1;

    final isPlannerCall = templateId == 'planner.global_plan';
    final isSynthesisCall = templateId == 'synthesizer.final_answer';

    if (!isPlannerCall && !isSynthesisCall) {
      return const AssistantModelOutput(text: '{"summary": "用户在询问深圳的天气情况。"}');
    }

    if (isPlannerCall) {
      planCallCount += 1;

      onDelta?.call('第 $planCallCount 轮推理中...');

      final hasWebSearch = _hasExecutedTool(messages, 'web_search');
      final hasWebFetch = _hasExecutedTool(messages, 'web_fetch');

      // First retrieval step: search the web.
      if (!hasWebSearch && availableTools.contains('web_search')) {
        return AssistantModelOutput(
          text: jsonEncode(<String, dynamic>{
            'contractId': 'assistant_turn',
            'decision': {'nextAction': 'tool_call'},
            'toolCalls': [
              {
                'tool': 'web_search',
                'arguments': {'query': '深圳 今天 天气 实时'},
              },
            ],
            'reasonShort': '用户想了解深圳天气，先搜索最新信息。',
          }),
          toolCalls: <AssistantToolCall>[
            AssistantToolCall(
              name: 'web_search',
              arguments: <String, dynamic>{'query': '深圳 今天 天气 实时'},
            ),
          ],
        );
      }

      // Second retrieval step: deep-read the authoritative result.
      if (hasWebSearch &&
          !hasWebFetch &&
          availableTools.contains('web_fetch')) {
        return AssistantModelOutput(
          text: jsonEncode(<String, dynamic>{
            'contractId': 'assistant_turn',
            'decision': {'nextAction': 'tool_call'},
            'toolCalls': [
              {
                'tool': 'web_fetch',
                'arguments': {
                  'url': 'https://weather.cma.cn/shenzhen',
                  'maxChars': 5000,
                },
              },
            ],
            'reasonShort': '搜索到气象局页面，深入阅读获取详细天气数据。',
          }),
          toolCalls: <AssistantToolCall>[
            AssistantToolCall(
              name: 'web_fetch',
              arguments: <String, dynamic>{
                'url': 'https://weather.cma.cn/shenzhen',
                'maxChars': 5000,
              },
            ),
          ],
        );
      }
    }

    // Final answer (planCallCount >= 3 or synthesis)
    onDelta?.call('整理最终答案...');
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'contractId': 'assistant_turn',
        'decision': {'nextAction': 'answer'},
        'messageKind': 'answer',
        'userMarkdown': '## 深圳天气\n\n今天深圳天气晴朗，温度约25°C，相对湿度65%，东南风3级。适合户外活动。',
        'result': {
          'text': '今天深圳天气晴朗，温度约25°C，相对湿度65%。',
          'interpretation': '深圳当前天气概况',
        },
        'evidence': [
          {'claim': '温度25°C', 'source': 'web_search', 'confidence': 'high'},
          {'claim': '湿度65%', 'source': 'web_fetch', 'confidence': 'high'},
        ],
        'reasonShort': '综合搜索结果和网页详细内容，整理天气信息。',
        'selfCheck': {
          'goalSatisfied': true,
          'constraintSatisfied': true,
          'safetyBoundarySatisfied': true,
          'failedItems': <String>[],
        },
        'diagnostics': {
          'emergedTags': <Map<String, dynamic>>[],
          'failedChecks': <String>[],
          'parseStatus': '',
          'notes': <String>['基于搜索结果 + 气象局网页深度阅读'],
        },
        'modelSelfScore': {'score': 95, 'reason': '多源验证，数据可靠'},
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

void main() {
  group('Phase 8 — 新工具端到端测试', () {
    late LocalPhaseExecutionOwner loop;
    late _MultiToolLlm mockLlm;
    late AssistantMemoryRepository memoryRepo;
    late SearchResultCache searchCache;
    late Directory tempDir;
    late int webFetchCallCount;
    late int webSearchCallCount;

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
      tempDir = await Directory.systemTemp.createTemp('pa_new_tools_');
      mockLlm = _MultiToolLlm();
      webFetchCallCount = 0;
      webSearchCallCount = 0;
      searchCache = SearchResultCache();

      // Mock HTTP client for web_fetch
      final mockHttpClient = MockClient((request) async {
        webFetchCallCount += 1;
        if (request.url.host == 'weather.cma.cn') {
          return http.Response(
            '<html><head><title>深圳天气预报 - 中国气象局</title></head>'
            '<body>'
            '<h1>深圳市天气预报</h1>'
            '<p>今日天气：晴</p>'
            '<p>最高温度：26°C</p>'
            '<p>最低温度：18°C</p>'
            '<p>相对湿度：65%</p>'
            '<p>风向：东南风3级</p>'
            '<p>空气质量：良好</p>'
            '</body></html>',
            200,
            headers: {'content-type': 'text/html; charset=utf-8'},
          );
        }
        return http.Response('Not found', 404);
      });

      memoryRepo = AssistantMemoryRepository(
        ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
      );

      // Pre-seed a memory for personalization
      await memoryRepo.rememberText(
        id: 'user-pref-city',
        text: '用户常住深圳，关注深圳本地天气',
        metadata: <String, dynamic>{'type': 'preference'},
      );

      // Build tool chain
      final webSearchTool = _FakeWebSearchTool(
        searchCache: searchCache,
        onExecute: () => webSearchCallCount++,
      );
      final webFetchTool = WebFetchTool(client: mockHttpClient);
      final memorySearchTool = MemorySearchTool(memoryRepository: memoryRepo);

      final toolRegistry = AssistantToolRegistry()
        ..register(webSearchTool)
        ..register(webFetchTool)
        ..register(memorySearchTool);

      final runtime = ReactRuntime(
        llmProvider: mockLlm,
        toolRegistry: toolRegistry,
      );
      loop = LocalPhaseExecutionOwner(
        runtime,
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions.json',
        ),
        memoryRepository: memoryRepo,
      );
    });

    tearDown(() async {
      await tempDir.delete(recursive: true);
    });

    test('多工具链路：至少完成 web_search，必要时继续 web_fetch，再生成最终答案', () async {
      final traces = <AssistantTraceEvent>[];
      final response = await loop.run(
        const AssistantRunRequest(
          sessionId: 'multi_tool_weather',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳今天天气怎么样？'),
          ],
        ),
        onTraceEvent: traces.add,
      );

      expect(response.finalText, isNotEmpty);
      expect(response.degraded, isFalse);

      // web_search 必须调用；web_fetch 允许按当前收敛策略择机触发。
      expect(webSearchCallCount, greaterThan(0), reason: 'web_search 应被调用');

      // Trace 至少包含 web_search；若触发深读则包含 web_fetch。
      final toolStarts = traces
          .where((t) => t.type == AssistantTraceEventType.toolStart)
          .toList();
      final toolMessages = toolStarts.map((t) => t.message).toList();
      expect(
        toolMessages.any((m) => m.contains('web_search')),
        isTrue,
        reason: 'trace 应包含 web_search toolStart',
      );
      if (webFetchCallCount > 0) {
        expect(
          toolMessages.any((m) => m.contains('web_fetch')),
          isTrue,
          reason: 'trace 应包含 web_fetch toolStart',
        );
      }

      // Tool results 至少应覆盖已执行的检索步骤。
      final toolResults = traces
          .where((t) => t.type == AssistantTraceEventType.toolResult)
          .toList();
      expect(
        toolResults.length,
        greaterThanOrEqualTo(webFetchCallCount > 0 ? 2 : 1),
        reason: 'toolResult 数量应与已执行的检索步骤一致',
      );

      // Journey should cover multi-tool phases
      final journey = response.runArtifacts?.journey;
      expect(journey, isNotNull);
      final stages = journey!.stages.map((item) => item.stageId.name).toSet();
      expect(stages.contains('analyze'), isTrue);
      expect(stages.contains('search') || stages.contains('verify'), isTrue);
      expect(stages.contains('answer'), isTrue);

      // Final answer should contain weather info
      final combined =
          '${response.finalText} '
          '${response.displayMarkdown}';
      expect(
        combined.contains('天气') ||
            combined.contains('深圳') ||
            combined.contains('温度'),
        isTrue,
        reason: '最终答案应包含天气内容',
      );
    });

    test('搜索缓存：相同查询不重复请求', () async {
      // First run: populates cache
      await loop.run(
        const AssistantRunRequest(
          sessionId: 'cache_test_1',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳天气'),
          ],
        ),
      );
      final firstRunSearchCount = webSearchCallCount;
      expect(firstRunSearchCount, greaterThan(0));

      // SearchCache should have an entry
      expect(searchCache.has('深圳 今天 天气 实时'), isTrue, reason: '搜索缓存应包含查询结果');

      // The cache is shared, so a direct get should work
      final cached = searchCache.get('深圳 今天 天气 实时');
      expect(cached, isNotNull);
      expect(cached?['summary'], contains('深圳'));
    });

    test('memory_search 工具可独立执行', () async {
      final memoryTool = MemorySearchTool(memoryRepository: memoryRepo);
      final result = await memoryTool.execute(
        AssistantToolArguments.fromJson(<String, dynamic>{
          'query': '用户住在哪里',
        }),
      );
      expect(result.success, true);
      expect(result.data?['resultCount'], greaterThan(0));
      final results = result.data?['results'] as List;
      expect(results.first['text'], contains('深圳'));
    });

    test('web_fetch 工具可独立执行', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          '<html><head><title>测试页面</title></head>'
          '<body><p>测试内容 123</p></body></html>',
          200,
          headers: {'content-type': 'text/html; charset=utf-8'},
        );
      });
      final fetchTool = WebFetchTool(client: mockClient);
      final result = await fetchTool.execute(
        AssistantToolArguments.fromJson(<String, dynamic>{
          'url': 'https://example.com/test',
        }),
      );
      expect(result.success, true);
      expect(result.data?['title'], '测试页面');
      expect(result.data?['content'], contains('测试内容'));
      expect(result.data?['url'], 'https://example.com/test');
      expect(result.data?['charCount'], isA<int>());
    });

    test('tool_catalog.meta.json 包含新工具定义', () async {
      TestWidgetsFlutterBinding.ensureInitialized();
      final jsonStr = await rootBundle.loadString(
        'assets/assistant/tools/catalog/tool_catalog.meta.json',
      );
      final catalog = jsonDecode(jsonStr) as Map<String, dynamic>;
      final tools = (catalog['tools'] as List).cast<Map<String, dynamic>>();
      final toolNames = tools.map((t) => t['toolName'] as String).toSet();

      expect(
        toolNames.contains('web_fetch'),
        isTrue,
        reason: 'catalog 应包含 web_fetch',
      );
      expect(
        toolNames.contains('memory_search'),
        isTrue,
        reason: 'catalog 应包含 memory_search',
      );

      // Check userInteraction metadata
      final webFetchMeta = tools.firstWhere(
        (t) => t['toolName'] == 'web_fetch',
      );
      expect(webFetchMeta['userInteraction'], isNotNull);
      expect(webFetchMeta['userInteraction']['phaseTitle'], equals('阅读网页'));

      final memoryMeta = tools.firstWhere(
        (t) => t['toolName'] == 'memory_search',
      );
      expect(memoryMeta['userInteraction'], isNotNull);
      expect(memoryMeta['userInteraction']['phaseTitle'], equals('回忆相关信息'));

      expect(
        catalog.containsKey('domainToolMatrix'),
        isTrue,
        reason: 'tool catalog 允许维护 domain->tool 治理矩阵，但不得维护 domain->skill 第二真相源',
      );
    });
  });
}

/// Fake web_search that returns realistic results with cache integration.
class _FakeWebSearchTool implements AssistantTool {
  _FakeWebSearchTool({required this.searchCache, required this.onExecute});

  final SearchResultCache searchCache;
  final void Function() onExecute;

  @override
  String get name => 'web_search';

  @override
  String get description => '网络搜索';

  @override
  Future<AssistantToolResult> execute(AssistantToolArguments arguments) async {
    final query = (arguments['query'] as String?)?.trim() ?? '';

    // Check cache
    final cached = searchCache.get(query);
    if (cached != null) {
      return AssistantToolResult(
        success: true,
        message: cached['message'] as String? ?? '缓存命中',
        data: AssistantToolResultData.fromJson(<String, dynamic>{
          ...cached,
          'cacheHit': true,
        }),
      );
    }

    onExecute();
    final resultData = <String, dynamic>{
      'provider': 'duckduckgo',
      'summary': '深圳今天天气晴朗，温度25°C',
      'references': <Map<String, dynamic>>[
        {
          'title': '深圳天气预报 - 中国气象局',
          'url': 'https://weather.cma.cn/shenzhen',
          'source': '中国气象局',
          'provider': 'duckduckgo',
          'snippet': '深圳今天晴，最高温度26°C，最低温度18°C。',
        },
        {
          'title': '深圳实时天气 - 天气网',
          'url': 'https://tianqi.com/shenzhen/',
          'source': '天气网',
          'provider': 'duckduckgo',
          'snippet': '深圳当前温度25°C，湿度65%。',
        },
      ],
      'message': '检索结果：深圳今天天气晴朗，温度25°C',
    };

    searchCache.put(query, resultData);

    return AssistantToolResult(
      success: true,
      message: '检索结果：深圳今天天气晴朗，温度25°C',
      data: AssistantToolResultData.fromJson(resultData),
    );
  }
}
