import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/chat_message_bubble.dart';

/// Helper that wraps a [ChatMessageBubble] inside a minimal widget tree
/// (ScreenUtilInit + MaterialApp + Scaffold) so the bubble can be rendered
/// in isolation without the full ChatDetailPage lifecycle.
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

/// L1b Widget 测试：ChatMessageBubble 助理 UI 回归
///
/// 领域：ui/chat，业务对象：chat_message_bubble（助理消息渲染）
void main() {
  testWidgets('助理过程阶段时间线卡片正常渲染', (tester) async {
    final message = _assistantMessage(
      id: 'assistant_msg_timeline',
      content: '这是测试回答',
      extra: {
        'uiPhaseTimelineV1': <Map<String, dynamic>>[
          <String, dynamic>{
            'phaseId': 'p1',
            'title': '深度思考',
            'summary': '已完成分析',
            'status': 'completed',
          },
          <String, dynamic>{
            'phaseId': 'p2',
            'title': '关键词检索',
            'status': 'completed',
          },
          <String, dynamic>{
            'phaseId': 'p3',
            'title': '资料整理',
            'status': 'completed',
            'details': <String>['汇总了 3 篇文献'],
          },
        ],
      },
    );
    await tester.pumpWidget(_bubbleHarness(message));
    await tester.pump(const Duration(seconds: 1));

    expect(
      find.textContaining('深度思考'),
      findsOneWidget,
      reason: '第一个阶段标题「深度思考」应显示',
    );
    expect(
      find.textContaining('关键词检索'),
      findsOneWidget,
      reason: '第二个阶段标题「关键词检索」应显示',
    );
    expect(
      find.textContaining('资料整理'),
      findsOneWidget,
      reason: '第三个阶段标题「资料整理」应显示',
    );
  });

  testWidgets('助理过程抽屉 searchSummary 参考资料可展开', (tester) async {
    Map<String, dynamic>? tappedRef;
    final message = _assistantMessage(
      id: 'assistant_msg_process',
      content: '参考如下',
      extra: {
        'uiProcessContentBlocks': <Map<String, dynamic>>[
          <String, dynamic>{
            'type': 'searchSummary',
            'text': '检索到 1 篇资料',
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '外部来源标题',
                'url': 'https://example.com/data',
                'source': 'example.com',
              },
            ],
          },
        ],
      },
    );
    await tester.pumpWidget(
      _bubbleHarness(message, onReferenceTap: (ref) => tappedRef = ref),
    );
    await tester.pump(const Duration(seconds: 1));

    expect(
      find.textContaining('已完成'),
      findsOneWidget,
      reason: '过程抽屉头部应显示「已完成」阶段标签',
    );

    await tester.tap(find.textContaining('已完成'));
    await tester.pump(const Duration(milliseconds: 300));

    expect(
      find.textContaining('检索到 1 篇资料'),
      findsOneWidget,
      reason: '展开抽屉后应显示 searchSummary 文案',
    );

    await tester.tap(find.textContaining('检索到 1 篇资料'));
    await tester.pump(const Duration(milliseconds: 300));

    expect(
      find.textContaining('外部来源标题'),
      findsOneWidget,
      reason: '展开 searchSummary 后应显示参考资料标题',
    );

    await tester.tap(find.textContaining('外部来源标题'));
    await tester.pump();

    expect(tappedRef, isNotNull, reason: 'onReferenceTap 应被触发');
    expect(tappedRef!['url'], 'https://example.com/data');
  });

  testWidgets('助理过程抽屉可从 uiProcessTimelineV2 恢复', (tester) async {
    final message = _assistantMessage(
      id: 'assistant_msg_timeline_v2',
      content: '深圳天气晴朗',
      extra: {
        'uiProcessTimelineV2': <Map<String, dynamic>>[
          <String, dynamic>{
            'scope': 'root',
            'type': 'processReplace',
            'nodeId': 'root.intent',
            'summary': '已识别问题方向，准备开始处理',
            'references': const <Map<String, dynamic>>[],
          },
          <String, dynamic>{
            'scope': 'aggregation',
            'type': 'processCommit',
            'nodeId': 'aggregation.final',
            'summary': '已核对 2 个来源，正在整理可直接参考的结论',
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '中国气象局',
                'url': 'https://weather.cma.cn/shenzhen',
                'source': 'weather.cma.cn',
              },
            ],
          },
        ],
      },
    );
    await tester.pumpWidget(_bubbleHarness(message));
    await tester.pump(const Duration(milliseconds: 300));

    expect(
      find.textContaining('已核对 2 个来源'),
      findsOneWidget,
      reason: '应优先从 uiProcessTimelineV2 恢复完成态摘要',
    );

    await tester.tap(find.textContaining('已核对 2 个来源').first);
    await tester.pump(const Duration(milliseconds: 300));

    await tester.tap(find.textContaining('已核对 2 个来源').last);
    await tester.pump(const Duration(milliseconds: 300));

    expect(
      find.textContaining('中国气象局'),
      findsOneWidget,
      reason: 'timeline v2 中的来源应可展开显示',
    );
  });

  testWidgets('多 skill timeline 可同时恢复 root/skill/aggregation 过程', (
    tester,
  ) async {
    final message = _assistantMessage(
      id: 'assistant_msg_multiskill_timeline_v2',
      content: '深圳天气与出游建议',
      extra: {
        'uiProcessTimelineV2': <Map<String, dynamic>>[
          <String, dynamic>{
            'scope': 'root',
            'type': 'processReplace',
            'nodeId': 'root.intent',
            'summary': '我先拆成天气和出游两部分分别处理',
            'references': const <Map<String, dynamic>>[],
          },
          <String, dynamic>{
            'scope': 'skill',
            'type': 'processCommit',
            'nodeId': 'weather',
            'runId': 'skill_weather_1',
            'summary': '天气部分已核对完成，适合轻松出门',
            'references': const <Map<String, dynamic>>[],
          },
          <String, dynamic>{
            'scope': 'skill',
            'type': 'processCommit',
            'nodeId': 'fallback_general_search',
            'runId': 'skill_travel_1',
            'summary': '出游部分已补充室内外备选方案',
            'references': const <Map<String, dynamic>>[],
          },
          <String, dynamic>{
            'scope': 'aggregation',
            'type': 'processCommit',
            'nodeId': 'aggregation.final',
            'summary': '已汇总成最终建议',
            'references': const <Map<String, dynamic>>[],
          },
        ],
      },
    );
    await tester.pumpWidget(_bubbleHarness(message));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.textContaining('已汇总成最终建议'), findsOneWidget);

    await tester.tap(find.textContaining('已汇总成最终建议'));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.textContaining('天气部分已核对完成'), findsOneWidget);
    expect(find.textContaining('出游部分已补充'), findsOneWidget);
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

    expect(find.textContaining('not-json-payload'), findsWidgets);
  });
}
