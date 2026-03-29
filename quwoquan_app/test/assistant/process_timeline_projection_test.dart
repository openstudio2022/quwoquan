import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';

void main() {
  group('process timeline projection', () {
    test('canonical 4-step timeline 会投影成可见 3-step timeline', () {
      final canonical = _canonicalFourStepTimeline();

      final visible = buildVisibleProcessTimeline(canonical);

      expect(
        visible.map((frame) => frame.stepId).toList(growable: false),
        orderedEquals(const <ProcessStepId>[
          ProcessStepId.understanding,
          ProcessStepId.retrievalProcessing,
          ProcessStepId.answerOrganization,
        ]),
      );
      expect(visible.first.detail, contains('关注点：天气现状、出门体感'));
      expect(
        visible.first.understandingSnapshot.queryDesignSummary,
        '我会先按天气现状和出门建议两路来核对。',
      );
    });

    test('持久化消息读取时 UI timeline 只恢复 3-step，但 canonical 仍保留 4-step', () {
      final canonical = _canonicalFourStepTimeline();
      final message = <String, dynamic>{
        'role': 'assistant',
        'content': '深圳今天晴，轻装出门更合适。',
        ...buildPersistedAssistantTurnFields(
          journey: const AssistantJourney(),
          processTimeline: canonical,
          displayMarkdown: '深圳今天晴，轻装出门更合适。',
          displayPlainText: '深圳今天晴，轻装出门更合适。',
          followupPrompt: '',
          actionHints: const <String>[],
          elapsedMs: 1200,
        ),
      };

      final persistedCanonical = resolvePersistedAssistantProcessTimeline(
        message,
      );
      final persistedVisible = resolvePersistedAssistantVisibleProcessTimeline(
        message,
      );

      expect(
        persistedCanonical.map((frame) => frame.stepId).toList(growable: false),
        orderedEquals(const <ProcessStepId>[
          ProcessStepId.understanding,
          ProcessStepId.retrievalDesign,
          ProcessStepId.retrievalProcessing,
          ProcessStepId.answerOrganization,
        ]),
      );
      expect(
        persistedVisible.map((frame) => frame.stepId).toList(growable: false),
        orderedEquals(const <ProcessStepId>[
          ProcessStepId.understanding,
          ProcessStepId.retrievalProcessing,
          ProcessStepId.answerOrganization,
        ]),
      );
      expect(persistedVisible.first.detail, contains('关注点：天气现状、出门体感'));
    });

    test('当前 v1 消息缺少 processTimeline 时不再回退到 journey', () {
      final message = <String, dynamic>{
        'role': 'assistant',
        'content': '深圳今天晴，轻装出门更合适。',
        assistantTurnSchemaVersionField: assistantTurnSchemaVersion,
        assistantJourneyField: const AssistantJourney(
          entries: <AssistantJourneyEntry>[
            AssistantJourneyEntry(
              entryId: 'journey.analyze.1',
              stageId: JourneyStageId.analyze,
              kind: JourneyEntryKind.narrative,
              status: JourneyStageStatus.completed,
              order: 0,
              headline: '我先确认你现在最需要的是实时天气结果。',
            ),
          ],
        ).toJson(),
      };

      expect(resolvePersistedAssistantVisibleProcessTimeline(message), isEmpty);
    });

    test('旧版本消息不再兼容 journey 回退恢复时间轴', () {
      final message = <String, dynamic>{
        'role': 'assistant',
        'content': '深圳今天晴，轻装出门更合适。',
        assistantTurnSchemaVersionField: 'assistant_turn_legacy',
        assistantJourneyField: const AssistantJourney(
          entries: <AssistantJourneyEntry>[
            AssistantJourneyEntry(
              entryId: 'journey.analyze.1',
              stageId: JourneyStageId.analyze,
              kind: JourneyEntryKind.narrative,
              status: JourneyStageStatus.completed,
              order: 0,
              headline: '我先确认你现在最需要的是实时天气结果。',
            ),
          ],
        ).toJson(),
      };

      expect(resolvePersistedAssistantVisibleProcessTimeline(message), isEmpty);
    });
  });
}

List<ProcessTimelineFrame> _canonicalFourStepTimeline() {
  return <ProcessTimelineFrame>[
    buildProcessTimelineFrame(
      stepId: ProcessStepId.understanding,
      status: JourneyStageStatus.completed,
      headline: '我先确认你现在最需要的是实时天气结果。',
      detail: '关注点：天气现状、出门体感',
      understandingSnapshot: const RunArtifactsUnderstandingSnapshot(
        intentSummary: '我先确认你现在最需要的是实时天气结果。',
        userFacingSummary: '我先确认你现在最需要的是实时天气结果。',
        concernPoints: <String>['天气现状', '出门体感'],
      ),
    ),
    buildProcessTimelineFrame(
      stepId: ProcessStepId.retrievalDesign,
      status: JourneyStageStatus.completed,
      headline: '我会先按天气现状和出门建议两路来核对。',
      detail: '天气现状：深圳 实时天气\n出门建议：体感温度 / 降雨概率',
      understandingSnapshot: const RunArtifactsUnderstandingSnapshot(
        queryDesignSummary: '我会先按天气现状和出门建议两路来核对。',
        queryGroups: <RunArtifactsUnderstandingQueryGroup>[
          RunArtifactsUnderstandingQueryGroup(
            dimension: '天气现状',
            queries: <String>['深圳 实时天气'],
            why: '先确认当前天气和温度。',
          ),
          RunArtifactsUnderstandingQueryGroup(
            dimension: '出门建议',
            queries: <String>['深圳 体感温度', '深圳 降雨概率'],
            why: '再判断是否需要携带雨具与增减衣物。',
          ),
        ],
      ),
    ),
    buildProcessTimelineFrame(
      stepId: ProcessStepId.retrievalProcessing,
      status: JourneyStageStatus.completed,
      headline: '能直接回答的关键信息已经收拢好了。',
      retrievalProcessing: const RetrievalProcessingSnapshot(
        processingSummary: '能直接回答的关键信息已经收拢好了。',
        selectedKeyPoints: <String>['晴', '26℃', '体感偏热'],
      ),
    ),
    buildProcessTimelineFrame(
      stepId: ProcessStepId.answerOrganization,
      status: JourneyStageStatus.completed,
      headline: '我把结果压成一句直接结论和一条简洁建议。',
      answerProcessing: const RunArtifactsAnswerProcessing(
        readinessSummary: '我把结果压成一句直接结论和一条简洁建议。',
      ),
    ),
  ];
}
