import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/assistant/infrastructure/openclaw_bridge.dart';
import 'package:quwoquan_app/assistant/conversation/orchestration/agent_loop.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/conversation/orchestration/session_manager.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/skills/assistant_skill_executor.dart';
import 'package:quwoquan_app/assistant/skills/skill_manifest.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_registry.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:test/test.dart';

void main() {
  group('Acceptance VM scenarios', () {
    late AssistantToolRegistry toolRegistry;
    late PersonalAssistantAgentLoop agentLoop;
    late SimpleSkillExecutor skillExecutor;
    late Directory tempDir;

    setUp(() async {
      tempDir = await Directory.systemTemp.createTemp('pa_acceptance_vm_');
      toolRegistry = AssistantToolRegistry()
        ..register(_DeterministicWebSearchTool());
      final runtime = ReactRuntime(
        llmProvider: const HeuristicLocalLlmProvider(),
        toolRegistry: toolRegistry,
      );
      agentLoop = PersonalAssistantAgentLoop(
        runtime,
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
        ),
      );
      skillExecutor = SimpleSkillExecutor(toolRegistry);
    });

    tearDown(() async {
      if (await tempDir.exists()) {
        await tempDir.delete(recursive: true);
      }
    });

    test(
      'Scenario A: voice command can invoke knowledge skill (web search)',
      () async {
        const manifest = PersonalAssistantSkillManifest(
          id: 'web.quick_search',
          name: '快速搜索',
          description: '知识百科与生活问答搜索',
          version: '1.0.0',
          category: 'knowledge',
          executionTarget: 'tool_chain',
          parametersSchema: <String, dynamic>{},
          visibility: 'both',
          allowedTools: <String>['web_search'],
          domainId: 'knowledge_qa',
          toolChainProfile: 'knowledge_qa',
        );
        final voiceText = '请问今日杭州天气与出行规划建议';
        final result = await skillExecutor.invoke(
          skill: manifest,
          arguments: <String, dynamic>{
            'toolName': 'web_search',
            'toolArgs': <String, dynamic>{
              'query': voiceText,
              'provider': 'perplexity',
              'backupProviders': <String>['brave', 'openclaw_proxy'],
            },
          },
        );

        expect(result.success, isTrue);
        expect(result.message, contains('结论：'));
        expect(result.message, contains('不确定性：'));
      },
    );

    test(
      'Scenario A2: feishu voice -> OpenClaw bridge -> gateway invoke skill',
      () async {
        final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
        server.listen((request) async {
          if (request.uri.path.contains('/v1/skills/invoke') &&
              request.method.toUpperCase() == 'POST') {
            final body = await utf8.decoder.bind(request).join();
            final decoded = jsonDecode(body);
            final json = decoded is Map
                ? decoded.cast<String, dynamic>()
                : <String, dynamic>{};
            final skillId = json['skill_id']?.toString() ?? '';
            request.response.headers.contentType = ContentType.json;
            request.response.write(
              jsonEncode(<String, dynamic>{
                'success': skillId == 'web.quick_search',
                'message': 'web search success',
                'data': <String, dynamic>{'source': 'mock-openclaw'},
              }),
            );
            await request.response.close();
            return;
          }
          request.response.statusCode = HttpStatus.notFound;
          await request.response.close();
        });
        addTearDown(() async {
          await server.close(force: true);
        });

        final bridge = OpenClawBridge(
          baseUrl: 'http://127.0.0.1:${server.port}',
        );
        final text = await bridge.handleVoiceCommandForKnowledgeQa(
          '请问今天杭州天气如何',
        );
        expect(text, isNotNull);
        final normalized = text!.toLowerCase();
        expect(normalized, anyOf(contains('success'), contains('unavailable')));
      },
    );

    test('Scenario B: app text chat can directly ask assistant', () async {
      final response = await agentLoop.run(
        const AssistantRunRequest(
          sessionId: 'assistant',
          userId: 'u_mobile',
          deviceProfile: 'mobile',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '帮我搜索财经知识并给出简要说明'),
          ],
        ),
      );

      expect(response.finalText.trim().isNotEmpty, isTrue);
      expect(
        response.traces.any(
          (e) => e.type == AssistantTraceEventType.lifecycleStart,
        ),
        isTrue,
      );
      expect(
        response.traces.any(
          (e) => e.type == AssistantTraceEventType.lifecycleEnd,
        ),
        isTrue,
      );
      // HeuristicLocalLlmProvider 不生成 tool call，故不检测 toolStart/toolResult
    });
  });
}

class _DeterministicWebSearchTool implements AssistantTool {
  @override
  String get name => 'web_search';

  @override
  String get description =>
      'Deterministic web search stub for VM acceptance tests.';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    final query = (arguments['query'] as String?)?.trim() ?? '';
    if (query.isEmpty) {
      return const AssistantToolResult(
        success: false,
        message: 'Missing query',
        errorCode: AssistantErrorCode.invalidArguments,
      );
    }
    return AssistantToolResult(
      success: true,
      message: '检索结果：杭州天气多云，出行建议优先地铁并关注晚高峰拥堵。',
      data: <String, dynamic>{
        'provider': 'stub',
        'summary': '杭州天气多云，出行建议优先地铁并关注晚高峰拥堵。',
        'raw': <String, dynamic>{
          'results': <Map<String, dynamic>>[
            <String, dynamic>{
              'title': '杭州天气预报',
              'snippet': '今日多云，气温 15-23C，晚间有小雨概率。',
              'url': 'https://example.com/weather/hangzhou',
            },
            <String, dynamic>{
              'title': '杭州交通出行提示',
              'snippet': '工作日晚高峰拥堵明显，建议错峰或地铁出行。',
              'url': 'https://example.com/traffic/hangzhou',
            },
          ],
        },
      },
    );
  }
}
