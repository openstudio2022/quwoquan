import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/planner_contracts.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/domain/channel/channel.dart';
import 'package:quwoquan_app/assistant/orchestration/process_journal_bus.dart';

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
          type: AssistantTraceEventType.searchQueryGenerated,
          message: '生成检索计划',
          timestamp: DateTime.now(),
          data: const <String, dynamic>{
            'toolName': 'web_search',
            'query': '深圳天气',
            'problemClass': 'realtime_info',
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
      expect(firstNarrative.phaseIdType, PlannerPhaseId.understanding);
      expect(firstNarrative.actionCodeType, PlannerActionCode.assessEvidence);
      expect(firstNarrative.reasonCodeType, PlannerReasonCode.confirmFocus);
      expect(firstNarrative.displayMessage, isNot(contains('我先帮你把')));
      expect(firstNarrative.displayMessage, isNot(contains('收一收')));
    });

    test('source update 在原始账中严格追加，不再按 nodeId 覆盖', () {
      final bus = ProcessJournalBus(userGoalSummary: '深圳天气');
      final now = DateTime.now();

      bus.consumeTrace(
        AssistantTraceEvent(
          type: AssistantTraceEventType.searchCompleted,
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
          type: AssistantTraceEventType.searchCompleted,
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
      expect(sourceUpdates.last.references.single.url, contains('example.com'));
    });

    test('displaySnapshot 会折叠 narrative 与 sourceUpdate 的同文案重复', () {
      final snapshot = ProcessJournalBus.toDisplaySnapshot(
        const <ProcessJournalEvent>[
          ProcessJournalEvent(
            eventId: 'narrative_1',
            type: ProcessJournalEventType.narrativeCommit,
            stage: 'understanding',
            phaseId: 'understanding',
            actionCode: 'frame_problem',
            reasonCode: 'align_goal',
            reasonShort: '先确认 Cursor 相关范围，再决定查哪些维度。',
            nodeId: 'root.intent.plan',
          ),
          ProcessJournalEvent(
            eventId: 'source_update_1',
            type: ProcessJournalEventType.sourceUpdate,
            stage: 'understanding',
            phaseId: 'understanding',
            actionCode: 'frame_problem',
            reasonCode: 'align_goal',
            reasonShort: '先确认 Cursor 相关范围，再决定查哪些维度。',
            nodeId: 'root.intent.plan',
            references: <ProcessSourceReference>[
              ProcessSourceReference(
                title: 'Cursor 文档',
                url: 'https://cursor.com/docs',
                source: 'cursor.com',
              ),
            ],
          ),
        ],
      );

      expect(snapshot, hasLength(1));
      expect(snapshot.single.type, ProcessJournalEventType.sourceUpdate);
      expect(snapshot.single.displayMessage, '先确认 Cursor 相关范围，再决定查哪些维度。');
      expect(snapshot.single.references, hasLength(1));
    });
  });
}
