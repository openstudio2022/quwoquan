import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/chat_message_bubble.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/assistant_journey_view_model.dart';

Widget _wrapBubble({
  required Map<String, dynamic> message,
  bool isRight = false,
  VoidCallback? onTap,
  void Function(LongPressStartDetails)? onLongPressStart,
  bool showFeedbackActions = false,
  AssistantJourneyViewModel? journeyViewModel,
  bool answerGateOpen = true,
  bool isAssistantRunning = false,
  String? runningStatusLabel,
}) {
  return MaterialApp(
    home: Scaffold(
      body: SingleChildScrollView(
        child: ChatMessageBubble(
          message: message,
          isRight: isRight,
          bubbleColor: Colors.white,
          textColor: Colors.black,
          isSelectionMode: false,
          isSelected: false,
          onLongPressStart: onLongPressStart ?? (_) {},
          onTap: onTap,
          showFeedbackActions: showFeedbackActions,
          journeyViewModel: journeyViewModel,
          answerGateOpen: answerGateOpen,
          isAssistantRunning: isAssistantRunning,
          runningStatusLabel: runningStatusLabel,
        ),
      ),
    ),
  );
}

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 渲染契约
  // ──────────────────────────────────────────────────────────────────
  group('ChatMessageBubble — 渲染契约', () {
    testWidgets('文本消息正确显示 content', (tester) async {
      final message = <String, dynamic>{
        'type': 'text',
        'content': '你好世界',
        'senderId': 'user_001',
        'senderName': '测试用户',
      };
      await tester.pumpWidget(_wrapBubble(message: message, isRight: true));
      await tester.pump();

      expect(find.text('你好世界'), findsAtLeastNWidgets(1));
    });

    testWidgets('发送者名称正确显示（左侧气泡）', (tester) async {
      final message = <String, dynamic>{
        'type': 'text',
        'content': '一条消息',
        'senderId': 'user_002',
        'senderName': '李明',
      };
      await tester.pumpWidget(_wrapBubble(message: message, isRight: false));
      await tester.pump();

      expect(find.text('李明'), findsOneWidget);
    });

    testWidgets('ChatMessageBubble widget 正确渲染', (tester) async {
      final message = <String, dynamic>{
        'type': 'text',
        'content': '测试消息',
        'senderId': 'user_001',
      };
      await tester.pumpWidget(_wrapBubble(message: message));
      await tester.pump();

      expect(find.byType(ChatMessageBubble), findsOneWidget);
    });

    testWidgets('完整 card fence 渲染为用户可见内容而不是源码残片', (tester) async {
      final message = <String, dynamic>{
        'type': 'text',
        'content':
            '## 华为云盘古分析\n\n```card:compare\n{"title":"差异化优势","vendor":"华为云"}\n```',
        'senderId': AppConceptConstants.assistantSenderId,
      };
      await tester.pumpWidget(_wrapBubble(message: message));
      await tester.pump();

      expect(
        find.textContaining('差异化优势', findRichText: true),
        findsAtLeastNWidgets(1),
      );
      expect(
        find.textContaining('华为云', findRichText: true),
        findsAtLeastNWidgets(1),
      );
      expect(
        find.textContaining('card:compare', findRichText: true),
        findsNothing,
      );
      expect(find.textContaining('```', findRichText: true), findsNothing);
    });

    testWidgets('非法 card fence 不会把 markdown 源码泄漏到界面', (tester) async {
      final message = <String, dynamic>{
        'type': 'text',
        'content':
            '## 查询结论\n\n```card:unknown\n{"title":"内部协议","vendor":"Cursor"}\n```\n\n最终结论仍然保留。',
        'senderId': AppConceptConstants.assistantSenderId,
      };
      await tester.pumpWidget(_wrapBubble(message: message));
      await tester.pump();

      expect(
        find.textContaining('最终结论仍然保留。', findRichText: true),
        findsAtLeastNWidgets(1),
      );
      expect(
        find.textContaining('card:unknown', findRichText: true),
        findsNothing,
      );
      expect(find.textContaining('内部协议', findRichText: true), findsNothing);
      expect(find.textContaining('```', findRichText: true), findsNothing);
    });

    testWidgets('assistant 结构碎片前缀会在最终渲染前被清掉', (tester) async {
      const dirtyMarkdown =
          '[{"id":"route_recommendation","query":"九寨沟 4天 路线","dimension":"route"}]'
          '## 4天路线建议\n\n- 只有 4 天时更推荐西线。';
      final message = <String, dynamic>{
        'type': 'text',
        'content': dirtyMarkdown,
        'displayMarkdown': dirtyMarkdown,
        'displayPlainText':
            '[{"id":"route_recommendation","query":"九寨沟 4天 路线","dimension":"route"}]'
            '只有 4 天时更推荐西线。',
        'senderId': AppConceptConstants.assistantSenderId,
      };
      await tester.pumpWidget(_wrapBubble(message: message));
      await tester.pump();

      expect(
        find.textContaining('4天路线建议', findRichText: true),
        findsAtLeastNWidgets(1),
      );
      expect(
        find.textContaining('route_recommendation', findRichText: true),
        findsNothing,
      );
    });

    testWidgets('assistant 历史消息会从 journey 恢复过程视图', (tester) async {
      final journey = AssistantJourney.fromJson(<String, dynamic>{
        'stages': <Map<String, dynamic>>[
          <String, dynamic>{
            'stageId': 'analyze',
            'status': 'completed',
            'order': 0,
            'summary': '我先把问题主线立住',
          },
          <String, dynamic>{
            'stageId': 'search',
            'status': 'completed',
            'order': 1,
            'summary': '我在核对最新资料',
            'referenceCount': 1,
          },
          <String, dynamic>{
            'stageId': 'answer',
            'status': 'completed',
            'order': 3,
            'summary': '已为你整理好',
          },
        ],
        'entries': <Map<String, dynamic>>[
          <String, dynamic>{
            'entryId': 'journey.analyze.1',
            'stageId': 'analyze',
            'kind': 'narrative',
            'status': 'completed',
            'order': 0,
            'headline': '我先把问题主线立住',
          },
          <String, dynamic>{
            'entryId': 'journey.search.1',
            'stageId': 'search',
            'kind': 'reference_bundle',
            'status': 'completed',
            'order': 1,
            'headline': '我在核对最新资料',
            'detail': '先把会影响路线判断的限制条件收拢。',
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '九寨沟景区公告',
                'url': 'https://example.com/jiuzhaigou',
                'source': '官方',
              },
            ],
          },
        ],
        'summary': '已为你整理好',
        'readiness': <String, dynamic>{
          'nextAction': 'answer',
          'finalAnswerMode': 'full',
          'answerEligibility': 'eligible',
          'finalAnswerReady': true,
        },
      });
      final message = <String, dynamic>{
        'type': 'text',
        'content': '路线建议已经整理好了。',
        'senderId': AppConceptConstants.assistantSenderId,
        ...buildPersistedAssistantTurnFields(
          journey: journey,
          displayMarkdown: '路线建议已经整理好了。',
          displayPlainText: '路线建议已经整理好了。',
          followupPrompt: '',
          actionHints: const <String>[],
          elapsedMs: 4200,
        ),
      };
      await tester.pumpWidget(_wrapBubble(message: message));
      await tester.pump();

      expect(find.byKey(TestKeys.assistantProcessHeader), findsOneWidget);

      await tester.tap(find.byKey(TestKeys.assistantProcessHeader));
      await tester.pump();

      expect(find.text('先把会影响路线判断的限制条件收拢。'), findsOneWidget);
      expect(find.text('处理1篇文档，接纳1篇如下'), findsOneWidget);
      expect(find.text('来源：官方'), findsOneWidget);
      expect(
        find.text(UITextConstants.assistantProcessStageUnderstand),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.assistantProcessStageSearch),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.assistantProcessStageAnswer),
        findsOneWidget,
      );

      await tester.tap(find.text('处理1篇文档，接纳1篇如下'));
      await tester.pump();

      expect(find.text('九寨沟景区公告 · 官方'), findsOneWidget);
    });

    testWidgets('assistant 流式答案出现后仍保留用户可理解的阶段提示', (tester) async {
      final message = <String, dynamic>{
        'type': 'text',
        'content': '',
        'streamFinalAnswer': '九寨沟方向备选方案已经整理出来了。',
        'senderId': AppConceptConstants.assistantSenderId,
      };
      await tester.pumpWidget(
        _wrapBubble(
          message: message,
          journeyViewModel: buildAssistantJourneyViewModel(
            journey: const AssistantJourney(
              stages: <AssistantJourneyStage>[
                AssistantJourneyStage(
                  stageId: JourneyStageId.answer,
                  status: JourneyStageStatus.active,
                  order: 3,
                  summary: '我在组织最终回答',
                ),
              ],
              entries: <AssistantJourneyEntry>[
                AssistantJourneyEntry(
                  entryId: 'journey.answer.streaming',
                  stageId: JourneyStageId.answer,
                  kind: JourneyEntryKind.narrative,
                  status: JourneyStageStatus.active,
                  order: 0,
                  headline: '我在组织最终回答',
                ),
              ],
            ),
            isRunning: true,
          ),
          answerGateOpen: true,
          isAssistantRunning: true,
          runningStatusLabel: UITextConstants.assistantPhaseAnswering,
        ),
      );
      await tester.pump();

      expect(find.textContaining('九寨沟方向备选方案'), findsAtLeastNWidgets(1));
      expect(
        find.text(UITextConstants.assistantProcessStageAnswer),
        findsAtLeastNWidgets(1),
        reason: '答案开始显示后，仍应在答案附近保留当前阶段提示',
      );
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 交互契约
  // ──────────────────────────────────────────────────────────────────
  group('ChatMessageBubble — 交互契约', () {
    testWidgets('长按消息气泡触发 onLongPressStart', (tester) async {
      var longPressed = false;
      final message = <String, dynamic>{
        'type': 'text',
        'content': '长按测试消息',
        'senderId': 'user_001',
      };
      await tester.pumpWidget(
        _wrapBubble(
          message: message,
          isRight: true,
          onLongPressStart: (_) => longPressed = true,
        ),
      );
      await tester.pump();

      final bubble = tester.widget<ChatMessageBubble>(
        find.byType(ChatMessageBubble),
      );
      bubble.onLongPressStart(const LongPressStartDetails());
      await tester.pump();

      expect(longPressed, isTrue);
    });

    testWidgets('tap 消息气泡触发 onTap', (tester) async {
      var tapped = false;
      final message = <String, dynamic>{
        'type': 'text',
        'content': '点击测试消息',
        'senderId': 'user_001',
      };
      await tester.pumpWidget(
        _wrapBubble(
          message: message,
          isRight: true,
          onTap: () => tapped = true,
        ),
      );
      await tester.pump();

      final bubble = tester.widget<ChatMessageBubble>(
        find.byType(ChatMessageBubble),
      );
      bubble.onTap!();
      await tester.pump();

      expect(tapped, isTrue);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 错误态渲染
  // ──────────────────────────────────────────────────────────────────
  group('ChatMessageBubble — 错误态渲染', () {
    testWidgets('空 content 安全渲染', (tester) async {
      final message = <String, dynamic>{
        'type': 'text',
        'content': '',
        'senderId': 'user_001',
      };
      await tester.pumpWidget(_wrapBubble(message: message));
      await tester.pump();

      expect(find.byType(ChatMessageBubble), findsOneWidget);
    });

    testWidgets('null content 安全渲染', (tester) async {
      final message = <String, dynamic>{'type': 'text', 'senderId': 'user_001'};
      await tester.pumpWidget(_wrapBubble(message: message));
      await tester.pump();

      expect(find.byType(ChatMessageBubble), findsOneWidget);
    });

    testWidgets('空 message map 安全渲染', (tester) async {
      await tester.pumpWidget(_wrapBubble(message: const {}));
      await tester.pump();

      expect(find.byType(ChatMessageBubble), findsOneWidget);
    });

    testWidgets('未知 type 安全渲染', (tester) async {
      final message = <String, dynamic>{
        'type': 'unknown_type_xyz',
        'content': '未知类型消息',
        'senderId': 'user_001',
      };
      await tester.pumpWidget(_wrapBubble(message: message));
      await tester.pump();

      expect(find.byType(ChatMessageBubble), findsOneWidget);
    });
  });
}
