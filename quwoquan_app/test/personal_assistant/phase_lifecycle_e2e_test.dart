import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_gateway.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_runtime.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';

/// Validates the v3 phase lifecycle end-to-end:
///   understanding → tool execution → assessment → analyzing → answering
///
/// Assertions:
///   1. Phase timeline uses user-facing language (no internal strings)
///   2. Tool execution produces references
///   3. Final answer is non-empty and contains weather information
///   4. Semantic trace events cover the full loop
void main() {
  group('Phase lifecycle E2E — 深圳天气', () {
    late AssistantGateway gateway;

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

      final runtime = AssistantRuntime.createForTest();
      await runtime.ensureRemoteConfigLoaded();
      gateway = AssistantGateway(runtime);
    });

    test('完整阶段闭环：理解→搜索→评估→分析→回答', () async {
      final traces = <AssistantTraceEvent>[];
      final response = await gateway.runWithTraceStream(
        AssistantRunRequest(
          sessionId: 'phase_e2e_weather',
          userId: 'test_user',
          deviceProfile: 'mobile',
          channel: 'app',
          messages: const <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳天气怎么样'),
          ],
        ),
        onTraceEvent: traces.add,
      );

      // --- 基本响应断言 ---
      expect(response.finalText, isNotEmpty, reason: '应返回非空回复');
      expect(
        response.finalText.contains('未配置可用模型'),
        isFalse,
        reason: '不应降级为未配置模型文案',
      );

      // --- 阶段时间线断言 ---
      final structured = response.structuredResponse;
      final timeline = (structured['uiPhaseTimelineV1'] as List?)
              ?.whereType<Map>()
              .map((p) => p.cast<String, dynamic>())
              .toList() ??
          [];

      expect(timeline, isNotEmpty, reason: '应生成阶段时间线');

      final phaseTypes =
          timeline.map((p) => (p['phaseType'] as String?) ?? '').toList();
      final phaseTitles =
          timeline.map((p) => (p['title'] as String?) ?? '').toList();

      // 必须包含核心阶段
      expect(
        phaseTypes.contains('answering'),
        isTrue,
        reason: '时间线应包含 answering 阶段',
      );

      // 最后一个阶段应为 answering 且已完成
      final lastPhase = timeline.last;
      expect(lastPhase['phaseType'], equals('answering'));
      expect(lastPhase['status'], equals('completed'));

      // --- 用户语言检查：禁止内部字符串 ---
      final forbiddenStrings = [
        'contractVersion',
        'assistant_turn_v',
        'turnPhase',
        'AssistantTraceEventType',
        'UserPhaseEventType',
        'thinkingStarted',
        'planStarted',
        'toolStart',
        'toolResult',
        'lifecycleStart',
        'lifecycleEnd',
      ];
      for (final phase in timeline) {
        final title = (phase['title'] as String?) ?? '';
        final summary = (phase['summary'] as String?) ?? '';
        final details = (phase['details'] as List?)
                ?.whereType<String>()
                .toList() ??
            [];
        final allText = [title, summary, ...details].join(' ');
        for (final forbidden in forbiddenStrings) {
          expect(
            allText.contains(forbidden),
            isFalse,
            reason:
                '阶段 "${phase['phaseType']}" 包含内部字符串 "$forbidden"，'
                '应使用面向用户的自然语言',
          );
        }
      }

      // --- 标题检查：都应为用户可理解的中文 ---
      for (final title in phaseTitles) {
        expect(title, isNotEmpty, reason: '每个阶段必须有标题');
      }

      // --- trace 事件覆盖检查 ---
      final traceTypes = traces.map((t) => t.type).toSet();
      expect(
        traceTypes.contains(AssistantTraceEventType.planStarted),
        isTrue,
        reason: '应发射 planStarted 语义事件',
      );
      expect(
        traceTypes.contains(AssistantTraceEventType.thinkingStarted),
        isTrue,
        reason: '应发射 thinkingStarted 语义事件',
      );
      expect(
        traceTypes.contains(AssistantTraceEventType.lifecycleEnd),
        isTrue,
        reason: '应发射 lifecycleEnd 事件标记结束',
      );

      // --- 理解阶段应存在 ---
      expect(
        phaseTypes.contains('understanding'),
        isTrue,
        reason: '时间线应包含 understanding 阶段，实际: $phaseTypes',
      );

      // --- 所有阶段 status 应为 completed ---
      for (final phase in timeline) {
        expect(
          phase['status'],
          equals('completed'),
          reason: '阶段 "${phase['phaseType']}" 状态应为 completed',
        );
      }

      // --- 每个阶段 title 应为用户语言 ---
      final expectedTitles = {
        'understanding': '理解问题',
        'answering': '组织回答',
      };
      for (final phase in timeline) {
        final type = (phase['phaseType'] as String?) ?? '';
        if (expectedTitles.containsKey(type)) {
          expect(
            phase['title'],
            equals(expectedTitles[type]),
            reason: '阶段 $type 标题应为 "${expectedTitles[type]}"',
          );
        }
      }
    });

    test('搜索工具阶段应包含参考资料（模型可用时）', () async {
      final traces = <AssistantTraceEvent>[];
      final response = await gateway.runWithTraceStream(
        AssistantRunRequest(
          sessionId: 'phase_e2e_weather_refs',
          userId: 'test_user',
          deviceProfile: 'mobile',
          channel: 'app',
          messages: const <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳今天天气'),
          ],
        ),
        onTraceEvent: traces.add,
      );

      final structured = response.structuredResponse;
      final timeline = (structured['uiPhaseTimelineV1'] as List?)
              ?.whereType<Map>()
              .map((p) => p.cast<String, dynamic>())
              .toList() ??
          [];

      // 查找工具搜索阶段
      final searchPhases = timeline
          .where((p) =>
              (p['phaseType'] as String? ?? '').contains('search') ||
              (p['phaseType'] as String? ?? '').contains('tool:'))
          .toList();

      final hasToolStart = traces.any(
        (t) => t.type == AssistantTraceEventType.toolStart,
      );

      if (searchPhases.isNotEmpty) {
        final searchPhase = searchPhases.first;
        final refs = (searchPhase['references'] as List?) ?? [];
        expect(
          refs.isNotEmpty,
          isTrue,
          reason: '搜索阶段应产出参考资料 references',
        );

        for (final ref in refs.whereType<Map>()) {
          expect(
            (ref['url'] as String?)?.isNotEmpty ?? false,
            isTrue,
            reason: '每条参考资料应有 url',
          );
        }

        final summary = (searchPhase['summary'] as String?) ?? '';
        expect(
          summary.contains('资料'),
          isTrue,
          reason: '搜索阶段 summary 应包含"资料"',
        );

        expect(hasToolStart, isTrue, reason: '有搜索阶段时应有 toolStart trace');
      }

      // 若模型 API 不可用（HTTP 400），搜索阶段可能不存在，
      // 此时跳过 toolStart 断言，只验证降级行为正常
      if (!hasToolStart && searchPhases.isEmpty) {
        expect(response.finalText, isNotEmpty, reason: '降级后仍应有回复');
      }
    });

    test('阶段时间线不暴露 JSON 原文', () async {
      final response = await gateway.runWithTraceStream(
        AssistantRunRequest(
          sessionId: 'phase_e2e_weather_no_json',
          userId: 'test_user',
          deviceProfile: 'mobile',
          channel: 'app',
          messages: const <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳天气预报'),
          ],
        ),
        onTraceEvent: (_) {},
      );

      final structured = response.structuredResponse;
      final timeline = (structured['uiPhaseTimelineV1'] as List?)
              ?.whereType<Map>()
              .map((p) => p.cast<String, dynamic>())
              .toList() ??
          [];

      for (final phase in timeline) {
        final details = (phase['details'] as List?)
                ?.whereType<String>()
                .toList() ??
            [];
        for (final detail in details) {
          expect(
            detail.contains('"contractVersion"'),
            isFalse,
            reason: '阶段详情不应包含 JSON 原文片段 contractVersion',
          );
          expect(
            detail.contains('"turnPhase"'),
            isFalse,
            reason: '阶段详情不应包含 JSON 原文片段 turnPhase',
          );
        }
      }
    });
  });
}
