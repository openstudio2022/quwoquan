import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/orchestration/local_phase_execution_owner.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/conversation/orchestration/session_manager.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/retrieval/contracts/capability_catalog.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_registry.dart';
import 'package:test/test.dart';

Map<String, dynamic> _canonicalHistoryAssistantMessage(String content) {
  const journey = AssistantJourney(
    stages: <AssistantJourneyStage>[
      AssistantJourneyStage(
        stageId: JourneyStageId.analyze,
        status: JourneyStageStatus.completed,
        order: 0,
        summary: '我先把问题边界理清',
      ),
      AssistantJourneyStage(
        stageId: JourneyStageId.search,
        status: JourneyStageStatus.completed,
        order: 1,
        summary: '我补充核对了关键来源',
      ),
      AssistantJourneyStage(
        stageId: JourneyStageId.verify,
        status: JourneyStageStatus.completed,
        order: 2,
        summary: '我交叉确认了结论',
      ),
      AssistantJourneyStage(
        stageId: JourneyStageId.answer,
        status: JourneyStageStatus.completed,
        order: 3,
        summary: '已为你整理好',
      ),
    ],
    entries: <AssistantJourneyEntry>[
      AssistantJourneyEntry(
        entryId: 'journey.analyze',
        stageId: JourneyStageId.analyze,
        kind: JourneyEntryKind.narrative,
        status: JourneyStageStatus.completed,
        order: 0,
        headline: '我先把问题边界理清',
      ),
    ],
    readiness: AssistantJourneyReadiness(finalAnswerReady: true),
  );
  return <String, dynamic>{
    'role': 'assistant',
    'content': content,
    ...buildPersistedAssistantTurnFields(
      journey: journey,
      displayMarkdown: content,
      displayPlainText: content,
      followupPrompt: '',
      actionHints: const <String>[],
      elapsedMs: 1200,
    ),
  };
}

// ─── In-memory VectorStore（无 ObjectBox 依赖，纯离线）──────────────────────
class _InMemoryVectorStore implements AssistantVectorStore {
  final List<VectorMemoryItem> _items = [];

  @override
  Future<void> upsert(VectorMemoryItem item) async {
    _items.removeWhere((e) => e.id == item.id);
    _items.add(item);
  }

  @override
  Future<List<VectorMemoryItem>> search(
    List<double> queryVector, {
    int limit = 5,
  }) async {
    return _items.take(limit).toList();
  }
}

// ─── Capturing LLM provider（记录每次 reason() 被调用时的 messages 参数）──────
class _CapturingSequenceProvider implements AssistantLlmProvider {
  _CapturingSequenceProvider(this._answers);

  final List<String> _answers;
  final List<List<Map<String, dynamic>>> capturedMessages =
      <List<Map<String, dynamic>>>[];
  int _idx = 0;

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
    capturedMessages.add(
      messages.map((m) => <String, dynamic>{...m}).toList(growable: false),
    );
    final out = _answers[_idx < _answers.length ? _idx : _answers.length - 1];
    _idx += 1;
    return AssistantModelOutput(text: out);
  }
}

class _CapturedLlmCall {
  const _CapturedLlmCall({required this.templateId, required this.messages});

  final String templateId;
  final List<Map<String, dynamic>> messages;
}

