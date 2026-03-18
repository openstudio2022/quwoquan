import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/assistant_journey_view_model.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/assistant_process_drawer.dart';

AssistantJourneyViewModel _viewModel({
  AssistantJourney journey = const AssistantJourney(),
  bool isRunning = false,
  int elapsedMs = 0,
}) {
  return buildAssistantJourneyViewModel(
    journey: journey,
    isRunning: isRunning,
    elapsedMs: elapsedMs,
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
      expect(find.text('我在核对最新资料'), findsOneWidget);
      expect(
        find.text(UITextConstants.assistantProcessStageUnderstand),
        findsAtLeastNWidgets(1),
      );
      expect(
        find.text(UITextConstants.assistantProcessStageSearch),
        findsAtLeastNWidgets(1),
      );
      expect(
        find.text(UITextConstants.assistantProcessStageAnalyze),
        findsAtLeastNWidgets(1),
        reason: 'timeline v2 会保留固定 4 主阶段骨架',
      );
      expect(find.text('来源：官方'), findsOneWidget);

      await tester.tap(find.text('我在核对最新资料'));
      await tester.pump();

      expect(find.text('四川文旅公告 · 官方'), findsOneWidget);
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

      expect(find.text('已深度思考，参考 2 篇资料，用时 4 秒'), findsOneWidget);
      expect(find.textContaining('4.2'), findsNothing);
    });
  });
}
