import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/application/assistant_gateway.dart';
import 'package:quwoquan_app/assistant/domain/channel/channel.dart';
import 'package:quwoquan_app/assistant/domain/conversation/conversation.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';

const _firstReplayQuery = '如果把九寨沟方向考虑进去，多给我几个备选方案';
const _secondReplayQuery = '如果我只有4天，优先哪条路线？';

void main() {
  group('Replay boundary E2E — 九寨沟两轮追问', () {
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

    test('首轮不应误入 expanding，并应尽快进入 final answer', () async {
      final diagnostics = await _runReplayTurn(
        gateway: gateway,
        sessionId: 'replay_boundary_session_first',
        query: _firstReplayQuery,
      );
      debugPrint('REPLAY_BOUNDARY_FIRST: ${diagnostics.toJson()}');

      expect(diagnostics.finalText.trim(), isNotEmpty);
      expect(diagnostics.nextAction, anyOf(equals('answer'), equals('')));
      expect(
        diagnostics.finalAnswerMode,
        anyOf(equals('full'), equals('bounded_answer'), equals('')),
      );

      if (!hasRemoteModel || diagnostics.degradedFailClosed) {
        return;
      }

      expect(
        diagnostics.expandSignalCount,
        0,
        reason: '首轮真实追问不应再落入 expanding/need_more_search 路径',
      );
      expect(diagnostics.nextAction, 'answer');
      expect(
        diagnostics.finalAnswerMode,
        anyOf(equals('full'), equals('bounded_answer')),
      );
      expect(
        diagnostics.modelCallCount,
        lessThanOrEqualTo(6),
        reason: '首轮应在有限模型调用内完成成答，避免重新扩检',
      );
    });

    test('第二轮追问保留 answer 路径，并输出调用预算画像', () async {
      const sessionId = 'replay_boundary_session_followup';
      await _runReplayTurn(
        gateway: gateway,
        sessionId: sessionId,
        query: _firstReplayQuery,
      );
      final diagnostics = await _runReplayTurn(
        gateway: gateway,
        sessionId: sessionId,
        query: _secondReplayQuery,
      );
      debugPrint('REPLAY_BOUNDARY_SECOND: ${diagnostics.toJson()}');

      expect(diagnostics.finalText.trim(), isNotEmpty);

      if (!hasRemoteModel || diagnostics.degradedFailClosed) {
        return;
      }

      expect(diagnostics.expandSignalCount, 0);
      expect(diagnostics.nextAction, 'answer');
      expect(
        diagnostics.finalAnswerMode,
        anyOf(equals('full'), equals('bounded_answer')),
      );
      expect(
        diagnostics.phaseOneRoute,
        'phase_one_direct_answer',
        reason: '第二轮连续追问应优先在 phase-one 收口，而不是回退 formal_synthesis',
      );
      expect(
        diagnostics.synthesisCallCount,
        0,
        reason: '第二轮连续追问不应再触发正式 synthesis 请求',
      );
    });
  });
}

