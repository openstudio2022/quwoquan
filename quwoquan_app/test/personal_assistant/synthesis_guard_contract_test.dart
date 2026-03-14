import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/personal_assistant/engine/agent_loop.dart';
import 'package:quwoquan_app/personal_assistant/engine/llm_provider.dart';
import 'package:quwoquan_app/personal_assistant/engine/react_runtime.dart';
import 'package:quwoquan_app/personal_assistant/engine/session_manager.dart';
import 'package:quwoquan_app/personal_assistant/memory/memory_repository.dart';
import 'package:quwoquan_app/personal_assistant/memory/objectbox_store.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/template_runtime/prompt_template.dart';
import 'package:quwoquan_app/personal_assistant/template_runtime/template_registry.dart';
import 'package:quwoquan_app/personal_assistant/template_runtime/template_runtime.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_registry.dart';
import 'package:test/test.dart';

typedef _ChatStrategy =
    Future<_MockChatResponse> Function(Map<String, dynamic> requestBody);

class _MockChatResponse {
  const _MockChatResponse.json(this.content)
    : isStream = false,
      streamChunks = const <String>[];

  const _MockChatResponse.sse(this.streamChunks)
    : isStream = true,
      content = '';

  final bool isStream;
  final String content;
  final List<String> streamChunks;
}

PromptTemplateRuntime _buildTemplateRuntime() {
  return PromptTemplateRuntime(
    registry: TemplateRegistry.withSeeded(
      seededTemplates: <String, PromptTemplate>{
        'planner.global_plan@v1': const PromptTemplate(
          templateId: 'planner.global_plan',
          templateVersion: 'v1',
          content: '你是测试助手。必须直接输出 assistant_turn JSON。',
        ),
        'synthesizer.final_answer@v1': const PromptTemplate(
          templateId: 'synthesizer.final_answer',
          templateVersion: 'v1',
          content: '你是测试助手。必须直接输出 assistant_turn JSON。',
        ),
      },
    ),
  );
}

Future<HttpServer> _startMockServer(_ChatStrategy strategy) async {
  final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
  server.listen((request) async {
    expect(request.uri.path, equals('/v1/chat/completions'));
    final bodyText = await utf8.decoder.bind(request).join();
    final body = jsonDecode(bodyText) as Map<String, dynamic>;
    final response = await strategy(body);
    request.response.statusCode = HttpStatus.ok;
    if (response.isStream) {
      request.response.headers.contentType = ContentType(
        'text',
        'event-stream',
        charset: 'utf-8',
      );
      for (final chunk in response.streamChunks) {
        final encodedEvent = jsonEncode(<String, dynamic>{
          'choices': <Map<String, dynamic>>[
            <String, dynamic>{
              'delta': <String, dynamic>{'content': chunk},
            },
          ],
        });
        request.response.write(
          'data: $encodedEvent\n\n',
        );
      }
      request.response.write('data: [DONE]\n\n');
    } else {
      request.response.headers.contentType = ContentType(
        'application',
        'json',
        charset: 'utf-8',
      );
      request.response.write(
        jsonEncode(<String, dynamic>{
          'choices': <Map<String, dynamic>>[
            <String, dynamic>{
              'message': <String, dynamic>{'content': response.content},
            },
          ],
        }),
      );
    }
    await request.response.close();
  });
  return server;
}

String _assistantTurnJson({
  required String markdown,
  String interpretation = '测试结论',
  List<Map<String, dynamic>> evidence = const <Map<String, dynamic>>[],
}) {
  return jsonEncode(<String, dynamic>{
    'contractVersion': 'assistant_turn',
    'decision': <String, dynamic>{'nextAction': 'answer'},
    'messageKind': 'answer',
    'userMarkdown': markdown,
    'result': <String, dynamic>{'interpretation': interpretation},
    'evidence': evidence,
    'reasoningBasis': const <dynamic>[],
    'selfCheck': const <String, dynamic>{},
    'diagnostics': const <String, dynamic>{},
    'modelSelfScore': const <String, dynamic>{},
    'toolCalls': const <dynamic>[],
    'slotState': const <String, dynamic>{},
    'askUser': const <String, dynamic>{},
    'subagentPlan': const <dynamic>[],
  });
}

List<String> _chunk(String input, {int size = 24}) {
  final chunks = <String>[];
  for (var i = 0; i < input.length; i += size) {
    final end = (i + size) > input.length ? input.length : i + size;
    chunks.add(input.substring(i, end));
  }
  return chunks;
}

OpenAiCompatibleLlmProvider _buildProvider(HttpServer server) {
  return OpenAiCompatibleLlmProvider(
    modelId: 'test-model',
    baseUrl: 'http://127.0.0.1:${server.port}/v1',
    apiKey: 'test-key',
    templateRuntime: _buildTemplateRuntime(),
    plannerTemplateVersion: 'v1',
    modelRef: 'openai/test-model',
  );
}

PersonalAssistantAgentLoop _buildLoop({
  required AssistantLlmProvider provider,
  required String tempDirPath,
}) {
  final runtime = ReactRuntime(
    llmProvider: provider,
    toolRegistry: AssistantToolRegistry(),
  );
  return PersonalAssistantAgentLoop(
    runtime,
    sessionManager: AssistantSessionManager(
      storagePath: '$tempDirPath/sessions.json',
    ),
    memoryRepository: AssistantMemoryRepository(
      ObjectBoxVectorStore(storagePath: '$tempDirPath/memory.json'),
    ),
  );
}

