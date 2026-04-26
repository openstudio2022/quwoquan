import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/assistant_journey_view_model.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/assistant_process_drawer.dart';

AssistantJourneyViewModel _viewModel({
  AssistantJourney journey = const AssistantJourney(),
  bool isRunning = false,
  int elapsedMs = 0,
  bool allowAnswerStage = true,
  List<ProcessTimelineFrame> processTimeline = const <ProcessTimelineFrame>[],
  RetrievalProcessingSnapshot retrievalProcessing =
      const RetrievalProcessingSnapshot(),
}) {
  final effectiveProcessTimeline = processTimeline.isNotEmpty
      ? processTimeline
      : _processTimelineFromJourney(
          journey,
          retrievalProcessing: retrievalProcessing,
        );
  return buildAssistantJourneyViewModel(
    journey: journey,
    processTimeline: effectiveProcessTimeline,
    isRunning: isRunning,
    allowAnswerStage: allowAnswerStage,
    elapsedMs: elapsedMs,
    retrievalProcessing: retrievalProcessing,
  );
}

List<ProcessTimelineFrame> _processTimelineFromJourney(
  AssistantJourney journey, {
  RetrievalProcessingSnapshot retrievalProcessing =
      const RetrievalProcessingSnapshot(),
}) {
  final hasRetrievalProcessing = _hasStructuredRetrievalProcessing(
    retrievalProcessing,
  );
  if (journey.isEmpty && !hasRetrievalProcessing) {
    return const <ProcessTimelineFrame>[];
  }
  final baseFrames = journey.isEmpty
      ? const <ProcessTimelineFrame>[]
      : buildProcessTimelineFramesFromJourneyFallback(journey);
  if (!hasRetrievalProcessing) {
    return baseFrames;
  }
  final designFrame = baseFrames.where(
    (frame) => frame.stepId == ProcessStepId.retrievalDesign,
  );
  final designNarrative = designFrame.isEmpty
      ? ''
      : '${designFrame.first.headline.trim()}\n${designFrame.first.detail.trim()}';
  final processingSummary = retrievalProcessing.processingSummary.trim();
  final shouldSupplementRetrievalProcessing =
      baseFrames.any((frame) => frame.stepId == ProcessStepId.retrievalProcessing) ||
      retrievalProcessing.acceptedReferences.isNotEmpty ||
      retrievalProcessing.processedDocumentCount > 0 ||
      retrievalProcessing.acceptedDocumentCount > 0 ||
      retrievalProcessing.selectedKeyPoints.any((item) => item.trim().isNotEmpty) ||
      retrievalProcessing.expansionReason.trim().isNotEmpty ||
      (processingSummary.isNotEmpty &&
          processingSummary != designNarrative.trim());
  if (!shouldSupplementRetrievalProcessing) {
    return baseFrames;
  }
  return buildProcessTimelineFromSnapshots(
    processTimeline: baseFrames,
    retrievalProcessing: retrievalProcessing,
  );
}

bool _hasStructuredRetrievalProcessing(RetrievalProcessingSnapshot snapshot) {
  return snapshot.processingSummary.trim().isNotEmpty ||
      snapshot.expansionReason.trim().isNotEmpty ||
      snapshot.acceptedReferences.isNotEmpty ||
      snapshot.selectedKeyPoints.any((item) => item.trim().isNotEmpty) ||
      snapshot.processedDocumentCount > 0 ||
      snapshot.acceptedDocumentCount > 0;
}