Future<_ReplayBoundaryDiagnostics> _runReplayTurn({
  required AssistantGateway gateway,
  required String sessionId,
  required String query,
}) async {
  final traces = <AssistantTraceEvent>[];
  final response = await gateway.runWithTraceStream(
    AssistantRunRequest(
      sessionId: sessionId,
      userId: 'test_user',
      deviceProfile: 'mobile',
      channel: 'app',
      messages: <AssistantRunMessage>[
        AssistantRunMessage(role: 'user', content: query),
      ],
    ),
    onTraceEvent: traces.add,
  );

  final structured = response.structuredResponse;
  final runArtifacts =
      (structured['runArtifacts'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final answerDecision =
      (runArtifacts['answerDecision'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final journal =
      (runArtifacts['processJournal'] as List?)
          ?.whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList(growable: false) ??
      const <Map<String, dynamic>>[];
  final uiUsageStats =
      (structured['uiUsageStats'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final phaseOneRoutingDiagnostics =
      (structured['phaseOneRoutingDiagnostics'] as Map?)
          ?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final toolSequence = traces
      .where((trace) => trace.type == AssistantTraceEventType.toolStart)
      .map((trace) => (trace.data?['toolName'] as String?)?.trim() ?? '')
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
  final llmIterationCount = traces
      .where(
        (trace) =>
            trace.type == AssistantTraceEventType.lifecycleStart &&
            trace.message.startsWith('llm request iteration '),
      )
      .length;
  final synthesisCallCount = traces
      .where(
        (trace) =>
            trace.type == AssistantTraceEventType.lifecycleStart &&
            trace.message.startsWith('llm request synthesis '),
      )
      .length;
  final expandSignalCount = journal.where((item) {
    final stage = (item['stage'] as String?)?.trim() ?? '';
    final phaseId = (item['phaseId'] as String?)?.trim() ?? '';
    final actionCode = (item['actionCode'] as String?)?.trim() ?? '';
    final reasonCode = (item['reasonCode'] as String?)?.trim() ?? '';
    return stage == 'expanding' ||
        phaseId == 'expanding' ||
        actionCode == 'expand_search' ||
        reasonCode == 'need_more_search' ||
        reasonCode == 'need_more_evidence';
  }).length;

  return _ReplayBoundaryDiagnostics(
    query: query,
    degradedFailClosed:
        response.degraded ||
        response.finalText.contains('模型输出无效') ||
        response.finalText.contains('已停止本轮回答'),
    finalText: response.displayPlainText.trim().isNotEmpty
        ? response.displayPlainText.trim()
        : response.finalText.trim(),
    modelCallCount: (uiUsageStats['modelCallCount'] as num?)?.toInt() ?? 0,
    nextAction: (answerDecision['nextAction'] as String?)?.trim() ?? '',
    finalAnswerMode:
        (answerDecision['finalAnswerMode'] as String?)?.trim() ?? '',
    phaseOneRoute:
        (phaseOneRoutingDiagnostics['route'] as String?)?.trim() ?? '',
    expandSignalCount: expandSignalCount,
    llmIterationCount: llmIterationCount,
    synthesisCallCount: synthesisCallCount,
    toolSequence: toolSequence,
    journalStages: _uniqueNonEmpty(
      journal.map((item) => (item['stage'] as String?)?.trim() ?? ''),
    ),
  );
}

class _ReplayBoundaryDiagnostics {
  const _ReplayBoundaryDiagnostics({
    required this.query,
    required this.degradedFailClosed,
    required this.finalText,
    required this.modelCallCount,
    required this.nextAction,
    required this.finalAnswerMode,
    required this.phaseOneRoute,
    required this.expandSignalCount,
    required this.llmIterationCount,
    required this.synthesisCallCount,
    required this.toolSequence,
    required this.journalStages,
  });

  final String query;
  final bool degradedFailClosed;
  final String finalText;
  final int modelCallCount;
  final String nextAction;
  final String finalAnswerMode;
  final String phaseOneRoute;
  final int expandSignalCount;
  final int llmIterationCount;
  final int synthesisCallCount;
  final List<String> toolSequence;
  final List<String> journalStages;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'query': query,
      'degradedFailClosed': degradedFailClosed,
      'finalText': finalText,
      'modelCallCount': modelCallCount,
      'nextAction': nextAction,
      'finalAnswerMode': finalAnswerMode,
      'phaseOneRoute': phaseOneRoute,
      'expandSignalCount': expandSignalCount,
      'llmIterationCount': llmIterationCount,
      'synthesisCallCount': synthesisCallCount,
      'toolSequence': toolSequence,
      'journalStages': journalStages,
    };
  }
}

List<String> _uniqueNonEmpty(Iterable<String> values) {
  final seen = <String>{};
  final out = <String>[];
  for (final raw in values) {
    final value = raw.trim();
    if (value.isEmpty || !seen.add(value)) continue;
    out.add(value);
  }
  return out;
}
