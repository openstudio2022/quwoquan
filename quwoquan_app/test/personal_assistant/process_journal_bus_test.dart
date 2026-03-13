import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/personal_assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/personal_assistant/engine/process_journal_bus.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';

void main() {
  group('ProcessJournalBus', () {
    test('内部 trace 不进入用户过程流', () {
      final bus = ProcessJournalBus(userGoalSummary: '深圳天气');

      bus.consumeTrace(
        AssistantTraceEvent(
          type: AssistantTraceEventType.planStarted,
          message: '开始规划: 压缩以上对话历史为简洁摘要',
          timestamp: DateTime.now(),
          data: const <String, dynamic>{'goal': '压缩以上对话历史为简洁摘要'},
          visibility: TraceVisibility.internal,
        ),
      );
      bus.consumeTrace(
        AssistantTraceEvent(
          type: AssistantTraceEventType.planStarted,
          message: '开始规划: 深圳天气',
          timestamp: DateTime.now(),
          data: const <String, dynamic>{'goal': '深圳天气'},
        ),
      );

      final snapshot = bus.snapshot;
      expect(snapshot, isNotEmpty);
      final text = snapshot.map((item) => item.displayMessage).join(' ');
      expect(text, isNot(contains('压缩以上对话历史为简洁摘要')));
      expect(text, isNot(contains('summarize_session')));
    });

    test('原始账 append-only，displaySnapshot 只保留当前直播版本', () {
      final bus = ProcessJournalBus(userGoalSummary: '深圳天气');

      bus.consumeTrace(
        AssistantTraceEvent(
          type: AssistantTraceEventType.thinkingProgress,
          message: '我先查深圳天气',
          timestamp: DateTime.now(),
          data: const <String, dynamic>{
            'phase': 'understanding',
            'streaming': true,
            'extracted': true,
          },
        ),
      );
      bus.consumeTrace(
        AssistantTraceEvent(
          type: AssistantTraceEventType.thinkingProgress,
          message: '我先查深圳天气，再补出门提醒',
          timestamp: DateTime.now(),
          data: const <String, dynamic>{
            'phase': 'understanding',
            'streaming': true,
            'extracted': true,
          },
        ),
      );
      bus.consumeTrace(
        AssistantTraceEvent(
          type: AssistantTraceEventType.toolStart,
          message: 'calling web_search',
          timestamp: DateTime.now(),
          data: const <String, dynamic>{
            'toolName': 'web_search',
            'query': '深圳天气',
          },
        ),
      );

      final rawSnapshot = bus.snapshot;
      final displaySnapshot = bus.displaySnapshot;
      final rawLiveCursorCount = rawSnapshot
          .where((item) => item.type == ProcessJournalEventType.liveCursor)
          .length;
      final displayLiveCursorCount = displaySnapshot
          .where((item) => item.type == ProcessJournalEventType.liveCursor)
          .length;
      final narratives = displaySnapshot
          .where((item) => item.type == ProcessJournalEventType.narrativeCommit)
          .map((item) => item.displayMessage)
          .toList(growable: false);
      final firstNarrative = displaySnapshot.firstWhere(
        (item) => item.type == ProcessJournalEventType.narrativeCommit,
        orElse: () => const ProcessJournalEvent(
          eventId: '',
          type: ProcessJournalEventType.narrativeCommit,
          stage: '',
        ),
      );

      expect(rawLiveCursorCount, equals(2), reason: '原始账应保留两次直播替换历史');
      expect(displayLiveCursorCount, 0, reason: '切阶段后展示快照不应再保留 live cursor');
      expect(narratives, contains('我在确认问题边界，避免后面越查越散。'));
      expect(firstNarrative.phaseId, equals('understanding'));
      expect(firstNarrative.actionCode, equals('align_evidence'));
      expect(firstNarrative.reasonCode, equals('confirm_focus'));
      expect(firstNarrative.displayMessage, isNot(contains('我先帮你把')));
      expect(firstNarrative.displayMessage, isNot(contains('收一收')));
    });

    test('source update 在原始账中严格追加，不再按 nodeId 覆盖', () {
      final bus = ProcessJournalBus(userGoalSummary: '深圳天气');
      final now = DateTime.now();

      bus.consumeTrace(
        AssistantTraceEvent(
          type: AssistantTraceEventType.toolResult,
          message: '第一批资料已返回',
          timestamp: now,
          data: const <String, dynamic>{
            'toolName': 'web_search',
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '中国气象局',
                'url': 'https://weather.cma.cn/shenzhen',
                'source': 'weather.cma.cn',
              },
            ],
          },
        ),
      );
      bus.consumeTrace(
        AssistantTraceEvent(
          type: AssistantTraceEventType.toolResult,
          message: '第二批资料已返回',
          timestamp: now.add(const Duration(seconds: 1)),
          data: const <String, dynamic>{
            'toolName': 'web_search',
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '深圳天气频道',
                'url': 'https://example.com/shenzhen-weather',
                'source': 'example.com',
              },
            ],
          },
        ),
      );

      final rawSnapshot = bus.snapshot;
      final sourceUpdates = rawSnapshot
          .where((item) => item.type == ProcessJournalEventType.sourceUpdate)
          .toList(growable: false);

      expect(sourceUpdates.length, equals(2), reason: '原始账应保留两次来源增量更新');
      expect(
        sourceUpdates.first.references.single.url,
        contains('weather.cma.cn'),
      );
      expect(
        sourceUpdates.last.references.single.url,
        contains('example.com'),
      );
    });
  });
}
