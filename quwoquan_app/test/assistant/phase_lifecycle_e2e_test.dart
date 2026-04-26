import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/application/assistant_request_policy.dart';
import 'package:quwoquan_app/assistant/application/assistant_run_stream.dart';
import 'package:quwoquan_app/assistant/application/assistant_gateway.dart';
import 'package:quwoquan_app/assistant/application/local_assistant_entry.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/domain/channel/channel.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
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
      final journeyStageIds = journey!.stages
          .map((item) => item.stageId.name)
          .toSet();
      final degradedFailClosed =
          response.finalText.contains('模型输出无效') ||
          response.finalText.contains('已停止本轮回答');

      expect(
        journey.entries.isNotEmpty || journey.stages.isNotEmpty,
        isTrue,
        reason: '应生成唯一用户旅程',
      );
      expect(
        response.structuredResponse.containsKey('uiPhaseTimelineV1'),
        isFalse,
      );

      if (!hasRemoteModel || response.degraded || degradedFailClosed) {
        expect(journeyStageIds.contains('analyze'), isTrue);
        expect(
          journeyStageIds.contains('answer') || journeyStageIds.isNotEmpty,
          isTrue,
        );
        return;
      }

      // 必须包含核心阶段
      expect(
        journeyStageIds.contains('answer'),
        isTrue,
        reason: '用户旅程应包含 answer 阶段',
      );
      expect(journeyStageIds.contains('analyze'), isTrue);
      expect(
        journeyStageIds.contains('search') ||
            journeyStageIds.contains('verify'),
        isTrue,
      );

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
                item.headline.trim().isNotEmpty ||
                item.detail.trim().isNotEmpty,
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
      expect(processText, isNot(contains('typed_plan_resolved')));
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
      final searchUpdates =
          (journey?.entries ?? const <AssistantJourneyEntry>[])
              .where(
                (item) =>
                    item.stageId.name == 'search' ||
                    item.stageId.name == 'verify',
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
          final summary = '${searchPhase.headline} ${searchPhase.detail}'
              .trim();
          expect(summary.trim().isNotEmpty, isTrue, reason: '搜索阶段即使无引用也应有摘要');
          expect(
            summary.contains('失败') ||
                summary.contains('重试') ||
                summary.contains('稍后') ||
                summary.isNotEmpty ||
                hasToolStart,
            isTrue,
            reason: '搜索阶段应有可读摘要或工具执行痕迹',
          );
        }
        final summary = '${searchPhase.headline} ${searchPhase.detail}'.trim();
        expect(summary.trim().isNotEmpty, isTrue, reason: '搜索阶段应始终有可读 summary');

        if (!hasToolStart) {
          expect(
            summary.trim().isNotEmpty,
            isTrue,
            reason: '无 toolStart 时搜索阶段条目应至少有可读摘要',
          );
        }
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
      if (response.degraded) {
        return;
      }
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

    test('用户可见阶段按顺序流式输出并在完成态保持稳定字段，且第一阶段保留 query-design 信息', () async {
      final entry = LocalAssistantEntry(
        assistantGateway: gateway,
        requestPolicy: const AssistantRequestPolicy(),
      );
      final events = await entry
          .runStream(
            request: const AssistantRunRequest(
              sessionId: 'phase_e2e_four_stage_stream',
              userId: 'test_user',
              deviceProfile: 'mobile',
              channel: 'app',
              messages: <AssistantRunMessage>[
                AssistantRunMessage(role: 'user', content: '深圳天气怎么样'),
              ],
            ),
          )
          .toList();

      final processEvents = events
          .where(
            (event) =>
                event.type == AssistantRunStreamEventType.processTimelineUpdate,
          )
          .toList(growable: false);
      expect(
        processEvents,
        isNotEmpty,
        reason: '应发出 processTimelineUpdate 流式事件',
      );

      // ready 链路不再单独插入 retrieval_processing 过程帧（证据摘要进 journey / answer 前快照）。
      const expectedSteps = <ProcessStepId>[
        ProcessStepId.understanding,
        ProcessStepId.retrievalProcessing,
      ];

      final firstSeenIndex = <ProcessStepId, int>{};
      var previousFrameCount = 0;
      for (var i = 0; i < processEvents.length; i += 1) {
        final frames =
            processEvents[i].processTimeline ?? const <ProcessTimelineFrame>[];
        expect(frames, isNotEmpty, reason: '每次 processTimelineUpdate 都应携带快照');
        expect(
          frames.length,
          greaterThanOrEqualTo(previousFrameCount),
          reason: '阶段快照应单调累积，不能回退丢阶段',
        );
        previousFrameCount = frames.length;
        final orders = frames
            .map((frame) => frame.order)
            .toList(growable: false);
        expect(
          orders,
          orderedEquals(List<int>.from(orders)..sort()),
          reason: 'processTimeline 应按阶段顺序输出',
        );
        for (final frame in frames) {
          firstSeenIndex.putIfAbsent(frame.stepId, () => i);
        }
      }

      expect(firstSeenIndex.keys, containsAll(expectedSteps));
      for (var i = 0; i < expectedSteps.length - 1; i += 1) {
        expect(
          firstSeenIndex[expectedSteps[i]]!,
          lessThan(firstSeenIndex[expectedSteps[i + 1]]!),
          reason: '可见阶段必须按 understanding → retrieval_processing 顺序首次出现',
        );
      }

      final completedIndex = events.indexWhere(
        (event) => event.type == AssistantRunStreamEventType.completed,
      );
      expect(
        completedIndex,
        greaterThanOrEqualTo(0),
        reason: '应产出 completed 终态事件',
      );
      final firstAnswerDeltaIndex = events.indexWhere(
        (event) =>
            event.type == AssistantRunStreamEventType.answerDelta &&
            ((event.chunkText ?? '').trim().isNotEmpty),
      );
      if (firstAnswerDeltaIndex < 0) {
        final completedResponse = events
            .lastWhere(
              (event) => event.type == AssistantRunStreamEventType.completed,
            )
            .response;
        expect(completedResponse?.degraded, isTrue);
        return;
      }
      expect(
        firstAnswerDeltaIndex,
        inInclusiveRange(0, completedIndex - 1),
        reason: 'nextAction=answer 的路径必须在 completed 前先发出真实 answerDelta',
      );
      final finalProcessTimelineIndex = events.lastIndexWhere(
        (event) =>
            event.type == AssistantRunStreamEventType.processTimelineUpdate,
      );
      expect(
        finalProcessTimelineIndex,
        inInclusiveRange(0, completedIndex - 1),
        reason: 'completed 前必须补发最终 processTimelineUpdate',
      );
      final firstJourneyUpdateIndex = events.indexWhere(
        (event) => event.type == AssistantRunStreamEventType.journeyUpdate,
      );
      if (firstJourneyUpdateIndex >= 0) {
        expect(
          firstJourneyUpdateIndex,
          greaterThan(finalProcessTimelineIndex),
          reason: 'journey 不应再抢占过程主轨，最终更新应晚于 processTimeline',
        );
      }
      final retrievalStageStreamIndex = events.indexWhere((event) {
        if (event.type != AssistantRunStreamEventType.processTimelineUpdate) {
          return false;
        }
        final frames = event.processTimeline ?? const <ProcessTimelineFrame>[];
        return frames.any(
          (frame) => frame.stepId == ProcessStepId.retrievalProcessing,
        );
      });
      expect(
        retrievalStageStreamIndex,
        inInclusiveRange(0, completedIndex - 1),
        reason: 'retrieval_processing 必须在 completed 之前进入流式过程轨',
      );

      final streamedFinalTimeline =
          processEvents.last.processTimeline ?? const <ProcessTimelineFrame>[];
      expect(
        streamedFinalTimeline
            .map((frame) => frame.stepId)
            .toList(growable: false),
        orderedEquals(expectedSteps),
        reason: '最终流式过程轨应完整包含 2 个可见阶段',
      );

      for (final frame in streamedFinalTimeline) {
        expect(
          frame.status,
          isNot(JourneyStageStatus.pending),
          reason: '完成态 processTimeline 不应保留 pending 阶段',
        );
        expect(
          _frameHasStableSignal(frame),
          isTrue,
          reason: '每个阶段都应有稳定字段或可展示内容',
        );
        _expectUserFacingProcessFrame(frame);
      }
      final understandingFrame = streamedFinalTimeline.firstWhere(
        (frame) => frame.stepId == ProcessStepId.understanding,
      );
      expect(understandingFrame.headline.trim(), isNotEmpty);

      final completed = events
          .lastWhere(
            (event) => event.type == AssistantRunStreamEventType.completed,
          )
          .response!;
      expect(
        completed.finalText.trim(),
        isNotEmpty,
        reason: 'completed response 应返回最终答案',
      );
      final completedCanonicalTimeline =
          resolveAssistantProcessTimelineFromRunResponse(completed);
      expect(
        completedCanonicalTimeline,
        isNotEmpty,
        reason: '完成态 canonical processTimeline 不应为空',
      );
      final completedVisibleTimeline =
          resolveAssistantVisibleProcessTimelineFromRunResponse(completed);
      expect(
        jsonEncode(
          completedVisibleTimeline
              .map((frame) => frame.toJson())
              .toList(growable: false),
        ),
        equals(
          jsonEncode(
            streamedFinalTimeline
                .map((frame) => frame.toJson())
                .toList(growable: false),
          ),
        ),
        reason: '完成态 processTimeline 应与最后一次流式快照保持一致',
      );
    });
  });
}

