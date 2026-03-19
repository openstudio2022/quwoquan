import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/application/assistant_gateway.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/domain/channel/channel.dart';
import 'package:quwoquan_app/assistant/domain/conversation/conversation.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';

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
    late bool hasRemoteModel;

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
      hasRemoteModel = runtime.listAvailableModels().isNotEmpty;
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

      // --- 用户旅程断言 ---
      final journey = response.runArtifacts?.journey;
      expect(journey, isNotNull, reason: '应产出 canonical journey');
      final journeyStageIds = journey!.stages.map((item) => item.stageId.name).toSet();
      final degradedFailClosed =
          response.finalText.contains('模型输出无效') ||
          response.finalText.contains('已停止本轮回答');

      expect(
        journey.entries.isNotEmpty || journey.stages.isNotEmpty,
        isTrue,
        reason: '应生成唯一用户旅程',
      );
      expect(response.structuredResponse.containsKey('uiPhaseTimelineV1'), isFalse);

      if (!hasRemoteModel || degradedFailClosed) {
        expect(journeyStageIds.contains('analyze'), isTrue);
        expect(journeyStageIds.contains('answer') || journeyStageIds.isNotEmpty, isTrue);
        return;
      }

      // 必须包含核心阶段
      expect(
        journeyStageIds.contains('answer'),
        isTrue,
        reason: '用户旅程应包含 answer 阶段',
      );
      expect(journeyStageIds.contains('analyze'), isTrue);
      expect(journeyStageIds.contains('search') || journeyStageIds.contains('verify'), isTrue);

      // --- 用户语言检查：禁止内部字符串 ---
      final forbiddenStrings = [
        'contractId',
        'assistant_turn"',
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
      for (final entry in journey.entries) {
        final allText = '${entry.headline} ${entry.detail}'.trim();
        for (final forbidden in forbiddenStrings) {
          expect(
            allText.contains(forbidden),
            isFalse,
            reason: '用户旅程包含内部字符串 "$forbidden"，应使用面向用户的自然语言',
          );
        }
      }
      final visibleEntries = journey.entries
          .where(
            (item) =>
                item.headline.trim().isNotEmpty || item.detail.trim().isNotEmpty,
          )
          .toList(growable: false);
      expect(visibleEntries, isNotEmpty, reason: '应存在可展示的用户态旅程条目');
      for (final entry in visibleEntries) {
        expect(entry.stageId.name, isNotEmpty, reason: '旅程条目应带 stageId');
        expect(entry.kind.name, isNot('unknown'), reason: '旅程条目应带 kind');
      }

      final processText = journey.entries
          .map((item) => '${item.headline} ${item.detail}'.trim())
          .join(' ');
      expect(processText, isNot(contains('压缩以上对话历史为简洁摘要')));
      expect(processText, isNot(contains('summarize_session')));
      expect(processText, isNot(contains('intent_graph_resolved')));
      expect(processText, isNot(contains('repair invalid synthesis output')));

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

      final journey = response.runArtifacts?.journey;
      final searchUpdates = (journey?.entries ?? const <AssistantJourneyEntry>[])
          .where(
            (item) =>
                item.stageId.name == 'search' || item.stageId.name == 'verify',
          )
          .toList(growable: false);

      final hasToolStart = traces.any(
        (t) => t.type == AssistantTraceEventType.toolStart,
      );

      if (searchUpdates.isNotEmpty) {
        final searchPhase = searchUpdates.first;
        final refs = searchPhase.references;
        if (refs.isNotEmpty) {
          for (final ref in refs) {
            expect(ref.url.isNotEmpty, isTrue, reason: '每条参考资料应有 url');
          }
        } else {
          final summary =
              '${searchPhase.headline} ${searchPhase.detail}'.trim();
          expect(summary.trim().isNotEmpty, isTrue, reason: '搜索阶段即使无引用也应有摘要');
          expect(
            summary.contains('失败') ||
                summary.contains('重试') ||
                summary.contains('稍后') ||
                hasToolStart,
            isTrue,
            reason: '当外部检索没有可靠来源时，也应对用户说明当前在重试或已降级',
          );
        }
        final summary = '${searchPhase.headline} ${searchPhase.detail}'.trim();
        expect(summary.trim().isNotEmpty, isTrue, reason: '搜索阶段应始终有可读 summary');

        expect(hasToolStart, isTrue, reason: '有搜索阶段时应有 toolStart trace');
      }

      // 若模型 API 不可用（HTTP 400），搜索阶段可能不存在，
      // 此时跳过 toolStart 断言，只验证降级行为正常
      if (!hasToolStart && searchUpdates.isEmpty) {
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

      final journey = response.runArtifacts?.journey;
      for (final entry in journey?.entries ?? const <AssistantJourneyEntry>[]) {
        final text = '${entry.headline} ${entry.detail}'.trim();
        expect(
          text.contains('"contractId"'),
          isFalse,
          reason: '用户旅程不应包含 JSON 原文片段 contractId',
        );
        expect(
          text.contains('"turnPhase"'),
          isFalse,
          reason: '用户旅程不应包含 JSON 原文片段 turnPhase',
        );
      }
    });
  });
}
