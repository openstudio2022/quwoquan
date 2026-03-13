import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/personal_assistant/contracts/explainable_flow_event.dart';
import 'package:quwoquan_app/personal_assistant/engine/process_event_consolidator.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';

void main() {
  group('ProcessEventConsolidator narrative', () {
    test('weather flow uses user-facing explanation language', () {
      final consolidator = ProcessEventConsolidator(
        problemClass: 'realtime_info',
        userGoalSummary: '深圳天气',
      );

      final started = consolidator.consolidate(
        AssistantTraceEvent(
          type: AssistantTraceEventType.planStarted,
          message: '',
          timestamp: DateTime.now(),
          data: const <String, dynamic>{'goal': '查询深圳天气'},
        ),
      );
      expect(started, isNotNull);
      expect(started!.headline, contains('深圳'));
      expect(started.headline, isNot(contains('我先帮你把')));
      expect(started.headline, isNot(contains('收一收')));
      expect(started.headline, isNot(contains('你更像是想知道')));
      expect(started.headline, isNot(contains('我先替你')));

      final thinking = consolidator.consolidate(
        AssistantTraceEvent(
          type: AssistantTraceEventType.thinkingProgress,
          message: '用户想了解深圳天气，我需要搜索最新的天气信息。',
          timestamp: DateTime.now(),
          data: const <String, dynamic>{'phase': 'understanding'},
        ),
      );
      expect(thinking, isNotNull);
      expect(thinking!.headline, isNot(contains('用户想了解')));
      expect(thinking.headline, isNot(contains('我需要搜索')));
      expect(thinking.headline, isNot(contains('我先帮你把')));
      expect(thinking.headline, isNot(contains('收一收')));
      expect(thinking.headline, isNot(contains('你更像是想知道')));
      expect(thinking.headline, isNot(contains('我先替你')));

      consolidator.consolidate(
        AssistantTraceEvent(
          type: AssistantTraceEventType.toolStart,
          message: 'search started',
          timestamp: DateTime.now(),
          data: const <String, dynamic>{'toolName': 'web_search'},
        ),
      );
      final toolResult = consolidator.consolidate(
        AssistantTraceEvent(
          type: AssistantTraceEventType.toolResult,
          message: '',
          timestamp: DateTime.now(),
          data: const <String, dynamic>{
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '深圳天气预报',
                'url': 'https://example.com/weather',
                'source': 'example.com',
              },
            ],
          },
        ),
      );
      expect(toolResult, isNotNull);
      expect(toolResult!.headline, contains('来源'));
      expect(toolResult.headline, isNot(contains('找到 1 篇相关资料')));
    });

    test('replan and completion keep trust-building tone', () {
      final consolidator = ProcessEventConsolidator(
        problemClass: 'complex_reasoning',
        userGoalSummary: '查深圳住宿建议',
      );

      consolidator.consolidate(
        AssistantTraceEvent(
          type: AssistantTraceEventType.planStarted,
          message: '',
          timestamp: DateTime.now(),
          data: const <String, dynamic>{'goal': '查深圳住宿建议'},
        ),
      );
      final replan = consolidator.consolidate(
        AssistantTraceEvent(
          type: AssistantTraceEventType.replanTriggered,
          message: '',
          timestamp: DateTime.now(),
        ),
      );
      expect(replan, isNotNull);
      expect(replan!.headline, contains('再补'));
      expect(replan.headline, isNot(contains('我先替你')));

      final finished = consolidator.consolidate(
        AssistantTraceEvent(
          type: AssistantTraceEventType.lifecycleEnd,
          message: 'agent loop finished',
          timestamp: DateTime.now(),
        ),
      );
      expect(finished, isNotNull);
      expect(finished!.phaseId, equals(PhaseId.answer));
      expect(finished.headline, equals('已为你整理好'));
    });
  });
}
