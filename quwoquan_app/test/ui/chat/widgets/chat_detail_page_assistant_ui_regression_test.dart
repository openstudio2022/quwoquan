import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/chat_message_bubble.dart';

Widget _bubbleHarness(
  Map<String, dynamic> message, {
  void Function(Map<String, dynamic>)? onReferenceTap,
}) {
  return ScreenUtilInit(
    designSize: const Size(390, 844),
    builder: (_, _) => MaterialApp(
      locale: const Locale('zh'),
      home: Scaffold(
        body: SingleChildScrollView(
          child: ChatMessageBubble(
            message: message,
            isRight: false,
            bubbleColor: Colors.grey.shade200,
            textColor: Colors.black,
            isSelectionMode: false,
            isSelected: false,
            onLongPressStart: (_) {},
            hideAvatarAndName: true,
            useFullWidth: true,
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
    ...extra,
  };
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
        <String, dynamic>{
          'stageId': 'answer',
          'status': 'pending',
          'order': 3,
        },
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
      summary: '正在交叉核实关键结论',
    );
    final message = _assistantMessage(
      id: 'assistant_msg_top_level_journey',
      content: '这是测试回答',
      extra: {'journey': journey},
    );

    await tester.pumpWidget(_bubbleHarness(message));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.textContaining('正在交叉核实关键结论'), findsOneWidget);

    await tester.tap(find.byKey(TestKeys.assistantProcessHeader));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.text(UITextConstants.assistantProcessStageUnderstand), findsOneWidget);
    expect(find.text(UITextConstants.assistantProcessStageSearch), findsOneWidget);
    expect(find.text(UITextConstants.assistantProcessStageAnalyze), findsOneWidget);
    expect(find.text(UITextConstants.assistantProcessStageAnswer), findsOneWidget);
    expect(find.text('先把会影响判断的冲突信息排掉，再组织最终答案。'), findsOneWidget);
  });

  testWidgets('助理过程抽屉可从 runArtifacts.journey 恢复来源摘要', (tester) async {
    Map<String, dynamic>? tappedRef;
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
      summary: '正在整理可直接参考的结论',
      references: references,
    );
    final message = _assistantMessage(
      id: 'assistant_msg_run_artifacts_journey',
      content: '深圳天气晴朗',
      extra: {
        'runArtifacts': <String, dynamic>{'journey': journey},
      },
    );

    await tester.pumpWidget(
      _bubbleHarness(message, onReferenceTap: (ref) => tappedRef = ref),
    );
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.textContaining('正在整理可直接参考的结论'), findsOneWidget);

    await tester.tap(find.byKey(TestKeys.assistantProcessHeader));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text('正在整理可直接参考的结论'));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.text('中国气象局 · weather.cma.cn'), findsOneWidget);

    await tester.tap(find.text('中国气象局 · weather.cma.cn'));
    await tester.pump();

    expect(tappedRef, isNotNull);
    expect(tappedRef!['url'], equals('https://weather.cma.cn/shenzhen'));
  });

  testWidgets('journey 恢复时优先显示用户语言 headline 而不是脏 detail', (
    tester,
  ) async {
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
                'detail':
                    '{"contractVersion":"assistant_turn","queryTasks":[1]}',
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
    expect(find.textContaining('contractVersion'), findsNothing);
    expect(find.textContaining('queryTasks'), findsNothing);
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
              'entryId': 'journey.answer.1',
              'stageId': 'answer',
              'kind': 'narrative',
              'status': 'completed',
              'order': 3,
              'headline': '已汇总成最终建议',
            },
          ],
          summary: '已汇总成最终建议',
        ),
      },
    );

    await tester.pumpWidget(_bubbleHarness(message));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.textContaining('已汇总成最终建议'), findsAtLeastNWidgets(1));

    await tester.tap(find.byKey(TestKeys.assistantProcessHeader));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.textContaining('天气部分已核对完成'), findsOneWidget);
    expect(find.textContaining('出游部分已补充'), findsOneWidget);
    expect(find.textContaining('已汇总成最终建议'), findsAtLeastNWidgets(1));
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
    expect(find.text('产品对比'), findsWidgets);
    expect(find.textContaining('wechat'), findsWidgets);
  });

  testWidgets('助理 Markdown 结构块解析失败时安全降级显示', (tester) async {
    final message = _assistantMessage(
      id: 'assistant_msg_md_fallback',
      content: '```card:compare\nnot-json-payload\n```',
    );

    await tester.pumpWidget(_bubbleHarness(message));
    await tester.pump(const Duration(seconds: 1));

    expect(find.byType(ChatMessageBubble), findsOneWidget);
    expect(find.textContaining('```card:compare'), findsNothing);
  });
}
