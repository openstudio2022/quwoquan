import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/planner_contracts.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/domain/channel/channel.dart';
import 'package:quwoquan_app/assistant/orchestration/trace_user_event_translator.dart';

void main() {
  group('trace user event translator', () {
    test('phase narrative lifecycleStart 转成用户态 process event', () {
      final event = AssistantTraceEvent(
        type: AssistantTraceEventType.lifecycleStart,
        message: '我先把问题主线理清，再决定怎么查。',
        timestamp: DateTime.now(),
        runId: 'run_1',
        data: const <String, dynamic>{
          'phaseNarrative': true,
          'phaseId': 'understand',
          'narrative': '我先把问题主线理清，再决定怎么查。',
        },
      );

      final translated = TraceUserEventTranslator.translate(event);
      expect(translated, isNotNull);
      expect(translated!.type, UserEventType.processCommit);
      expect(translated.payload['reasonShort'], '我先把问题主线理清，再决定怎么查。');
      expect(translated.payload['phaseId'], PlannerPhaseId.understanding.wireName);
    });

    test('searchQueryGenerated 使用 canonical process code', () {
      final event = AssistantTraceEvent(
        type: AssistantTraceEventType.searchQueryGenerated,
        message: '生成检索计划',
        timestamp: DateTime.now(),
        data: <String, dynamic>{
          'toolName': 'web_search',
          'problemClass': 'realtime_info',
          'queryTasks': <Map<String, dynamic>>[
            <String, dynamic>{'query': '深圳天气', 'label': '当前状态'},
            <String, dynamic>{'query': '深圳天气影响', 'label': '决策影响'},
          ],
        },
      );

      final translated = TraceUserEventTranslator.translate(event);
      expect(translated, isNotNull);
      expect(translated!.type, UserEventType.processCommit);
      expect(translated.payload['phaseId'], PlannerPhaseId.searching.wireName);
      expect(
        translated.payload['actionCode'],
        PlannerActionCode.startRetrieval.wireName,
      );
      expect(
        translated.payload['reasonCode'],
        PlannerReasonCode.reduceWaitTime.wireName,
      );
    });

    test('assessment 使用 typed assessment 映射 canonical reason', () {
      final event = AssistantTraceEvent(
        type: AssistantTraceEventType.toolResult,
        message: 'assessment',
        timestamp: DateTime.now(),
        data: <String, dynamic>{
          'isAssessment': true,
          'assessmentType': AssessmentType.toolFailed.wireName,
          'shouldContinueLoop': true,
        },
      );

      final translated = TraceUserEventTranslator.translate(event);
      expect(translated, isNotNull);
      expect(translated!.payload['phaseId'], PlannerPhaseId.analyzing.wireName);
      expect(
        translated.payload['actionCode'],
        PlannerActionCode.assessEvidence.wireName,
      );
      expect(
        translated.payload['reasonCode'],
        PlannerReasonCode.sourceUnstable.wireName,
      );
    });
  });
}