void main() {
  test('repairs invalid streamed synthesis output before exposing final answer', () async {
    final planningJson = _assistantTurnJson(
      markdown: '## 中间结果\n- 我正在整理最终答案。',
      interpretation: 'phase one',
    );
    final repairedJson = _assistantTurnJson(
      markdown: '## 修复后的答案\n- 现在直接给出用户可见结果。',
      interpretation: 'repaired',
    );
    final server = await _startMockServer((body) async {
      final messages =
          (body['messages'] as List?)?.whereType<Map>().toList() ?? const <Map>[];
      final joined = messages
          .map((item) => (item['content'] ?? '').toString())
          .join('\n');
      final isStream = body['stream'] == true;
      if (joined.contains('上一次输出无效')) {
        return isStream
            ? _MockChatResponse.sse(_chunk(repairedJson))
            : _MockChatResponse.json(repairedJson);
      }
      if (isStream && joined.contains('领域执行结果摘要')) {
        return const _MockChatResponse.sse(<String>[
          '<tool_call><name>web_search</name></tool_call>',
        ]);
      }
      return isStream
          ? _MockChatResponse.sse(_chunk(planningJson))
          : _MockChatResponse.json(planningJson);
    });
    addTearDown(() async {
      await server.close(force: true);
    });
    final tempDir = await Directory.systemTemp.createTemp(
      'pa_synthesis_guard_',
    );
    addTearDown(() async {
      await tempDir.delete(recursive: true);
    });
    final loop = _buildLoop(
      provider: _buildProvider(server),
      tempDirPath: tempDir.path,
    );

    final response = await loop.run(
      const AssistantRunRequest(
        sessionId: 'repair-invalid-synthesis',
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '请直接给我最终结论'),
        ],
      ),
    );
    final markdown =
        ((response.structuredResponse['uiAnswer'] as Map?)?['markdownText']
                as String?) ??
            '';

    expect(markdown, contains('修复后的答案'));
    expect(markdown, isNot(contains('<tool_call>')));
    expect(markdown, isNot(contains('"toolCalls"')));
  });

  test('injects inline evidence links into streamed final markdown', () async {
    final planningJson = _assistantTurnJson(
      markdown: '## 中间结果\n- 我正在整理可引用结论。',
      interpretation: 'phase one',
    );
    final synthesisJson = _assistantTurnJson(
      markdown: '## 天气结论\n- 深圳今天有雨，外出建议带伞。',
      interpretation: '建议带伞',
      evidence: const <Map<String, dynamic>>[
        <String, dynamic>{
          'claim': '深圳今天有雨',
          'title': '深圳天气预报',
          'url': 'https://example.com/weather',
        },
      ],
    );
    final server = await _startMockServer((body) async {
      final messages =
          (body['messages'] as List?)?.whereType<Map>().toList() ?? const <Map>[];
      final joined = messages
          .map((item) => (item['content'] ?? '').toString())
          .join('\n');
      if (body['stream'] == true && joined.contains('领域执行结果摘要')) {
        return _MockChatResponse.sse(_chunk(synthesisJson));
      }
      return body['stream'] == true
          ? _MockChatResponse.sse(_chunk(planningJson))
          : _MockChatResponse.json(planningJson);
    });
    addTearDown(() async {
      await server.close(force: true);
    });
    final tempDir = await Directory.systemTemp.createTemp(
      'pa_synthesis_evidence_',
    );
    addTearDown(() async {
      await tempDir.delete(recursive: true);
    });
    final loop = _buildLoop(
      provider: _buildProvider(server),
      tempDirPath: tempDir.path,
    );

    final response = await loop.run(
      const AssistantRunRequest(
        sessionId: 'evidence-links',
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '请整理一条带来源的结论'),
        ],
      ),
    );
    final uiAnswer = (response.structuredResponse['uiAnswer'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final markdown = (uiAnswer['markdownText'] as String?) ?? '';
    final evidenceLinks =
        (uiAnswer['evidenceLinks'] as List?)?.whereType<Map>().toList() ??
        const <Map>[];
    final evidenceBindings =
        (uiAnswer['evidenceBindings'] as List?)?.whereType<Map>().toList() ??
        const <Map>[];
    final runArtifacts = response.runArtifacts;

    expect(markdown, contains('[来源1](https://example.com/weather)'));
    expect(evidenceLinks, isNotEmpty);
    expect(evidenceLinks.first['url'], equals('https://example.com/weather'));
    expect(evidenceBindings, isNotEmpty);
    expect(
      evidenceBindings.first['url'],
      equals('https://example.com/weather'),
    );
    expect(
      (evidenceBindings.first['claim'] as String?) ?? '',
      contains('深圳今天有雨'),
    );
    expect(
      ((evidenceBindings.first['bindingId'] as String?) ?? '').isNotEmpty,
      isTrue,
    );
    expect(runArtifacts, isNotNull);
    expect(runArtifacts!.answerEvidenceBindings, isNotEmpty);
    expect(
      runArtifacts.answerEvidenceBindings.first.url,
      equals('https://example.com/weather'),
    );
  });
}
