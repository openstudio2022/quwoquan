import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_journey_view_model.dart';
import 'package:quwoquan_app/assistant/transcript/citation/assistant_citation.dart';
import 'package:quwoquan_app/assistant/transcript/persisted_timeline/persisted_timeline_turn_codec.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_message_bubble.dart';

Widget _bubbleHarness(
  Map<String, dynamic> message, {
  void Function(AssistantCitation)? onReferenceTap,
  AssistantJourneyViewModel? journeyViewModel,
  bool answerGateOpen = true,
  bool isAssistantRunning = false,
  String? runningStatusLabel,
}) {
  final transcriptRow = PersistedTimelineTurnCodec.decode(message);
  return ScreenUtilInit(
    designSize: const Size(390, 844),
    builder: (_, _) => MaterialApp(
      locale: const Locale('zh'),
      home: Scaffold(
        body: SingleChildScrollView(
          child: AssistantMessageBubble(
            transcriptRow: transcriptRow,
            isRight: message['isSelf'] == true,
            bubbleColor: Colors.grey.shade200,
            textColor: Colors.black,
            isSelectionMode: false,
            isSelected: false,
            onLongPressStart: (_) {},
            hideAvatarAndName: true,
            useFullWidth: true,
            renderSelfTextWithoutBubble: true,
            journeyViewModel: journeyViewModel,
            answerGateOpen: answerGateOpen,
            isAssistantRunning: isAssistantRunning,
            runningStatusLabel: runningStatusLabel,
            onReferenceTap: onReferenceTap,
          ),
        ),
      ),
    ),
  );
}

Map<String, dynamic> _assistantMessage({
  required String id,
  required String content,
  Map<String, dynamic> extra = const <String, dynamic>{},
}) {
  final journey = _extractJourney(extra);
  final effectiveJourney = journey ?? const AssistantJourney();
  final processTimeline = journey == null
      ? const <ProcessTimelineFrame>[]
      : buildProcessTimelineFramesFromJourneyFallback(effectiveJourney);
  return <String, dynamic>{
    'id': id,
    'conversationId': AppConceptConstants.assistantConversationId,
    'type': 'text',
    'content': content,
    'senderId': AppConceptConstants.assistantSenderId,
    'senderName': AppConceptConstants.assistantLabel,
    'senderAvatar': '',
    'timestamp': '10:10',
    'isRead': true,
    'isSelf': false,
    ...buildPersistedAssistantTurnFields(
      journey: effectiveJourney,
      processTimeline: processTimeline,
      displayMarkdown: content,
      displayPlainText: content,
      followupPrompt: '',
      actionHints: const <String>[],
      elapsedMs: 4200,
    ),
    ...extra,
  };
}

AssistantJourney? _extractJourney(Map<String, dynamic> extra) {
  final topLevel = extra['journey'];
  if (topLevel is Map) {
    return AssistantJourney.fromJson(topLevel.cast<String, dynamic>());
  }
  final runArtifacts = (extra['runArtifacts'] as Map?)?.cast<String, dynamic>();
  final nested = runArtifacts?['journey'];
  if (nested is Map) {
    return AssistantJourney.fromJson(nested.cast<String, dynamic>());
  }
  return null;
}

Map<String, dynamic> _journeyPayload({
  required List<Map<String, dynamic>> stages,
  required List<Map<String, dynamic>> entries,
  String summary = '',
  List<Map<String, dynamic>> references = const <Map<String, dynamic>>[],
  bool finalAnswerReady = true,
}) {
  return <String, dynamic>{
    'stages': stages,
    'entries': entries,
    'summary': summary,
    'referenceSummary': <String, dynamic>{
      'count': references.length,
      'references': references,
    },
    'readiness': <String, dynamic>{
      'nextAction': 'answer',
      'finalAnswerMode': 'full',
      'answerEligibility': finalAnswerReady ? 'eligible' : 'draft',
      'finalAnswerReady': finalAnswerReady,
    },
  };
}