const AssistantJourney _referenceJourney = AssistantJourney(
  stages: <AssistantJourneyStage>[
    AssistantJourneyStage(
      stageId: JourneyStageId.analyze,
      status: JourneyStageStatus.completed,
      order: 0,
      summary: '我先把问题立住',
    ),
    AssistantJourneyStage(
      stageId: JourneyStageId.search,
      status: JourneyStageStatus.active,
      order: 1,
      summary: '我在核对最新资料',
      referenceCount: 1,
    ),
    AssistantJourneyStage(
      stageId: JourneyStageId.verify,
      status: JourneyStageStatus.pending,
      order: 2,
    ),
    AssistantJourneyStage(
      stageId: JourneyStageId.answer,
      status: JourneyStageStatus.pending,
      order: 3,
    ),
  ],
  entries: <AssistantJourneyEntry>[
    AssistantJourneyEntry(
      entryId: 'journey.analyze.1',
      stageId: JourneyStageId.analyze,
      kind: JourneyEntryKind.narrative,
      status: JourneyStageStatus.completed,
      order: 0,
      headline: '我先把问题立住',
    ),
    AssistantJourneyEntry(
      entryId: 'journey.search.1',
      stageId: JourneyStageId.search,
      kind: JourneyEntryKind.referenceBundle,
      status: JourneyStageStatus.active,
      order: 1,
      headline: '我在核对最新资料',
      references: <AssistantJourneyReference>[
        AssistantJourneyReference(
          title: '四川文旅公告',
          url: 'https://example.com/doc',
          source: '官方',
        ),
      ],
    ),
  ],
  summary: '已核对 1 个来源',
  referenceSummary: AssistantJourneyReferenceSummary(
    count: 1,
    references: <AssistantJourneyReference>[
      AssistantJourneyReference(
        title: '四川文旅公告',
        url: 'https://example.com/doc',
        source: '官方',
      ),
    ],
  ),
);

