import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/personal_assistant/engine/agent_loop.dart';
import 'package:quwoquan_app/personal_assistant/engine/llm_provider.dart';
import 'package:quwoquan_app/personal_assistant/engine/react_runtime.dart';
import 'package:quwoquan_app/personal_assistant/engine/session_manager.dart';
import 'package:quwoquan_app/personal_assistant/memory/memory_repository.dart';
import 'package:quwoquan_app/personal_assistant/memory/vector_store.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_registry.dart';
import 'package:test/test.dart';

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
          '{"userMarkdown":"深圳今天晴，25°C","decision":{"nextAction":"answer"}}',
        ]),
        toolRegistry: AssistantToolRegistry(),
      );
      final loop = PersonalAssistantAgentLoop(
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
          final loop = PersonalAssistantAgentLoop(
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
    test('磁盘 sessions.json 含降级消息时，load() 后应自动过滤', () async {
      // 直接写一个含污染消息的 sessions.json
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
        everyElement(
          isNot(
            anyOf(
              contains('模型调用失败'),
              contains('助手暂时不可用'),
              contains('HTTP 400'),
            ),
          ),
        ),
        reason: '从磁盘加载后，所有降级 assistant 消息应已被过滤',
      );
    });

    test('正常 assistant 消息不被误删', () async {
      // 直接写一个正常 sessions.json
      final sessionsPath = '${tempDir.path}/sessions_normal.json';
      final normalData = {
        'version': 'v2',
        'sessions': {
          'assistant': [
            {'role': 'user', 'content': '深圳天气'},
            {'role': 'assistant', 'content': '深圳今天晴朗，气温25°C。'},
            {'role': 'user', 'content': '明天呢'},
            {'role': 'assistant', 'content': '明天多云，气温22-27°C。'},
          ],
        },
      };
      await File(sessionsPath).writeAsString(jsonEncode(normalData));

      final manager = AssistantSessionManager(storagePath: sessionsPath);
      await manager.load();

      final history = manager.getOrCreateSession('assistant');
      final assistantContents = _assistantContents(history);

      expect(assistantContents.length, 2, reason: '正常 assistant 消息不应被删除');
      expect(assistantContents[0], '深圳今天晴朗，气温25°C。');
    });
  });

  // ══════════════════════════════════════════════════════════════════════════
  // 测试 3：summarizeRecent 不输出 JSON 原文
  // ══════════════════════════════════════════════════════════════════════════
  group('G3 — summarizeRecent 不得输出 JSON 格式的 assistant_turn_v2 原文', () {
    test('session 含 JSON envelope 时，summarizeRecent 输出纯文本', () {
      final manager = AssistantSessionManager(
        storagePath: '${tempDir.path}/sessions.json',
      );
      manager.appendMessage(sessionId: 'test', role: 'user', content: '深圳天气');
      manager.appendMessage(
        sessionId: 'test',
        role: 'assistant',
        content:
            '{"contractVersion":"assistant_turn_v2","decision":{"nextAction":"answer"},"userMarkdown":"深圳今天晴，25°C。"}',
      );

      final summary = manager.summarizeRecent('test');
      expect(
        summary,
        isNot(contains('contractVersion')),
        reason: 'summarizeRecent 不得输出 JSON 原文',
      );
      expect(
        summary,
        isNot(contains('assistant_turn_v2')),
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
}
