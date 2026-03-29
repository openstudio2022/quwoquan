import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/orchestration/local_phase_execution_owner.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/conversation/orchestration/session_manager.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_registry.dart';
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
        request.response.write('data: $encodedEvent\n\n');
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
  String text = '',
  String summary = '',
  String interpretation = '测试结论',
  List<Map<String, dynamic>> evidence = const <Map<String, dynamic>>[],
  List<Map<String, dynamic>> reasoningBasis = const <Map<String, dynamic>>[],
  Map<String, dynamic> understandingSnapshot = const <String, dynamic>{},
  Map<String, dynamic> answerProcessing = const <String, dynamic>{},
  Map<String, dynamic> retrievalProcessing = const <String, dynamic>{},
}) {
  return jsonEncode(<String, dynamic>{
    'contractId': 'assistant_turn',
    'decision': <String, dynamic>{'nextAction': 'answer'},
    'messageKind': 'answer',
    'phaseId': 'answering',
    'actionCode': 'compose_answer',
    'reasonCode': 'evidence_ready',
    'reasonShort': '关键信息已经齐了，可以直接给结论。',
    'userMarkdown': markdown,
    'result': <String, dynamic>{
      'text': text,
      'summary': summary,
      'interpretation': interpretation,
    },
    'evidence': evidence,
    'reasoningBasis': reasoningBasis,
    'selfCheck': const <String, dynamic>{},
    'diagnostics': const <String, dynamic>{},
    'modelSelfScore': const <String, dynamic>{},
    'toolCalls': const <dynamic>[],
    'slotState': const <String, dynamic>{},
    'askUser': const <String, dynamic>{},
    'subagentPlan': const <dynamic>[],
    if (understandingSnapshot.isNotEmpty)
      'understandingSnapshot': understandingSnapshot,
    if (answerProcessing.isNotEmpty) 'answerProcessing': answerProcessing,
    if (retrievalProcessing.isNotEmpty)
      'retrievalProcessing': retrievalProcessing,
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

LocalPhaseExecutionOwner _buildLoop({
  required AssistantLlmProvider provider,
  required String tempDirPath,
}) {
  final runtime = ReactRuntime(
    llmProvider: provider,
    toolRegistry: AssistantToolRegistry(),
  );
  return LocalPhaseExecutionOwner(
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
  test('流式成答连续失败时会 fail-closed，而不是偷偷切到另一条非流式 repair 答案', () async {
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
          (body['messages'] as List?)?.whereType<Map>().toList() ??
          const <Map>[];
      final joined = messages
          .map((item) => (item['content'] ?? '').toString())
          .join('\n');
      final isStream = body['stream'] == true;
      if (joined.contains('上一次输出未通过 assistant_turn 契约校验') ||
          joined.contains('上一次输出未通过最终成答契约校验') ||
          joined.contains('结构化 JSON 仍然无效') ||
          joined.contains('上一次输出无效')) {
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
    final markdown = response.displayMarkdown;

    expect(response.degraded, isTrue);
    expect(markdown, contains('这次生成答案失败'));
    expect(markdown, isNot(contains('## 问题理解')));
    expect(markdown, isNot(contains('## 关键观点')));
    expect(markdown, isNot(contains('## 回答概要')));
    expect(markdown, isNot(contains('<tool_call>')));
    expect(markdown, isNot(contains('"toolCalls"')));
  });

  test('repair 仍失败时会终止成答并把答案阶段标记为 blocked', () async {
    final planningJson = _assistantTurnJson(
      markdown: '## 中间结果\n- 我正在整理最终答案。',
      interpretation: 'phase one',
    );
    final server = await _startMockServer((body) async {
      final messages =
          (body['messages'] as List?)?.whereType<Map>().toList() ??
          const <Map>[];
      final joined = messages
          .map((item) => (item['content'] ?? '').toString())
          .join('\n');
      if (body['stream'] == true && joined.contains('领域执行结果摘要')) {
        return const _MockChatResponse.sse(<String>[
          '<tool_call><name>web_search</name></tool_call>',
        ]);
      }
      if (joined.contains('上一次输出未通过 assistant_turn 契约校验') ||
          joined.contains('上一次输出未通过最终成答契约校验') ||
          joined.contains('结构化 JSON 仍然无效') ||
          joined.contains('上一次输出无效')) {
        return const _MockChatResponse.json(
          '<tool_call><name>web_search</name></tool_call>',
        );
      }
      return body['stream'] == true
          ? _MockChatResponse.sse(_chunk(planningJson))
          : _MockChatResponse.json(planningJson);
    });
    addTearDown(() async {
      await server.close(force: true);
    });
    final tempDir = await Directory.systemTemp.createTemp(
      'pa_synthesis_fail_closed_',
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
        sessionId: 'fail-closed-synthesis',
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '请直接给我最终结论'),
        ],
      ),
    );

    expect(response.displayMarkdown, contains('这次生成答案失败'));
    final timeline =
        response.runArtifacts?.processTimeline ??
        const <ProcessTimelineFrame>[];
    final answerFrame = timeline.lastWhere(
      (frame) => frame.stepId == ProcessStepId.answerOrganization,
    );
    expect(answerFrame.status, JourneyStageStatus.blocked);
    expect(answerFrame.headline, contains('这次生成答案失败'));
  });

  test('injects inline evidence links into streamed final markdown', () async {
    final planningJson = _assistantTurnJson(
      markdown: '## 中间结果\n- 我正在整理可引用结论。',
      interpretation: 'phase one',
    );
    final synthesisJson = _assistantTurnJson(
      markdown: '## 天气结论\n- 深圳今天有雨，外出建议带伞。[来源1](https://example.com/weather)',
      interpretation: '建议带伞',
      evidence: const <Map<String, dynamic>>[
        <String, dynamic>{
          'claim': '深圳今天有雨',
          'title': '深圳天气预报',
          'url': 'https://example.com/weather',
          'source': '中国气象局',
          'snippet': '深圳今天有雨，外出建议带伞。',
        },
      ],
    );
    final server = await _startMockServer((body) async {
      final messages =
          (body['messages'] as List?)?.whereType<Map>().toList() ??
          const <Map>[];
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
    final markdown = response.displayMarkdown;
    final runArtifacts =
        (response.structuredResponse['runArtifacts'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final answerEvidenceBindings =
        (runArtifacts['answerEvidenceBindings'] as List?) ?? const <dynamic>[];

    expect(markdown, contains('[来源1](https://example.com/weather'));
    expect(answerEvidenceBindings, isNotEmpty);
    expect(
      (answerEvidenceBindings.first as Map)['url'],
      startsWith('https://example.com/weather'),
    );
    expect((answerEvidenceBindings.first as Map)['source'], equals('中国气象局'));
  });

  test(
    'keeps completed answer natural while preserving evidence bindings',
    () async {
      final planningJson = _assistantTurnJson(
        markdown: '## 中间结果\n- 我正在整理天气结论。',
        interpretation: 'phase one',
      );
      final synthesisJson = _assistantTurnJson(
        markdown:
            '## 深圳天气\n\n- 深圳今天有雨，外出建议带伞。[来源1](https://example.com/weather)',
        text: '深圳今天有雨，外出建议带伞。',
        summary: '深圳今天有雨，外出建议带伞',
        interpretation: '确认深圳今天的天气和出门准备',
        understandingSnapshot: const <String, dynamic>{
          'intentSummary': '你现在主要想确认深圳今天的天气和出门准备',
          'concernPoints': <String>['是否会下雨', '要不要带伞'],
        },
        answerProcessing: const <String, dynamic>{
          'readinessSummary': '天气实况和出门建议已经齐备',
          'keyFacts': <String>['深圳今天有雨，外出建议带伞。'],
          'missingDimensions': <String>[],
          'retrieveMoreReason': '',
        },
        evidence: const <Map<String, dynamic>>[
          <String, dynamic>{
            'evidenceId': 'weather_ev_1',
            'claim': '深圳今天有雨，外出建议带伞。',
            'title': '深圳天气预报',
            'url': 'https://example.com/weather',
            'source': '中国气象局',
            'snippet': '深圳今天有雨，外出建议带伞。',
            'text': '深圳今天有雨，外出建议带伞。',
          },
        ],
        reasoningBasis: const <Map<String, dynamic>>[
          <String, dynamic>{
            'evidenceId': 'weather_ev_1',
            'claim': '深圳今天有雨，外出建议带伞。',
            'text': '降雨信息和出门建议已经交叉确认。',
            'confidence': 0.96,
          },
        ],
      );
      final server = await _startMockServer((body) async {
        final messages =
            (body['messages'] as List?)?.whereType<Map>().toList() ??
            const <Map>[];
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
        'pa_synthesis_three_sections_',
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
          sessionId: 'three-section-answer',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳今天下不下雨，要不要带伞？'),
          ],
        ),
      );
      final markdown = response.displayMarkdown;
      final runArtifacts =
          (response.structuredResponse['runArtifacts'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final answerEvidenceBindings =
          (runArtifacts['answerEvidenceBindings'] as List?) ??
          const <dynamic>[];

      expect(markdown, contains('深圳天气'));
      expect(markdown, isNot(contains('## 深圳天气')));
      expect(markdown, isNot(contains('## 问题理解')));
      expect(markdown, isNot(contains('## 关键观点')));
      expect(markdown, isNot(contains('## 回答概要')));
      expect(markdown, contains('[来源1](https://example.com/weather'));
      expect(response.displayPlainText, contains('深圳今天有雨'));
      expect(response.displayPlainText, isNot(contains('问题理解')));
      expect(answerEvidenceBindings, isNotEmpty);
      expect(
        (answerEvidenceBindings.first as Map)['url'],
        startsWith('https://example.com/weather'),
      );
      expect(
        ((runArtifacts['understandingSnapshot'] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{})['intentSummary'],
        isNotEmpty,
      );
      expect(
        (((runArtifacts['answerProcessing'] as Map?)?.cast<String, dynamic>() ??
                    const <String, dynamic>{})['keyFacts']
                as List?) ??
            const <dynamic>[],
        isNotEmpty,
      );
    },
  );

  test('passes typed topic anchors into synthesizer.final_answer', () async {
    final tempDir = await Directory.systemTemp.createTemp(
      'pa_synthesis_anchor_vars_',
    );
    addTearDown(() async {
      await tempDir.delete(recursive: true);
    });
    final provider = _SynthesisTemplateCaptureProvider();
    final loop = _buildLoop(provider: provider, tempDirPath: tempDir.path);

    final response = await loop.run(
      const AssistantRunRequest(
        sessionId: 'synthesis-anchor-vars',
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '如果把九寨沟方向考虑进去，多给我几个备选方案'),
        ],
      ),
    );

    final vars = provider.lastSynthesisTemplateVariables;
    expect(vars, isNotNull);
    expect(vars!['userGoal'], contains('九寨沟'));
    expect(vars['entityAnchors'], contains('九寨沟'));
    expect((vars['intentGraphJson'] as String?) ?? '', contains('九寨沟'));
    expect(
      (vars['queryTasksJson'] as String?) ?? '',
      contains('candidate_space'),
    );
    expect((vars['queryTasksJson'] as String?) ?? '', contains('九寨沟'));
    expect(response.displayMarkdown, contains('九寨沟'));
  });

  test(
    'canonicalizes leaked structured prefixes before exposing final answer',
    () async {
      final planningJson = _assistantTurnJson(
        markdown: '## 中间结果\n- 我正在收敛 4 天路线判断。',
        interpretation: 'phase one',
      );
      const dirtyMarkdown =
          '[{"id":"route_recommendation","query":"九寨沟 4天 路线","dimension":"route"}]'
          '## 4天路线建议\n\n- 只有 4 天时更推荐西线。';
      final dirtySynthesisJson = jsonEncode(<String, dynamic>{
        'contractId': 'assistant_turn',
        'decision': const <String, dynamic>{'nextAction': 'answer'},
        'messageKind': 'answer',
        'userMarkdown': dirtyMarkdown,
        'result': const <String, dynamic>{
          'text':
              '[{"id":"route_recommendation","query":"九寨沟 4天 路线","dimension":"route"}]'
              '只有 4 天时更推荐西线。',
          'summary':
              '[{"id":"route_recommendation","query":"九寨沟 4天 路线","dimension":"route"}]'
              '4 天优先西线',
          'interpretation': '四天优先路线',
        },
        'evidence': const <dynamic>[],
        'reasoningBasis': const <dynamic>[],
        'selfCheck': const <String, dynamic>{},
        'diagnostics': const <String, dynamic>{},
        'modelSelfScore': const <String, dynamic>{},
        'toolCalls': const <dynamic>[],
        'slotState': const <String, dynamic>{},
        'askUser': const <String, dynamic>{},
        'subagentPlan': const <dynamic>[],
      });
      final server = await _startMockServer((body) async {
        final messages =
            (body['messages'] as List?)?.whereType<Map>().toList() ??
            const <Map>[];
        final joined = messages
            .map((item) => (item['content'] ?? '').toString())
            .join('\n');
        if (body['stream'] == true && joined.contains('领域执行结果摘要')) {
          return _MockChatResponse.sse(_chunk(dirtySynthesisJson));
        }
        return body['stream'] == true
            ? _MockChatResponse.sse(_chunk(planningJson))
            : _MockChatResponse.json(planningJson);
      });
      addTearDown(() async {
        await server.close(force: true);
      });
      final tempDir = await Directory.systemTemp.createTemp(
        'pa_synthesis_prefix_cleanup_',
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
          sessionId: 'structured-prefix-cleanup',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '如果我只有 4 天，优先哪条路线？'),
          ],
        ),
      );
      final markdown = response.displayMarkdown;

      expect(response.finalText, isNot(contains('route_recommendation')));
      expect(markdown, contains('4天路线建议'));
      expect(markdown, isNot(contains('## 4天路线建议')));
      expect(markdown, isNot(contains('## 问题理解')));
      expect(markdown, isNot(contains('## 关键观点')));
      expect(markdown, isNot(contains('## 回答概要')));
      expect(markdown, isNot(contains('route_recommendation')));
      expect(response.displayMarkdown, isNot(contains('route_recommendation')));
      expect(response.displayPlainText, contains('只有 4 天时更推荐西线'));
      expect(
        response.displayPlainText,
        isNot(contains('route_recommendation')),
      );
    },
  );
}

class _SynthesisTemplateCaptureProvider implements AssistantLlmProvider {
  Map<String, dynamic>? lastSynthesisTemplateVariables;

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
    if (templateId == 'synthesizer.final_answer') {
      lastSynthesisTemplateVariables = templateVariables;
      return AssistantModelOutput(
        text: _assistantTurnJson(
          markdown: '## 🗺️ 九寨沟备选方案\n\n- 先比较路线，再决定住宿。',
          interpretation: '九寨沟备选路线',
        ),
      );
    }
    return AssistantModelOutput(text: _planningTurnWithIntent());
  }

  String _planningTurnWithIntent() {
    return jsonEncode(<String, dynamic>{
      'contractId': 'assistant_turn',
      'decision': const <String, dynamic>{'nextAction': 'answer'},
      'messageKind': 'answer',
      'userMarkdown': '## 中间结果\n\n- 我先收拢九寨沟方向的路线备选。',
      'result': const <String, dynamic>{
        'text': '先收拢九寨沟方向的路线备选。',
        'summary': '九寨沟路线备选',
        'interpretation': 'phase one',
      },
      'intentGraph': <String, dynamic>{
        'userGoal': '把九寨沟方向考虑进去，给出备选方案',
        'problemShape': 'single_skill',
        'primarySkill': 'fallback_general_search',
        'problemClass': 'complex_reasoning',
        'answerShape': 'options',
        'requiresExternalEvidence': true,
        'entityAnchors': const <String>['九寨沟'],
        'queryTasks': const <Map<String, dynamic>>[
          <String, dynamic>{
            'id': 'candidate_space',
            'query': '九寨沟 备选路线 住宿 交通',
            'label': '候选范围',
            'dimension': 'candidate_space',
            'entityAnchors': <String>['九寨沟'],
          },
        ],
      },
      'evidence': const <dynamic>[],
      'reasoningBasis': const <dynamic>[],
      'selfCheck': const <String, dynamic>{
        'goalSatisfied': true,
        'constraintSatisfied': true,
        'safetyBoundarySatisfied': true,
        'failedItems': <String>[],
      },
      'diagnostics': const <String, dynamic>{},
      'modelSelfScore': const <String, dynamic>{'score': 90, 'reason': 'ok'},
      'toolCalls': const <dynamic>[],
      'slotState': const <String, dynamic>{},
      'askUser': const <String, dynamic>{},
      'subagentPlan': const <dynamic>[],
    });
  }
}
