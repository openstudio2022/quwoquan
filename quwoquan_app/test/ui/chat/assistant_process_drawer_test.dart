import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/assistant_journey_view_model.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/assistant_process_drawer.dart';

AssistantJourneyViewModel _viewModel({
  AssistantJourney journey = const AssistantJourney(),
  bool isRunning = false,
  int elapsedMs = 0,
  RetrievalProcessingSnapshot retrievalProcessing =
      const RetrievalProcessingSnapshot(),
}) {
  return buildAssistantJourneyViewModel(
    journey: journey,
    isRunning: isRunning,
    elapsedMs: elapsedMs,
    retrievalProcessing: retrievalProcessing,
  );
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
    test('内部规划口吻会转写为用户可读过程文案', () {
      final built = buildAssistantJourneyViewModel(
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

      expect(built.blocks, hasLength(2));
      expect(built.blocks.first.headline, contains('我先确认你真正想解决的是深圳天气'));
      expect(built.blocks[1].headline, contains('我会换几个检索角度继续交叉核对'));
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

      final viewModel = buildAssistantJourneyViewModel(
        journey: journey,
        isRunning: true,
        allowAnswerStage: false,
      );

      expect(viewModel.activeStageId, JourneyStageId.search);
      expect(
        viewModel.activeStageLabel,
        UITextConstants.assistantProcessStageSearch,
      );
      expect(
        viewModel.blocks.any((block) => block.stageId == JourneyStageId.answer),
        isFalse,
      );
    });

    test('空 journey 运行中也不再生成 seeded 假过程', () {
      final viewModel = _viewModel(isRunning: true);

      expect(viewModel.hasVisibleContent, isFalse);
      expect(viewModel.stages, isEmpty);
      expect(viewModel.blocks, isEmpty);
    });

    testWidgets('长等待且无进展时展示 reassurance', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AssistantProcessDrawer(
              viewModel: _viewModel(isRunning: true, elapsedMs: 7000),
            ),
          ),
        ),
      );

      expect(
        find.text(UITextConstants.assistantProcessLongWaitReassurance),
        findsOneWidget,
      );
    });

    testWidgets('三阶段已出现时不在头部插入 reassurance', (tester) async {
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

    testWidgets('短等待时不展示 reassurance', (tester) async {
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
    });

    testWidgets('运行中最小态不再展示耗时秒数', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AssistantProcessDrawer(
              viewModel: _viewModel(isRunning: true, elapsedMs: 9000),
            ),
          ),
        ),
      );

      expect(find.textContaining('耗时'), findsNothing);
    });

    testWidgets('更长等待时升级为 handoff 与 recovery 提示', (tester) async {
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

      expect(
        find.text(UITextConstants.assistantProcessHandoffReassurance),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.assistantProcessRecoveryReassurance),
        findsOneWidget,
      );
    });

    testWidgets('journey 会展示阶段轨道与来源列表', (tester) async {
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
      expect(find.textContaining('接纳1篇'), findsOneWidget);
      expect(
        find.text(UITextConstants.assistantProcessStageUnderstand),
        findsAtLeastNWidgets(1),
      );
      expect(
        find.text(UITextConstants.assistantProcessStageSearch),
        findsAtLeastNWidgets(1),
      );
      expect(
        find.text(UITextConstants.assistantProcessStageAnswer),
        findsNothing,
      );
      expect(find.text('查找信息'), findsNothing);
      expect(find.text('核对结论'), findsNothing);
      expect(find.text('整理回答'), findsNothing);
      expect(find.text('来源：官方'), findsNothing);

      await tester.tap(find.textContaining('接纳1篇'));
      await tester.pump();

      expect(find.text('1. 四川文旅公告 · 官方'), findsOneWidget);
    });

    testWidgets('search query design 会在无 retrieval snapshot 时回退展示', (
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
            summary: '检索词：实时天气：深圳天气 实时 降雨 温度',
          ),
        ],
        entries: <AssistantJourneyEntry>[
          AssistantJourneyEntry(
            entryId: 'journey.search.plan',
            stageId: JourneyStageId.search,
            kind: JourneyEntryKind.narrative,
            status: JourneyStageStatus.active,
            order: 0,
            detail: '我先按最影响结论的几路信息分开核对。\n检索词：实时天气：深圳天气 实时 降雨 温度',
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

      expect(find.text('我会先核对实时天气。'), findsAtLeastNWidgets(1));
      expect(find.textContaining('深圳天气 实时 降雨 温度'), findsNothing);
    });

    test('search 正式 narrative 存在时不会再回退补一遍 summary', () {
      const queryDesign = '我会先把最影响结论的几路信息拆开核对：\n- 体感与当前状态：深圳 天气 当前温度 体感 湿度 风力';
      final built = buildAssistantJourneyViewModel(
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
                block.stageId == JourneyStageId.search &&
                block.kind == AssistantJourneyBlockKind.narrative,
          )
          .toList(growable: false);

      expect(searchNarratives, hasLength(1));
      expect(searchNarratives.single.headline, contains('我会先把最影响结论的几路信息拆开核对'));
      expect(
        built.blocks.where((block) => block.stageId == JourneyStageId.search),
        hasLength(1),
      );
    });

    test('三阶段内容会按理解、检索、接纳文档、成答顺序归位', () {
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
            detail:
                '我开始整理Shenzhen tian qi的关键信息。已获取深圳官方及权威气象站的实时天气数据，信息完整，可直接作答。',
          ),
        ],
        readiness: AssistantJourneyReadiness(finalAnswerReady: true),
      );
      const retrievalProcessing = RetrievalProcessingSnapshot(
        processedDocumentCount: 10,
        acceptedDocumentCount: 3,
        processingSummary: '围绕深圳实时天气、深圳今天天气预报组织检索。\n检索词：深圳 实时天气；深圳今天天气',
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

      final viewModel = buildAssistantJourneyViewModel(
        journey: journey,
        isRunning: false,
        retrievalProcessing: retrievalProcessing,
      );

      expect(
        viewModel.blocks.map((block) => block.stageId).toList(growable: false),
        equals(const <JourneyStageId>[
          JourneyStageId.analyze,
          JourneyStageId.search,
          JourneyStageId.answer,
        ]),
      );
      expect(viewModel.blocks[1].kind, AssistantJourneyBlockKind.searchSummary);
      expect(viewModel.blocks[1].headline, contains('围绕深圳实时天气'));
      expect(viewModel.blocks[1].referenceLabel, '处理10篇文档，接纳3篇如下');
      expect(viewModel.blocks[2].headline, contains('已获取深圳官方及权威气象站的实时天气数据'));
      expect(viewModel.blocks[2].headline, isNot(contains('Shenzhen tian qi')));
    });

    test('检索引用块不会混入低信号系统状态文案', () {
      final built = buildAssistantJourneyViewModel(
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
        built.blocks.any(
          (block) =>
              block.headline.contains('已完成资料筛选') ||
              block.detail.contains('已完成资料筛选'),
        ),
        isFalse,
      );
      expect(
        built.blocks.where(
          (block) => block.kind == AssistantJourneyBlockKind.searchSummary,
        ),
        hasLength(1),
      );
      expect(
        built.blocks
            .singleWhere(
              (block) => block.kind == AssistantJourneyBlockKind.searchSummary,
            )
            .detail,
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

      expect(find.text('已完成深度思考'), findsOneWidget);
      expect(find.text('先把问题主线立住'), findsOneWidget);
      expect(find.text('已为你整理好'), findsAtLeastNWidgets(1));
      expect(find.text('我把重点条件和答案边界一起收拢了。'), findsOneWidget);
    });

    testWidgets('完成态首行摘要使用统一整秒模板', (tester) async {
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

      expect(find.text('已完成深度思考，处理 2 篇文档，耗时 4 秒'), findsOneWidget);
      expect(find.textContaining('4.2'), findsNothing);
    });
  });
}