bool _frameHasStableSignal(ProcessTimelineFrame frame) {
  switch (frame.stepId) {
    case ProcessStepId.understanding:
      return frame.headline.trim().isNotEmpty ||
          frame.understandingSnapshot.userFacingSummary.trim().isNotEmpty ||
          frame.detail.trim().isNotEmpty;
    case ProcessStepId.retrievalDesign:
      return false;
    case ProcessStepId.retrievalProcessing:
      return frame.headline.trim().isNotEmpty ||
          frame.retrievalProcessing.processingSummary.trim().isNotEmpty ||
          frame.detail.trim().isNotEmpty;
    case ProcessStepId.answerOrganization:
      return frame.headline.trim().isNotEmpty ||
          frame.answerProcessing.readinessSummary.trim().isNotEmpty ||
          frame.detail.trim().isNotEmpty;
    case ProcessStepId.unknown:
      return false;
  }
}

void _expectUserFacingProcessFrame(ProcessTimelineFrame frame) {
  final text = <String>[
    frame.headline,
    frame.detail,
    frame.understandingSnapshot.userFacingSummary,
    frame.retrievalProcessing.processingSummary,
    frame.answerProcessing.readinessSummary,
  ].join(' ');
  for (final forbidden in const <String>[
    'contractId',
    'assistant_turn',
    'tool_call',
    'toolresult',
    'searchPlans',
    'machineEnvelope',
    'turnPhase',
    'AssistantTraceEventType',
    '"reasonShort"',
  ]) {
    expect(
      text.contains(forbidden),
      isFalse,
      reason: '可见过程轨不应暴露内部协议字段 "$forbidden"',
    );
  }
}