class _TemplateAwareCaptureProvider implements AssistantLlmProvider {
  final List<_CapturedLlmCall> capturedCalls = <_CapturedLlmCall>[];
  int _plannerGlobalPlanCalls = 0;

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
    capturedCalls.add(
      _CapturedLlmCall(
        templateId: templateId,
        messages: messages
            .map((item) => <String, dynamic>{...item})
            .toList(growable: false),
      ),
    );
    if (templateId == 'summarize_session') {
      return const AssistantModelOutput(text: '上一轮主要在讨论九寨沟方向备选方案。');
    }
    if (templateId == 'planner.global_plan') {
      _plannerGlobalPlanCalls += 1;
      if (_plannerGlobalPlanCalls == 1) {
        return const AssistantModelOutput(
          text:
              '{"contractVersion":"assistant_turn","messageKind":"progress","phaseId":"understanding","actionCode":"frame_problem","reasonCode":"align_goal","reasonShort":"先确认问题焦点，再组织回答。","decision":{"nextAction":"answer","confidence":0.76,"reasoning":"当前问题可直接围绕单一主题回答"},"userMarkdown":"我先聚焦问题主线，再给你结论。","result":{"text":"","summary":"进入理解阶段","interpretation":"锁定华为云盘古竞争力分析","actionHints":[]},"intentGraph":{"userGoal":"判断华为云盘古的竞争力与上云取舍","problemShape":"single_skill","primarySkill":"fallback_general_search","problemClass":"simple_qa","inferredMotive":"用户想判断华为云盘古的竞争力与上云取舍","secondarySkills":[],"queryNormalization":{"normalizedQuery":"华为云盘古 竞争力 上云取舍"},"queryTasks":[],"contextSlots":{},"globalConstraints":{"mode":"qa"},"clarificationNeeded":false},"selfCheck":{"goalSatisfied":true,"constraintSatisfied":true,"safetyBoundarySatisfied":true,"failedItems":[]},"diagnostics":{"emergedTags":[],"failedChecks":[],"parseStatus":"","notes":[]}}',
        );
      }
      return const AssistantModelOutput(
        text:
            '{"contractVersion":"assistant_turn","phaseId":"answering","actionCode":"compose_answer","reasonCode":"evidence_ready","reasonShort":"关键信息已经够用了，开始整理成答案。","decision":{"nextAction":"answer"},"messageKind":"answer","userMarkdown":"## 华为云盘古分析\\n\\n- 我只围绕当前技术判断来回答。","result":{"text":"华为云盘古分析","summary":"围绕当前技术判断作答","interpretation":"聚焦云盘古竞争力"},"selfCheck":{"goalSatisfied":true,"constraintSatisfied":true,"safetyBoundarySatisfied":true,"failedItems":[]},"diagnostics":{"emergedTags":[],"failedChecks":[],"parseStatus":"","notes":[]}}',
      );
    }
    if (templateId == 'planner.postcondition_check' ||
        templateId.contains('synthesizer') ||
        templateId.contains('final_answer') ||
        templateId.contains('output_contract.answer')) {
      return const AssistantModelOutput(
        text:
            '{"contractVersion":"assistant_turn","decision":{"nextAction":"answer"},"messageKind":"answer","phaseId":"answering","actionCode":"compose_answer","reasonCode":"evidence_ready","reasonShort":"关键信息已经够用了，开始整理成答案。","userMarkdown":"## 华为云盘古分析\\n\\n- 我只围绕当前技术判断来回答。","result":{"text":"华为云盘古分析","summary":"围绕当前技术判断作答","interpretation":"聚焦云盘古竞争力"},"selfCheck":{"goalSatisfied":true,"constraintSatisfied":true,"safetyBoundarySatisfied":true,"failedItems":[]},"diagnostics":{"emergedTags":[],"failedChecks":[],"parseStatus":"","notes":[]}}',
      );
    }
    return const AssistantModelOutput(text: '{"summary":"ok"}');
  }
}

List<String> _assistantContents(List<dynamic> history) {
  return history
      .whereType<Map>()
      .where((m) => (m['role'] as String?) == 'assistant')
      .map((m) => (m['content'] as String?) ?? '')
      .toList(growable: false);
}