void main() {
  testWidgets('助理过程轨道可从顶层 journey 渲染', (tester) async {
    final journey = _journeyPayload(
      stages: <Map<String, dynamic>>[
        <String, dynamic>{
          'stageId': 'analyze',
          'status': 'completed',
          'order': 0,
          'summary': '先确认需求边界',
        },
        <String, dynamic>{
          'stageId': 'search',
          'status': 'completed',
          'order': 1,
          'summary': '已补齐检索材料',
          'referenceCount': 1,
        },
        <String, dynamic>{
          'stageId': 'verify',
          'status': 'active',
          'order': 2,
          'summary': '正在交叉核实关键结论',
          'referenceCount': 1,
        },
        <String, dynamic>{'stageId': 'answer', 'status': 'pending', 'order': 3},
      ],
      entries: <Map<String, dynamic>>[
        <String, dynamic>{
          'entryId': 'journey.verify.1',
          'stageId': 'verify',
          'kind': 'narrative',
          'status': 'active',
          'order': 2,
          'headline': '正在交叉核实关键结论',
          'detail': '先把会影响判断的冲突信息排掉，再组织最终答案。',
        },
      ],
      finalAnswerReady: false,
      summary: '正在交叉核实关键结论',
    );
    final message = _assistantMessage(
      id: 'assistant_msg_top_level_journey',
      content: '这是测试回答',
      extra: {'journey': journey},
    );

    await tester.pumpWidget(_bubbleHarness(message));
    await tester.pump(const Duration(milliseconds: 300));

    expect(
      find.text(UITextConstants.assistantProcessCompletedSummary),
      findsOneWidget,
    );
    expect(find.text('耗时 4 秒'), findsOneWidget);

    await tester.tap(find.byKey(TestKeys.assistantProcessHeader));
    await tester.pump(const Duration(milliseconds: 300));

    expect(
      find.text(UITextConstants.assistantProcessStageUnderstand),
      findsNothing,
    );
    expect(
      find.text(UITextConstants.assistantProcessStageSearch),
      findsNothing,
    );
    expect(find.textContaining('正在交叉核实关键结论'), findsAtLeastNWidgets(1));
    expect(
      find.text(UITextConstants.assistantProcessStageAnswer),
      findsNothing,
    );
  });

  testWidgets('助理过程抽屉可从 runArtifacts.journey 恢复来源摘要', (tester) async {
    AssistantCitation? tappedRef;
    final references = <Map<String, dynamic>>[
      <String, dynamic>{
        'title': '中国气象局',
        'url': 'https://weather.cma.cn/shenzhen',
        'source': 'weather.cma.cn',
      },
    ];
    final journey = _journeyPayload(
      stages: <Map<String, dynamic>>[
        <String, dynamic>{
          'stageId': 'search',
          'status': 'completed',
          'order': 1,
          'summary': '已核对 1 个天气来源',
          'referenceCount': 1,
        },
        <String, dynamic>{
          'stageId': 'verify',
          'status': 'active',
          'order': 2,
          'summary': '正在整理可直接参考的结论',
          'referenceCount': 1,
        },
      ],
      entries: <Map<String, dynamic>>[
        <String, dynamic>{
          'entryId': 'journey.verify.1',
          'stageId': 'verify',
          'kind': 'reference_bundle',
          'status': 'active',
          'order': 2,
          'headline': '正在整理可直接参考的结论',
          'references': references,
        },
      ],
      finalAnswerReady: false,
      summary: '正在整理可直接参考的结论',
      references: references,
    );
    final message = _assistantMessage(
      id: 'assistant_msg_run_artifacts_journey',
      content: '深圳天气晴朗',
      extra: {
        assistantRetrievalProcessingField: <String, dynamic>{
          'processedDocumentCount': 1,
          'acceptedDocumentCount': 1,
          'processingSummary': '已核对 1 个天气来源',
          'acceptedReferences': references,
        },
        'runArtifacts': <String, dynamic>{'journey': journey},
      },
    );

    await tester.pumpWidget(
      _bubbleHarness(message, onReferenceTap: (ref) => tappedRef = ref),
    );
    await tester.pump(const Duration(milliseconds: 300));

    expect(
      find.text(UITextConstants.assistantProcessCompletedSummary),
      findsOneWidget,
    );
    expect(find.text('搜索 1 篇'), findsOneWidget);
    expect(find.text('接纳 1 篇'), findsOneWidget);
    expect(find.text('耗时 4 秒'), findsOneWidget);

    await tester.tap(find.byKey(TestKeys.assistantProcessHeader));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.textContaining('正在整理可直接参考的结论'), findsAtLeastNWidgets(1));
    await tester.tap(find.textContaining('搜索了 1 篇').last);
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.text('1. 中国气象局'), findsOneWidget);

    await tester.tap(find.text('1. 中国气象局'));
    await tester.pump();

    expect(tappedRef, isNotNull);
    expect(tappedRef!.url, equals('https://weather.cma.cn/shenzhen'));
  });

  testWidgets('journey 恢复时优先显示用户语言 headline 而不是脏 detail', (tester) async {
    final message = _assistantMessage(
      id: 'assistant_msg_process_reason_short',
      content: '最终回答',
      extra: {
        'runArtifacts': {
          'journey': _journeyPayload(
            stages: <Map<String, dynamic>>[
              <String, dynamic>{
                'stageId': 'analyze',
                'status': 'completed',
                'order': 0,
                'summary': '先确认问题落点，后面的资料才更容易收敛。',
              },
            ],
            entries: <Map<String, dynamic>>[
              <String, dynamic>{
                'entryId': 'journey.analyze.reason_short',
                'stageId': 'analyze',
                'kind': 'narrative',
                'status': 'completed',
                'order': 0,
                'headline': '先确认问题落点，后面的资料才更容易收敛。',
                'detail': '{"contractId":"assistant_turn","searchPlans":[1]}',
              },
            ],
            summary: '先确认问题落点，后面的资料才更容易收敛。',
          ),
        },
      },
    );

    await tester.pumpWidget(_bubbleHarness(message));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.byKey(TestKeys.assistantProcessHeader));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.textContaining('先确认问题落点'), findsAtLeastNWidgets(1));
    expect(find.textContaining('contractId'), findsNothing);
    expect(find.textContaining('searchPlans'), findsNothing);
  });

  testWidgets('多阶段多条目 journey 可同时恢复分析检索核实与成答文案', (tester) async {
    final message = _assistantMessage(
      id: 'assistant_msg_multi_stage_journey',
      content: '深圳天气与出游建议',
      extra: {
        'journey': _journeyPayload(
          stages: <Map<String, dynamic>>[
            <String, dynamic>{
              'stageId': 'analyze',
              'status': 'completed',
              'order': 0,
              'summary': '先拆清楚天气和出游两个判断面',
            },
            <String, dynamic>{
              'stageId': 'search',
              'status': 'completed',
              'order': 1,
              'summary': '天气资料和游玩资料都已补齐',
            },
            <String, dynamic>{
              'stageId': 'verify',
              'status': 'completed',
              'order': 2,
              'summary': '已经交叉核实关键差异',
            },
            <String, dynamic>{
              'stageId': 'answer',
              'status': 'completed',
              'order': 3,
              'summary': '已汇总成最终建议',
            },
          ],
          entries: <Map<String, dynamic>>[
            <String, dynamic>{
              'entryId': 'journey.analyze.1',
              'stageId': 'analyze',
              'kind': 'narrative',
              'status': 'completed',
              'order': 0,
              'headline': '先拆清楚天气和出游两个判断面',
            },
            <String, dynamic>{
              'entryId': 'journey.search.weather',
              'stageId': 'search',
              'kind': 'narrative',
              'status': 'completed',
              'order': 1,
              'headline': '天气部分已核对完成，适合轻松出门',
            },
            <String, dynamic>{
              'entryId': 'journey.search.travel',
              'stageId': 'search',
              'kind': 'narrative',
              'status': 'completed',
              'order': 2,
              'headline': '出游部分已补充室内外备选方案',
            },
            <String, dynamic>{
              'entryId': 'journey.verify.1',
              'stageId': 'verify',
              'kind': 'narrative',
              'status': 'completed',
              'order': 3,
              'headline': '已经交叉核实关键差异',
            },
            <String, dynamic>{
              'entryId': 'journey.answer.1',
              'stageId': 'answer',
              'kind': 'narrative',
              'status': 'completed',
              'order': 4,
              'headline': '已汇总成最终建议',
            },
          ],
          summary: '已汇总成最终建议',
        ),
      },
    );

    await tester.pumpWidget(_bubbleHarness(message));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.textContaining('已完成处理'), findsAtLeastNWidgets(1));

    await tester.tap(find.byKey(TestKeys.assistantProcessHeader));
    await tester.pump(const Duration(milliseconds: 300));

    expect(
      find.text(UITextConstants.assistantProcessStageUnderstand),
      findsNothing,
    );
    expect(find.textContaining('先拆清楚天气和出游两个判断面'), findsAtLeastNWidgets(1));
    expect(find.textContaining('已经交叉核实关键差异'), findsAtLeastNWidgets(1));
  });

  testWidgets('助理 Markdown 与 card block 按层次渲染', (tester) async {
    final message = _assistantMessage(
      id: 'assistant_msg_md',
      content:
          '# 结论\n- 建议：先做流式\n\n```card:compare\n{"title":"产品对比","wechat":"强关系","xiaohongshu":"内容决策"}\n```',
    );

    await tester.pumpWidget(_bubbleHarness(message));
    await tester.pump(const Duration(seconds: 1));

    expect(find.text('结论'), findsWidgets);
    expect(find.textContaining('先做流式'), findsWidgets);
    expect(find.textContaining('```card:compare'), findsNothing);
  });

  testWidgets('助理 Markdown 结构块解析失败时安全降级显示', (tester) async {
    final message = _assistantMessage(
      id: 'assistant_msg_md_fallback',
      content: '```card:compare\nnot-json-payload\n```',
    );

    await tester.pumpWidget(_bubbleHarness(message));
    await tester.pump(const Duration(seconds: 1));

    expect(find.byType(AssistantMessageBubble), findsOneWidget);
    expect(find.textContaining('```card:compare'), findsNothing);
  });

  testWidgets('assistant 结构碎片前缀会在最终渲染前被清掉', (tester) async {
    const dirtyMarkdown =
        '[{"id":"route_recommendation","query":"九寨沟 4天 路线","dimension":"route"}]'
        '## 4天路线建议\n\n- 只有 4 天时更推荐西线。';
    final message = _assistantMessage(
      id: 'assistant_msg_dirty_prefix',
      content: dirtyMarkdown,
      extra: {
        'displayMarkdown': dirtyMarkdown,
        'displayPlainText':
            '[{"id":"route_recommendation","query":"九寨沟 4天 路线","dimension":"route"}]'
            '只有 4 天时更推荐西线。',
      },
    );

    await tester.pumpWidget(_bubbleHarness(message));
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

  testWidgets('assistant 流式答案出现后仍保留用户可理解的阶段提示', (tester) async {
    final message = _assistantMessage(
      id: 'assistant_msg_streaming',
      content: '',
      extra: {
        assistantDisplayStateField: const AssistantDisplayState(
          answer: AssistantAnswerDisplayState(
            blocks: <AssistantAnswerDisplayBlock>[
              AssistantAnswerDisplayBlock(
                blockId: 'streaming_answer',
                kind: DisplayBlockKind.markdown,
                body: '九寨沟方向备选方案已经整理出来了。',
              ),
            ],
          ),
        ).toJson(),
      },
    );

    await tester.pumpWidget(
      _bubbleHarness(
        message,
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
          processTimeline: const [],
          isRunning: true,
        ),
        answerGateOpen: true,
        isAssistantRunning: true,
        runningStatusLabel: UITextConstants.assistantPhaseAnswering,
      ),
    );
    await tester.pump();

    expect(find.textContaining('九寨沟方向备选方案'), findsAtLeastNWidgets(1));
  });

  testWidgets('assistant 流式中会直接渲染 displayState answer 预览', (tester) async {
    final message = _assistantMessage(
      id: 'assistant_msg_streaming_preview',
      content: '旧的完成态答案',
      extra: {
        assistantDisplayStateField: const AssistantDisplayState(
          answer: AssistantAnswerDisplayState(
            blocks: <AssistantAnswerDisplayBlock>[
              AssistantAnswerDisplayBlock(
                blockId: 'streaming_answer_preview',
                kind: DisplayBlockKind.markdown,
                body: '先给结论：经典线更稳妥，再按天气决定是否串黄龙。',
              ),
            ],
          ),
        ).toJson(),
      },
    );

    await tester.pumpWidget(
      _bubbleHarness(
        message,
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
                entryId: 'journey.answer.streaming.sections',
                stageId: JourneyStageId.answer,
                kind: JourneyEntryKind.narrative,
                status: JourneyStageStatus.active,
                order: 0,
                headline: '我在组织最终回答',
              ),
            ],
          ),
          processTimeline: const [],
          isRunning: true,
        ),
        answerGateOpen: true,
        isAssistantRunning: true,
        runningStatusLabel: UITextConstants.assistantPhaseAnswering,
      ),
    );
    await tester.pump();

    expect(find.textContaining('经典线更稳妥', findRichText: true), findsWidgets);
    expect(find.textContaining('旧的完成态答案', findRichText: true), findsNothing);
  });

  testWidgets('assistant 流式中 answer gate 关闭时不会渲染 displayState answer 预览', (
    tester,
  ) async {
    final message = _assistantMessage(
      id: 'assistant_msg_streaming_preview_blocked',
      content: '旧的完成态答案',
      extra: {
        assistantDisplayStateField: const AssistantDisplayState(
          answer: AssistantAnswerDisplayState(
            blocks: <AssistantAnswerDisplayBlock>[
              AssistantAnswerDisplayBlock(
                blockId: 'streaming_answer_preview_blocked',
                kind: DisplayBlockKind.markdown,
                body: '这段流式答案不应在 gate 关闭时提前露出。',
              ),
            ],
          ),
        ).toJson(),
      },
    );

    await tester.pumpWidget(
      _bubbleHarness(
        message,
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
                entryId: 'journey.answer.streaming.blocked',
                stageId: JourneyStageId.answer,
                kind: JourneyEntryKind.narrative,
                status: JourneyStageStatus.active,
                order: 0,
                headline: '我在组织最终回答',
              ),
            ],
          ),
          processTimeline: const <ProcessTimelineFrame>[
            ProcessTimelineFrame(
              frameId: 'streaming_gate_closed_understanding',
              stepId: ProcessStepId.understanding,
              status: JourneyStageStatus.active,
              headline: '我在继续收清问题边界',
            ),
          ],
          isRunning: true,
        ),
        answerGateOpen: false,
        isAssistantRunning: true,
        runningStatusLabel: UITextConstants.assistantPhaseAnswering,
      ),
    );
    await tester.pump();

    expect(
      find.textContaining('这段流式答案不应在 gate 关闭时提前露出。', findRichText: true),
      findsNothing,
    );
    expect(find.textContaining('旧的完成态答案', findRichText: true), findsNothing);
  });

  testWidgets('completed displayMarkdown 会优先渲染自然最终成答并保留引用', (tester) async {
    AssistantCitation? tappedRef;
    const structuredMarkdown =
        '深圳今天有雨，外出建议带伞。[1](https://weather.cma.cn/shenzhen)\n\n'
        '如果你会晚点出门，带把折叠伞更稳妥。';
    final message = _assistantMessage(
      id: 'assistant_msg_natural_completed',
      content: '旧的一句话答案',
      extra: {
        'displayMarkdown': structuredMarkdown,
        'displayPlainText': '深圳今天有雨，外出建议带伞。如果你会晚点出门，带把折叠伞更稳妥。',
        'runArtifacts': <String, dynamic>{
          'displayMarkdown': structuredMarkdown,
          'displayPlainText': '深圳今天有雨，外出建议带伞。如果你会晚点出门，带把折叠伞更稳妥。',
          'answerEvidenceBindings': <Map<String, dynamic>>[
            <String, dynamic>{
              'bindingId': 'binding_weather_1',
              'label': '来源1',
              'claim': '深圳今天有雨，外出建议带伞。',
              'evidenceId': 'weather_ev_1',
              'url': 'https://weather.cma.cn/shenzhen',
              'title': '深圳天气预报 - 中国气象局',
              'source': 'weather.cma.cn',
              'snippet': '深圳今天有雨，外出建议带伞。',
            },
          ],
        },
      },
    );

    await tester.pumpWidget(
      _bubbleHarness(message, onReferenceTap: (ref) => tappedRef = ref),
    );
    await tester.pump();

    expect(find.text('旧的一句话答案'), findsNothing);
    expect(find.textContaining('深圳今天有雨', findRichText: true), findsWidgets);
    expect(find.textContaining('问题理解', findRichText: true), findsNothing);
    expect(
      find.byKey(const ValueKey<String>('assistant_reference_chip_1')),
      findsOneWidget,
    );

    await tester.tap(
      find.byKey(const ValueKey<String>('assistant_reference_chip_1')),
    );
    await tester.pump();

    expect(tappedRef, isNotNull);
    expect(tappedRef!.url, equals('https://weather.cma.cn/shenzhen'));
  });

  testWidgets('answerEvidenceBindings 会渲染为可点击递增角标', (tester) async {
    AssistantCitation? tappedRef;
    final message = _assistantMessage(
      id: 'assistant_msg_citations',
      content:
          '这条结论来自官方仓库[1](https://github.com/flutter/flutter)，补充解释见文档中心[2](https://developer.mozilla.org/zh-CN/)。',
      extra: {
        'runArtifacts': <String, dynamic>{
          'answerEvidenceBindings': <Map<String, dynamic>>[
            <String, dynamic>{
              'bindingId': 'binding_1',
              'label': '来源1',
              'claim': '官方仓库',
              'evidenceId': 'evidence_1',
              'url': 'https://github.com/flutter/flutter',
              'title': 'Flutter GitHub 仓库',
              'source': 'github.com',
              'snippet': 'Flutter SDK 与框架源码仓库',
            },
            <String, dynamic>{
              'bindingId': 'binding_2',
              'label': '来源2',
              'claim': '文档中心',
              'evidenceId': 'evidence_2',
              'url': 'https://developer.mozilla.org/zh-CN/',
              'title': 'MDN Web Docs',
              'source': 'developer.mozilla.org',
              'snippet': '文档中心',
            },
          ],
        },
      },
    );

    await tester.pumpWidget(
      _bubbleHarness(message, onReferenceTap: (ref) => tappedRef = ref),
    );
    await tester.pump();

    expect(
      find.byKey(const ValueKey<String>('assistant_reference_chip_1')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('assistant_reference_chip_2')),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.assistantReferenceSectionTitle),
      findsNothing,
    );

    await tester.tap(
      find.byKey(const ValueKey<String>('assistant_reference_chip_2')),
    );
    await tester.pump();

    expect(tappedRef, isNotNull);
    expect(tappedRef!.url, equals('https://developer.mozilla.org/zh-CN/'));
    expect(tappedRef!.source, equals('developer.mozilla.org'));
  });
}