void main() {
  group('AssistantProcessDrawer', () {
    test('理解阶段的内部规划口吻不会再显示为固定确认句', () {
      final built = _viewModel(
        journey: const AssistantJourney(
          stages: <AssistantJourneyStage>[
            AssistantJourneyStage(
              stageId: JourneyStageId.analyze,
              status: JourneyStageStatus.active,
              order: 0,
              summary: '用户想了解深圳天气，我需要搜索最新的天气信息。',
            ),
            AssistantJourneyStage(
              stageId: JourneyStageId.search,
              status: JourneyStageStatus.active,
              order: 1,
              summary: '我先换几个检索词继续找',
            ),
          ],
          entries: <AssistantJourneyEntry>[
            AssistantJourneyEntry(
              entryId: 'journey.analyze.1',
              stageId: JourneyStageId.analyze,
              kind: JourneyEntryKind.narrative,
              status: JourneyStageStatus.active,
              order: 0,
              headline: '用户想了解深圳天气，我需要搜索最新的天气信息。',
            ),
            AssistantJourneyEntry(
              entryId: 'journey.search.1',
              stageId: JourneyStageId.search,
              kind: JourneyEntryKind.narrative,
              status: JourneyStageStatus.active,
              order: 1,
              headline: '我先换几个检索词继续找',
            ),
          ],
        ),
        isRunning: true,
      );

      expect(
        built.blocks.any(
          (block) => block.headline.contains('我先确认你现在最需要的是实时天气结果'),
        ),
        isFalse,
      );
      expect(
        built.blocks.any(
          (block) =>
              block.stageId == ProcessStepId.retrievalDesign &&
              block.headline.contains('我先换几个检索词继续找'),
        ),
        isTrue,
      );
    });

    test('运行中且 answer gate 未打开时，会继续停留在搜索阶段', () {
      const journey = AssistantJourney(
        stages: <AssistantJourneyStage>[
          AssistantJourneyStage(
            stageId: JourneyStageId.analyze,
            status: JourneyStageStatus.completed,
            order: 0,
            summary: '先把问题立住',
          ),
          AssistantJourneyStage(
            stageId: JourneyStageId.search,
            status: JourneyStageStatus.completed,
            order: 1,
            summary: '我在核对实时天气来源',
          ),
          AssistantJourneyStage(
            stageId: JourneyStageId.answer,
            status: JourneyStageStatus.active,
            order: 3,
            summary: '我开始整理答案',
          ),
        ],
        entries: <AssistantJourneyEntry>[
          AssistantJourneyEntry(
            entryId: 'journey.search.1',
            stageId: JourneyStageId.search,
            kind: JourneyEntryKind.narrative,
            status: JourneyStageStatus.completed,
            order: 0,
            headline: '我在核对实时天气来源',
          ),
          AssistantJourneyEntry(
            entryId: 'journey.answer.1',
            stageId: JourneyStageId.answer,
            kind: JourneyEntryKind.narrative,
            status: JourneyStageStatus.active,
            order: 1,
            headline: '我开始整理答案',
          ),
        ],
        readiness: AssistantJourneyReadiness(finalAnswerReady: false),
      );

      final viewModel = _viewModel(
        journey: journey,
        isRunning: true,
        allowAnswerStage: false,
      );

      expect(viewModel.activeStageId, ProcessStepId.retrievalProcessing);
      expect(
        viewModel.activeStageLabel,
        UITextConstants.assistantProcessStageRetrievalProcessing,
      );
      expect(
        viewModel.blocks.any(
          (block) => block.stageId == ProcessStepId.answerOrganization,
        ),
        isFalse,
      );
    });

    test('空 journey 运行中也不再生成 seeded 假过程', () {
      final viewModel = _viewModel(isRunning: true);

      expect(viewModel.hasVisibleContent, isFalse);
      expect(viewModel.stages, isEmpty);
      expect(viewModel.blocks, isEmpty);
    });

    testWidgets('长等待且无进展时顶部栏展示耗时', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AssistantProcessDrawer(
              viewModel: _viewModel(isRunning: true, elapsedMs: 7000),
            ),
          ),
        ),
      );

      expect(find.text('耗时 7 秒'), findsOneWidget);
    });

    testWidgets('两阶段已出现时不在头部插入 reassurance', (tester) async {
      const journey = AssistantJourney(
        stages: <AssistantJourneyStage>[
          AssistantJourneyStage(
            stageId: JourneyStageId.analyze,
            status: JourneyStageStatus.active,
            order: 0,
          ),
          AssistantJourneyStage(
            stageId: JourneyStageId.search,
            status: JourneyStageStatus.pending,
            order: 1,
          ),
          AssistantJourneyStage(
            stageId: JourneyStageId.answer,
            status: JourneyStageStatus.pending,
            order: 2,
          ),
        ],
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AssistantProcessDrawer(
              viewModel: _viewModel(
                journey: journey,
                isRunning: true,
                elapsedMs: 7000,
                processTimeline: const <ProcessTimelineFrame>[
                  ProcessTimelineFrame(
                    frameId: 'process.understanding',
                    stepId: ProcessStepId.understanding,
                    status: JourneyStageStatus.completed,
                    order: 0,
                    headline: '我先把问题立住',
                  ),
                ],
              ),
              initiallyExpanded: true,
            ),
          ),
        ),
      );

      expect(
        find.text(UITextConstants.assistantProcessLongWaitReassurance),
        findsNothing,
      );
    });

    testWidgets('短等待时顶部栏也会展示耗时', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AssistantProcessDrawer(
              viewModel: _viewModel(isRunning: true, elapsedMs: 1500),
            ),
          ),
        ),
      );

      expect(
        find.text(UITextConstants.assistantProcessLongWaitReassurance),
        findsNothing,
      );
      expect(find.text('耗时 2 秒'), findsOneWidget);
    });

    testWidgets('运行中顶部栏展示耗时而不展示阶段结果', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AssistantProcessDrawer(
              viewModel: _viewModel(isRunning: true, elapsedMs: 9000),
            ),
          ),
        ),
      );

      expect(find.text(UITextConstants.assistantProcessRunningSummary), findsOneWidget);
      expect(find.text('耗时 9 秒'), findsOneWidget);
      expect(find.text(UITextConstants.assistantProcessStageUnderstand), findsNothing);
    });

    testWidgets('更长等待时顶部栏继续展示耗时而不是 reassurance', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Column(
              children: [
                AssistantProcessDrawer(
                  viewModel: _viewModel(isRunning: true, elapsedMs: 13000),
                ),
                AssistantProcessDrawer(
                  viewModel: _viewModel(isRunning: true, elapsedMs: 21000),
                ),
              ],
            ),
          ),
        ),
      );

      expect(find.text('耗时 13 秒'), findsOneWidget);
      expect(find.text('耗时 21 秒'), findsOneWidget);
    });

    testWidgets('展开后会渲染独立的过程正文容器', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AssistantProcessDrawer(
              viewModel: _viewModel(
                journey: _referenceJourney,
                isRunning: false,
              ),
            ),
          ),
        ),
      );

      expect(find.byKey(TestKeys.assistantProcessBody), findsNothing);

      await tester.tap(find.byKey(TestKeys.assistantProcessHeader));
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byKey(TestKeys.assistantProcessBody), findsOneWidget);
    });

    testWidgets('journey 会展示两段叙事与来源列表', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AssistantProcessDrawer(
              viewModel: _viewModel(
                journey: _referenceJourney,
                isRunning: true,
              ),
              initiallyExpanded: true,
            ),
          ),
        ),
      );

      expect(find.text('我先把问题立住'), findsOneWidget);
      expect(find.text('处理 1 篇'), findsOneWidget);
      expect(find.text('接纳 1 篇'), findsOneWidget);
      expect(find.textContaining('处理了 1 篇'), findsOneWidget);
      expect(
        find.text(UITextConstants.assistantProcessStageUnderstand),
        findsNothing,
      );
      expect(
        find.text(UITextConstants.assistantProcessStageRetrievalProcessing),
        findsNothing,
      );
      expect(
        find.text(UITextConstants.assistantProcessStageAnswer),
        findsNothing,
      );
      expect(find.text('查找信息'), findsNothing);
      expect(find.text('核对结论'), findsNothing);
      expect(find.text('整理回答'), findsNothing);
      expect(find.text('来源：官方'), findsNothing);

      await tester.tap(find.textContaining('处理了 1 篇').last);
      await tester.pump();

      expect(find.text('1. 四川文旅公告 · 官方'), findsOneWidget);
    });

    testWidgets('有 search stage 时会展示独立 query design，而不是回退成 processing', (
      tester,
    ) async {
      const journey = AssistantJourney(
        stages: <AssistantJourneyStage>[
          AssistantJourneyStage(
            stageId: JourneyStageId.analyze,
            status: JourneyStageStatus.completed,
            order: 0,
          ),
          AssistantJourneyStage(
            stageId: JourneyStageId.search,
            status: JourneyStageStatus.active,
            order: 1,
            summary: '- 实时天气',
          ),
        ],
        entries: <AssistantJourneyEntry>[
          AssistantJourneyEntry(
            entryId: 'journey.search.plan',
            stageId: JourneyStageId.search,
            kind: JourneyEntryKind.narrative,
            status: JourneyStageStatus.active,
            order: 0,
            detail: '- 实时天气',
          ),
        ],
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AssistantProcessDrawer(
              viewModel: _viewModel(journey: journey, isRunning: true),
              initiallyExpanded: true,
            ),
          ),
        ),
      );

      expect(find.textContaining('实时天气'), findsOneWidget);
      expect(find.textContaining('深圳天气 实时 降雨 温度'), findsNothing);
    });

    test('search 正式 narrative 存在时不会再回退补一遍 summary', () {
      const queryDesign = '- 体感与当前状态';
      final built = _viewModel(
        journey: const AssistantJourney(
          stages: <AssistantJourneyStage>[
            AssistantJourneyStage(
              stageId: JourneyStageId.search,
              status: JourneyStageStatus.completed,
              order: 1,
              summary: queryDesign,
            ),
          ],
          entries: <AssistantJourneyEntry>[
            AssistantJourneyEntry(
              entryId: 'journey.search.plan',
              stageId: JourneyStageId.search,
              kind: JourneyEntryKind.narrative,
              status: JourneyStageStatus.completed,
              order: 0,
              detail: queryDesign,
            ),
          ],
        ),
        isRunning: false,
        retrievalProcessing: const RetrievalProcessingSnapshot(
          processingSummary: queryDesign,
        ),
      );

      final searchNarratives = built.blocks
          .where(
            (block) =>
                block.stageId == ProcessStepId.retrievalProcessing &&
                block.kind == AssistantJourneyBlockKind.searchSummary,
          )
          .toList(growable: false);

      expect(searchNarratives, hasLength(1));
      expect(searchNarratives.single.headline, contains('体感与当前状态'));
      expect(
        built.blocks.where(
          (block) => block.stageId == ProcessStepId.retrievalProcessing,
        ),
        hasLength(1),
      );
    });

    test('三阶段内容会按理解、检索设计、检索处理顺序归位', () {
      const journey = AssistantJourney(
        stages: <AssistantJourneyStage>[
          AssistantJourneyStage(
            stageId: JourneyStageId.analyze,
            status: JourneyStageStatus.completed,
            order: 0,
          ),
          AssistantJourneyStage(
            stageId: JourneyStageId.search,
            status: JourneyStageStatus.completed,
            order: 1,
          ),
          AssistantJourneyStage(
            stageId: JourneyStageId.verify,
            status: JourneyStageStatus.completed,
            order: 2,
          ),
          AssistantJourneyStage(
            stageId: JourneyStageId.answer,
            status: JourneyStageStatus.completed,
            order: 3,
          ),
        ],
        entries: <AssistantJourneyEntry>[
          AssistantJourneyEntry(
            entryId: 'journey.analyze.weather',
            stageId: JourneyStageId.analyze,
            kind: JourneyEntryKind.narrative,
            status: JourneyStageStatus.completed,
            order: 0,
            headline: '先确认你想看的就是深圳今天的实时天气。',
          ),
          AssistantJourneyEntry(
            entryId: 'journey.search.plan',
            stageId: JourneyStageId.search,
            kind: JourneyEntryKind.narrative,
            status: JourneyStageStatus.completed,
            order: 1,
            detail: '围绕深圳实时天气、深圳今天天气预报组织检索。\n检索词：深圳 实时天气；深圳今天天气',
          ),
          AssistantJourneyEntry(
            entryId: 'journey.answer.weather',
            stageId: JourneyStageId.answer,
            kind: JourneyEntryKind.narrative,
            status: JourneyStageStatus.completed,
            order: 2,
            detail: '已获取深圳官方及权威气象站的实时天气数据，信息完整，可直接作答。',
          ),
          AssistantJourneyEntry(
            entryId: 'journey.verify.weather',
            stageId: JourneyStageId.verify,
            kind: JourneyEntryKind.referenceBundle,
            status: JourneyStageStatus.completed,
            order: 3,
            detail: '已获取深圳官方及权威气象站的实时天气数据，信息完整，可直接作答。',
            references: <AssistantJourneyReference>[
              AssistantJourneyReference(
                title: '深圳天气预报 - nmc.cn',
                url: 'https://www.nmc.cn',
                source: 'nmc.cn',
              ),
              AssistantJourneyReference(
                title: '深圳天气预报 - weather.com.cn',
                url: 'https://www.weather.com.cn',
                source: 'weather.com.cn',
              ),
              AssistantJourneyReference(
                title: '中央气象台 - wx.nmc.cn',
                url: 'https://wx.nmc.cn',
                source: 'wx.nmc.cn',
              ),
            ],
          ),
        ],
        readiness: AssistantJourneyReadiness(finalAnswerReady: true),
      );
      const retrievalProcessing = RetrievalProcessingSnapshot(
        processedDocumentCount: 10,
        acceptedDocumentCount: 3,
        processingSummary: '已获取深圳官方及权威气象站的实时天气数据，信息完整，可直接作答。',
        acceptedReferences: <RetrievalProcessingReference>[
          RetrievalProcessingReference(
            title: '深圳天气预报 - nmc.cn',
            url: 'https://www.nmc.cn',
            source: 'nmc.cn',
          ),
          RetrievalProcessingReference(
            title: '深圳天气预报 - weather.com.cn',
            url: 'https://www.weather.com.cn',
            source: 'weather.com.cn',
          ),
          RetrievalProcessingReference(
            title: '中央气象台 - wx.nmc.cn',
            url: 'https://wx.nmc.cn',
            source: 'wx.nmc.cn',
          ),
        ],
      );

      final viewModel = _viewModel(
        journey: journey,
        isRunning: false,
        retrievalProcessing: retrievalProcessing,
      );

      expect(
        viewModel.blocks.map((block) => block.stageId).toList(growable: false),
        equals(const <ProcessStepId>[
          ProcessStepId.understanding,
          ProcessStepId.retrievalDesign,
          ProcessStepId.retrievalProcessing,
          ProcessStepId.retrievalProcessing,
        ]),
      );
      expect(viewModel.blocks[1].kind, AssistantJourneyBlockKind.narrative);
      expect(viewModel.blocks[1].headline, contains('围绕深圳实时天气'));
      expect(viewModel.blocks[1].items, isEmpty);
      expect(viewModel.blocks[2].kind, AssistantJourneyBlockKind.referenceStats);
      expect(viewModel.blocks[2].headline, '处理了 10 篇，接纳了 3 篇');
      expect(viewModel.blocks[2].references, hasLength(3));
      expect(viewModel.blocks[3].kind, AssistantJourneyBlockKind.searchSummary);
      expect(viewModel.blocks[3].headline, contains('已获取深圳官方及权威气象站'));
      expect(viewModel.blocks[3].items, isEmpty);
      expect(viewModel.blocks[2].referenceLabel, isEmpty);
    });

    test('canonical 四阶段过程轨会折叠成可见三阶段，且 understanding 不再吞并 query design', () {
      final built = _viewModel(
        processTimeline: <ProcessTimelineFrame>[
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
            understandingSnapshot: const RunArtifactsUnderstandingSnapshot(
              intentSummary: '我会先按天气现状和出门建议两路来核对。',
            ),
          ),
          buildProcessTimelineFrame(
            stepId: ProcessStepId.retrievalProcessing,
            status: JourneyStageStatus.completed,
            headline: '能直接回答的关键信息已经收拢好了。',
            retrievalProcessing: const RetrievalProcessingSnapshot(
              processingSummary: '能直接回答的关键信息已经收拢好了。',
            ),
          ),
        ],
      );

      expect(
        built.blocks.map((block) => block.stageId).toList(growable: false),
        orderedEquals(const <ProcessStepId>[
          ProcessStepId.understanding,
          ProcessStepId.retrievalDesign,
          ProcessStepId.retrievalProcessing,
        ]),
      );
      expect(built.blocks.first.detail, isEmpty);
      expect(
        built.blocks[1].headline,
        contains('我会先按天气现状和出门建议两路来核对'),
      );
    });

    test('两段叙事会连续带出检索词设计与成答组织', () {
      const designNarrative =
          '我会先沿着天气现状这一条线继续核对，先锁定最新天气面，检索词会围绕“深圳 实时天气”、“深圳 降雨 概率”展开。';
      final built = buildAssistantJourneyViewModel(
        journey: const AssistantJourney(),
        processTimeline: <ProcessTimelineFrame>[
          ProcessTimelineFrame(
            frameId: 'u',
            stepId: ProcessStepId.understanding,
            status: JourneyStageStatus.completed,
          ),
          ProcessTimelineFrame(
            frameId: 'd',
            stepId: ProcessStepId.retrievalDesign,
            status: JourneyStageStatus.completed,
            headline: designNarrative,
          ),
          ProcessTimelineFrame(
            frameId: 'r',
            stepId: ProcessStepId.retrievalProcessing,
            status: JourneyStageStatus.completed,
          ),
        ],
        isRunning: false,
        understandingSnapshot: RunArtifactsUnderstandingSnapshot(
          userFacingSummary: '我先把问题边界收清。',
          retrievalDesignNarrative: designNarrative,
        ),
        retrievalProcessing: const RetrievalProcessingSnapshot(
          processedDocumentCount: 3,
          acceptedDocumentCount: 1,
          processingSummary: '我已经把能直接支撑回答的资料筛出来。',
          selectedKeyPoints: <String>['结果更新时间一致'],
        ),
        answerProcessing: const RunArtifactsAnswerProcessing(
          readinessSummary: '接下来把资料整理成最终回答。',
          keyFacts: <String>['先说结论再补建议'],
        ),
      );

      expect(built.blocks.first.headline, contains('我先把问题边界收清'));
      expect(built.blocks.first.items, isEmpty);
      expect(built.blocks[1].headline, contains(designNarrative));
      expect(built.blocks[2].kind, AssistantJourneyBlockKind.referenceStats);
      expect(built.blocks[3].items, isEmpty);
      expect(
        built.blocks[3].detail,
        isEmpty,
        reason: '检索处理阶段不再回灌 answerProcessing 或 selectedKeyPoints 生成叙事',
      );
    });

    test('检索引用块不会混入低信号系统状态文案', () {
      final built = _viewModel(
        journey: const AssistantJourney(),
        isRunning: false,
        retrievalProcessing: const RetrievalProcessingSnapshot(
          processedDocumentCount: 10,
          acceptedDocumentCount: 3,
          processingSummary: '已完成资料筛选并进入成答',
          acceptedReferences: <RetrievalProcessingReference>[
            RetrievalProcessingReference(
              title: '深圳天气预报 - nmc.cn',
              url: 'https://www.nmc.cn',
              source: 'nmc.cn',
            ),
          ],
        ),
      );

      expect(
        built.blocks.where(
          (block) => block.kind == AssistantJourneyBlockKind.referenceStats,
        ),
        hasLength(1),
      );
      expect(
        built.blocks.where(
          (block) => block.kind == AssistantJourneyBlockKind.searchSummary,
        ),
        isEmpty,
      );
    });

    testWidgets('journey 完成态会展示 narrative 细节', (tester) async {
      const completedJourney = AssistantJourney(
        stages: <AssistantJourneyStage>[
          AssistantJourneyStage(
            stageId: JourneyStageId.analyze,
            status: JourneyStageStatus.completed,
            order: 0,
            summary: '先把问题主线立住',
          ),
          AssistantJourneyStage(
            stageId: JourneyStageId.answer,
            status: JourneyStageStatus.completed,
            order: 3,
            summary: '已为你整理好',
          ),
        ],
        entries: <AssistantJourneyEntry>[
          AssistantJourneyEntry(
            entryId: 'journey.analyze.done',
            stageId: JourneyStageId.analyze,
            kind: JourneyEntryKind.narrative,
            status: JourneyStageStatus.completed,
            order: 0,
            headline: '先把问题主线立住',
          ),
          AssistantJourneyEntry(
            entryId: 'journey.answer.done',
            stageId: JourneyStageId.answer,
            kind: JourneyEntryKind.narrative,
            status: JourneyStageStatus.completed,
            order: 1,
            headline: '已为你整理好',
            detail: '我把重点条件和答案边界一起收拢了。',
          ),
        ],
        readiness: AssistantJourneyReadiness(finalAnswerReady: true),
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AssistantProcessDrawer(
              viewModel: _viewModel(
                journey: completedJourney,
                isRunning: false,
              ),
              initiallyExpanded: true,
            ),
          ),
        ),
      );

      expect(find.text('已完成处理'), findsOneWidget);
      expect(find.text('先把问题主线立住'), findsOneWidget);
    });

    testWidgets('完成态顶部栏使用统计与耗时模板，不展示结果摘要', (tester) async {
      const completedJourney = AssistantJourney(
        stages: <AssistantJourneyStage>[
          AssistantJourneyStage(
            stageId: JourneyStageId.analyze,
            status: JourneyStageStatus.completed,
            order: 0,
            summary: '先把问题主线立住',
          ),
          AssistantJourneyStage(
            stageId: JourneyStageId.search,
            status: JourneyStageStatus.completed,
            order: 1,
            summary: '已核对 2 个来源',
            referenceCount: 2,
          ),
          AssistantJourneyStage(
            stageId: JourneyStageId.answer,
            status: JourneyStageStatus.completed,
            order: 3,
            summary: '已为你整理好',
          ),
        ],
        entries: <AssistantJourneyEntry>[
          AssistantJourneyEntry(
            entryId: 'journey.search.done',
            stageId: JourneyStageId.search,
            kind: JourneyEntryKind.referenceBundle,
            status: JourneyStageStatus.completed,
            order: 0,
            headline: '已核对 2 个来源',
            references: <AssistantJourneyReference>[
              AssistantJourneyReference(
                title: '四川文旅公告',
                url: 'https://example.com/doc',
                source: '官方',
              ),
              AssistantJourneyReference(
                title: '景区通知',
                url: 'https://example.com/notice',
                source: '景区',
              ),
            ],
          ),
        ],
        referenceSummary: AssistantJourneyReferenceSummary(
          count: 2,
          references: <AssistantJourneyReference>[
            AssistantJourneyReference(
              title: '四川文旅公告',
              url: 'https://example.com/doc',
              source: '官方',
            ),
            AssistantJourneyReference(
              title: '景区通知',
              url: 'https://example.com/notice',
              source: '景区',
            ),
          ],
        ),
        readiness: AssistantJourneyReadiness(finalAnswerReady: true),
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AssistantProcessDrawer(
              viewModel: _viewModel(
                journey: completedJourney,
                isRunning: false,
                elapsedMs: 4200,
              ),
            ),
          ),
        ),
      );

      expect(find.text('已完成处理'), findsOneWidget);
      expect(find.text('处理 2 篇'), findsOneWidget);
      expect(find.text('接纳 2 篇'), findsOneWidget);
      expect(find.text('耗时 4 秒'), findsOneWidget);
      expect(find.text('已核对 2 个来源'), findsNothing);
      expect(find.textContaining('4.2'), findsNothing);
    });

    testWidgets('完成态头部不再展示完成图标，展开后会显示完整参考链接', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AssistantProcessDrawer(
              viewModel: _viewModel(
                journey: _referenceJourney,
                isRunning: false,
                retrievalProcessing: const RetrievalProcessingSnapshot(
                  processedDocumentCount: 4,
                  acceptedDocumentCount: 1,
                  acceptedReferences: <RetrievalProcessingReference>[
                    RetrievalProcessingReference(
                      title: '四川文旅公告',
                      url: 'https://example.com/doc',
                      source: '官方',
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      );

      expect(find.byIcon(CupertinoIcons.checkmark_circle_fill), findsNothing);

      await tester.tap(find.byKey(TestKeys.assistantProcessHeader));
      await tester.pump(const Duration(milliseconds: 300));
      await tester.tap(find.byIcon(CupertinoIcons.chevron_down).last);
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('https://example.com/doc'), findsOneWidget);
    });
  });
}