void main() {
  late Directory tempDir;

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp('pa_history_guard_');
  });

  tearDown(() async {
    if (await tempDir.exists()) {
      await tempDir.delete(recursive: true);
    }
  });

  // ══════════════════════════════════════════════════════════════════════════
  // 测试 1：失败文案不得污染下一轮模型输入历史
  // ══════════════════════════════════════════════════════════════════════════
  group('G1 — 失败/降级文案不得污染下一轮模型输入历史', () {
    test('HTTP 400 错误文案不得进入第二轮 messages', () async {
      // 第一轮 LLM 返回降级文本（模拟 HTTP 400），第二轮正常
      late _CapturingSequenceProvider provider;
      final runtime = ReactRuntime(
        llmProvider: provider = _CapturingSequenceProvider(<String>[
          '模型调用失败: HTTP 400 - Param Incorrect',
          '{"contractVersion":"assistant_turn","messageKind":"answer","phaseId":"answering","actionCode":"compose_answer","reasonCode":"evidence_ready","reasonShort":"信息已经够用了，可以直接回答。","decision":{"nextAction":"answer"},"userMarkdown":"## 深圳天气\\n\\n- 今天晴，约25°C。","result":{"text":"深圳今天晴，25°C","summary":"深圳天气晴朗","interpretation":"给出天气结论"},"selfCheck":{"goalSatisfied":true,"constraintSatisfied":true,"safetyBoundarySatisfied":true,"failedItems":[]},"diagnostics":{"emergedTags":[],"failedChecks":[],"parseStatus":"","notes":[]}}',
        ]),
        toolRegistry: AssistantToolRegistry(),
      );
      final loop = LocalPhaseExecutionOwner(
        runtime,
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions.json',
        ),
        memoryRepository: AssistantMemoryRepository(_InMemoryVectorStore()),
      );

      // 第一轮
      await loop.run(
        const AssistantRunRequest(
          sessionId: 'assistant',
          messages: [AssistantRunMessage(role: 'user', content: '深圳天气')],
        ),
      );

      // 第二轮
      await loop.run(
        const AssistantRunRequest(
          sessionId: 'assistant',
          messages: [AssistantRunMessage(role: 'user', content: '那明天呢')],
        ),
      );

      expect(provider.capturedMessages.length, greaterThanOrEqualTo(2));
      final secondCallMsgs = provider.capturedMessages[1];
      final polluted = secondCallMsgs.any((m) {
        final c = (m['content'] as String?) ?? '';
        return c.contains('模型调用失败: HTTP 400') || c.contains('助手暂时不可用');
      });
      expect(
        polluted,
        isFalse,
        reason: '降级文案"模型调用失败: HTTP 400"不应出现在下一轮模型输入 messages 中',
      );
    });

    test('所有已知降级前缀均被阻断', () async {
      final degradedTexts = [
        '模型调用失败: HTTP 400 - Param Incorrect',
        '模型调用异常: timeout',
        '助手暂时不可用，请稍后重试。',
        '当前模型服务不可用',
        '模板渲染失败: planner.global_plan 模板缺失或为空。',
      ];

      for (final degraded in degradedTexts) {
        final tempSub = await Directory.systemTemp.createTemp(
          'pa_degrade_guard_',
        );
        try {
          late _CapturingSequenceProvider provider;
          final runtime = ReactRuntime(
            llmProvider: provider = _CapturingSequenceProvider([
              degraded,
              '正常答案',
            ]),
            toolRegistry: AssistantToolRegistry(),
          );
          final loop = LocalPhaseExecutionOwner(
            runtime,
            sessionManager: AssistantSessionManager(
              storagePath: '${tempSub.path}/sessions.json',
            ),
            memoryRepository: AssistantMemoryRepository(_InMemoryVectorStore()),
          );

          await loop.run(
            const AssistantRunRequest(
              sessionId: 'assistant',
              messages: [AssistantRunMessage(role: 'user', content: '问题1')],
            ),
          );
          await loop.run(
            const AssistantRunRequest(
              sessionId: 'assistant',
              messages: [AssistantRunMessage(role: 'user', content: '问题2')],
            ),
          );

          if (provider.capturedMessages.length >= 2) {
            final secondMsgs = provider.capturedMessages[1];
            final polluted = secondMsgs.any((m) {
              final c = (m['content'] as String?) ?? '';
              return c == degraded;
            });
            expect(
              polluted,
              isFalse,
              reason: '降级文本"$degraded"不应出现在第二轮 messages 中',
            );
          }
        } finally {
          await tempSub.delete(recursive: true);
        }
      }
    });
  });

  // ══════════════════════════════════════════════════════════════════════════
  // 测试 2：sessions.json 加载时自动清洗历史降级消息
  // ══════════════════════════════════════════════════════════════════════════
  group('G2 — SessionManager 加载时自动清洗降级消息', () {
    test('旧版 sessions.json 含污染 assistant 历史时，load() 后应直接清空', () async {
      final sessionsPath = '${tempDir.path}/sessions.json';
      final pollutedData = {
        'version': 'v2',
        'sessions': {
          'assistant': [
            {'role': 'user', 'content': '深圳天气'},
            {
              'role': 'assistant',
              'content': '模型调用失败: HTTP 400 - Param Incorrect',
            },
            {'role': 'user', 'content': '那明天呢'},
            {'role': 'assistant', 'content': '助手暂时不可用，请稍后重试。'},
          ],
        },
      };
      await File(sessionsPath).writeAsString(jsonEncode(pollutedData));

      final manager = AssistantSessionManager(storagePath: sessionsPath);
      await manager.load();

      final history = manager.getOrCreateSession('assistant');
      final assistantContents = _assistantContents(history);

      expect(
        assistantContents,
        isEmpty,
        reason: '旧版历史不再兼容，应在 load() 时整体清空',
      );
    });

    test('canonical v3 assistant 消息会被保留', () async {
      final sessionsPath = '${tempDir.path}/sessions_normal.json';
      final normalData = {
        'version': assistantHistoryStorageVersion,
        'sessions': {
          'assistant': [
            {'role': 'user', 'content': '深圳天气'},
            _canonicalHistoryAssistantMessage('深圳今天晴朗，气温25°C。'),
            {'role': 'user', 'content': '明天呢'},
            _canonicalHistoryAssistantMessage('明天多云，气温22-27°C。'),
          ],
        },
      };
      await File(sessionsPath).writeAsString(jsonEncode(normalData));

      final manager = AssistantSessionManager(storagePath: sessionsPath);
      await manager.load();

      final history = manager.getOrCreateSession('assistant');
      final assistantContents = _assistantContents(history);

      expect(assistantContents.length, 2, reason: 'canonical assistant 消息不应被删除');
      expect(assistantContents[0], '深圳今天晴朗，气温25°C。');
    });
  });

  // ══════════════════════════════════════════════════════════════════════════
  // 测试 3：summarizeRecent 不输出 JSON 原文
  // ══════════════════════════════════════════════════════════════════════════
  group('G3 — summarizeRecent 不得输出 JSON 格式的 assistant_turn 原文', () {
    test('session 含 JSON envelope 时，summarizeRecent 输出纯文本', () {
      final manager = AssistantSessionManager(
        storagePath: '${tempDir.path}/sessions.json',
      );
      manager.appendMessage(sessionId: 'test', role: 'user', content: '深圳天气');
      manager.appendMessage(
        sessionId: 'test',
        role: 'assistant',
        content:
            '{"contractVersion":"assistant_turn","messageKind":"answer","phaseId":"answering","actionCode":"compose_answer","reasonCode":"evidence_ready","reasonShort":"信息已经够用了，可以直接回答。","decision":{"nextAction":"answer"},"userMarkdown":"## 深圳天气\\n\\n- 今天晴，约25°C。","result":{"text":"深圳今天晴，25°C。","summary":"深圳天气晴朗","interpretation":"给出天气结论"},"selfCheck":{"goalSatisfied":true,"constraintSatisfied":true,"safetyBoundarySatisfied":true,"failedItems":[]},"diagnostics":{"emergedTags":[],"failedChecks":[],"parseStatus":"","notes":[]}}',
      );

      final summary = manager.summarizeRecent('test');
      expect(
        summary,
        isNot(contains('contractVersion')),
        reason: 'summarizeRecent 不得输出 JSON 原文',
      );
      expect(
        summary,
        isNot(contains('assistant_turn')),
        reason: 'summarizeRecent 不得输出 JSON 原文',
      );
    });

    test('session 含降级文本时，summarizeRecent 跳过该条', () {
      final manager = AssistantSessionManager(
        storagePath: '${tempDir.path}/sessions.json',
      );
      manager.appendMessage(sessionId: 'test', role: 'user', content: '深圳天气');
      manager.appendMessage(
        sessionId: 'test',
        role: 'assistant',
        content: '模型调用失败: HTTP 400 - Param Incorrect',
      );
      manager.appendMessage(sessionId: 'test', role: 'user', content: '那明天呢');

      final summary = manager.summarizeRecent('test');
      expect(
        summary,
        isNot(contains('模型调用失败')),
        reason: 'summarizeRecent 不得输出降级文本',
      );
      expect(
        summary,
        isNot(contains('HTTP 400')),
        reason: 'summarizeRecent 不得输出 HTTP 400 错误信息',
      );
    });
  });

  // ══════════════════════════════════════════════════════════════════════════
  // 测试 4：新问题不得继承旧旅行上下文
  // ══════════════════════════════════════════════════════════════════════════
  group('G4 — 新问题不得继承旧旅行上下文', () {
    test(
      '技术问题不会把 session history / long-term recall / gps 提前注入 planner',
      () async {
        final provider = _TemplateAwareCaptureProvider();
        final runtime = ReactRuntime(
          llmProvider: provider,
          toolRegistry: AssistantToolRegistry(),
        );
        final sessionManager = AssistantSessionManager(
          storagePath: '${tempDir.path}/g4_sessions.json',
        );
        final memoryRepository = AssistantMemoryRepository(
          _InMemoryVectorStore(),
        );
        await sessionManager.load();
        sessionManager.appendMessage(
          sessionId: 'shared_session',
          role: 'user',
          content: '如果把九寨沟方向考虑进去，多给我几个备选方案',
        );
        sessionManager.appendMessage(
          sessionId: 'shared_session',
          role: 'assistant',
          content: '九寨沟方向备选方案：沟口、川主寺、松潘古城',
        );
        sessionManager.updateSessionTopicSummary(
          sessionId: 'shared_session',
          latestUserQuery: '如果把九寨沟方向考虑进去，多给我几个备选方案',
          latestAssistantReply: '九寨沟方向备选方案：沟口、川主寺、松潘古城',
        );
        await memoryRepository.rememberText(
          id: 'travel_memory',
          text: '九寨沟方向备选方案：沟口、川主寺、松潘古城',
        );

        final loop = LocalPhaseExecutionOwner(
          runtime,
          sessionManager: sessionManager,
          memoryRepository: memoryRepository,
        );
        await loop.run(
          const AssistantRunRequest(
            sessionId: 'shared_session',
            capabilityCatalog: <String>[
              AssistantCapabilityCatalog.chatRecent,
              AssistantCapabilityCatalog.chatLongterm,
            ],
            gpsLocation: <String, dynamic>{'city': '阿坝州'},
            messages: <AssistantRunMessage>[
              AssistantRunMessage(
                role: 'user',
                content:
                    '华为云盘古是否落后了，华为在AI竞争中是否落伍了，要在华为云上开租电商系统使用华为AI相比阿里字节有啥优势',
              ),
            ],
          ),
        );

        final plannerTranscript = provider.capturedCalls
            .where((call) => call.templateId == 'planner.global_plan')
            .expand((call) => call.messages)
            .map((item) => (item['content'] ?? '').toString())
            .join('\n');
        expect(plannerTranscript, isNotEmpty);
        for (final forbidden in const <String>[
          '<session_history>',
          '<memory_recall>',
          '"historySummarySnippet"',
          '"recentCityMentions"',
          '"gpsCity"',
          '九寨沟方向备选方案',
          '阿坝州',
        ]) {
          expect(
            plannerTranscript.contains(forbidden),
            isFalse,
            reason: '技术问题的 planner 输入不应继承旧旅行上下文: $forbidden',
          );
        }
      },
    );
  });
}
