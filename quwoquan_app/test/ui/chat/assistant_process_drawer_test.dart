import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/application/capability_gateway.dart';
import 'package:quwoquan_app/assistant/contracts/explainable_flow_event.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/assistant_process_drawer.dart';

void main() {
  group('AssistantProcessDrawer', () {
    testWidgets('长等待且无进展时展示 reassurance', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AssistantProcessDrawer(
              processState: const AssistantProcessState(elapsedMs: 7000),
              isRunning: true,
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
              processState: const AssistantProcessState(elapsedMs: 1500),
              isRunning: true,
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
              children: const [
                AssistantProcessDrawer(
                  processState: AssistantProcessState(elapsedMs: 13000),
                  isRunning: true,
                ),
                AssistantProcessDrawer(
                  processState: AssistantProcessState(elapsedMs: 21000),
                  isRunning: true,
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

    testWidgets('flow events 优先渲染并展示阶段状态与来源列表', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AssistantProcessDrawer(
              processState: const AssistantProcessState(
                contentBlocks: <ProcessContentBlock>[
                  ProcessContentBlock(
                    type: ProcessContentBlockType.text,
                    text: 'legacy block',
                  ),
                ],
              ),
              isRunning: true,
              initiallyExpanded: true,
              flowEvents: const <ExplainableFlowEvent>[
                ExplainableFlowEvent(
                  phaseId: PhaseId.understand,
                  phaseOrder: 0,
                  phaseStatus: ExplainablePhaseStatus.completed,
                  headline: '我先把问题立住',
                ),
                ExplainableFlowEvent(
                  phaseId: PhaseId.execute,
                  phaseOrder: 1,
                  phaseStatus: ExplainablePhaseStatus.active,
                  headline: '我在核对最新资料',
                  references: <FlowReference>[
                    FlowReference(
                      title: '四川文旅公告',
                      url: 'https://example.com/doc',
                      source: '官方',
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      );

      expect(find.text('我在核对最新资料'), findsOneWidget);
      expect(find.text('legacy block'), findsNothing);
      expect(find.text('进行中'), findsOneWidget);
      expect(find.text('已完成 1/2 步'), findsOneWidget);
      expect(
        find.text(UITextConstants.assistantProcessStageUnderstand),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.assistantProcessStageSearch),
        findsOneWidget,
      );
      expect(find.text('已核对 1 个来源'), findsOneWidget);

      await tester.tap(find.text('已核对 1 个来源'));
      await tester.pump();

      expect(find.text('四川文旅公告 · 官方'), findsOneWidget);
    });

    testWidgets('flow events 会按阶段步骤展示完成态与细节', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AssistantProcessDrawer(
              processState: const AssistantProcessState(),
              isRunning: false,
              initiallyExpanded: true,
              flowEvents: const <ExplainableFlowEvent>[
                ExplainableFlowEvent(
                  phaseId: PhaseId.understand,
                  phaseOrder: 0,
                  phaseStatus: ExplainablePhaseStatus.completed,
                  headline: '先把问题主线立住',
                ),
                ExplainableFlowEvent(
                  phaseId: PhaseId.answer,
                  phaseOrder: 1,
                  phaseStatus: ExplainablePhaseStatus.completed,
                  headline: '已为你整理好',
                  detail: '我把重点条件和答案边界一起收拢了。',
                ),
              ],
            ),
          ),
        ),
      );

      expect(find.text('先把问题主线立住'), findsOneWidget);
      expect(find.text('已为你整理好'), findsAtLeastNWidgets(1));
      expect(find.text('已完成'), findsWidgets);
      expect(find.text('我把重点条件和答案边界一起收拢了。'), findsOneWidget);
    });
  });
}
