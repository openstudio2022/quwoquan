import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/application/assistant_gateway.dart';
import 'package:quwoquan_app/assistant/application/local_assistant_entry.dart';
import 'package:quwoquan_app/assistant/application/assistant_request_policy.dart';
import 'package:quwoquan_app/assistant/application/assistant_providers.dart';
import 'package:quwoquan_app/assistant/application/assistant_run_stream.dart';
import 'package:quwoquan_app/assistant/application/remote_assistant_entry.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/domain/channel/channel.dart';
import 'package:quwoquan_app/assistant/domain/conversation/conversation.dart';
import 'package:quwoquan_app/assistant/infrastructure/infrastructure.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_conversation_page.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_reference_webview_page.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_message_bubble.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/assistant_process_drawer.dart';
import 'package:webview_flutter_platform_interface/webview_flutter_platform_interface.dart';

void main() {
  setUpAll(() {
    WebViewPlatform.instance = _FakeWebViewPlatform();
  });

  testWidgets('assistant 对话页使用外置语音按钮与发送按钮', (tester) async {
    final localEntry = _ControlledLocalAssistantEntry();
    addTearDown(localEntry.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatRepositoryProvider.overrideWithValue(
            _EmptyAssistantChatRepository(),
          ),
          relationshipCapabilityRepositoryProvider.overrideWithValue(
            _AssistantCapabilityRepository(),
          ),
          assistantGatewayProvider.overrideWithValue(
            _ImmediateAssistantGateway(
              const AssistantRunResponse(
                finalText: '',
                traces: <AssistantTraceEvent>[],
              ),
            ),
          ),
          localAssistantEntryProvider.overrideWithValue(localEntry),
        ],
        child: MaterialApp(
          home: Scaffold(body: AssistantConversationPage(onBack: _noop)),
        ),
      ),
    );

    await _pumpUntil(
      tester,
      condition: () =>
          find.byKey(TestKeys.assistantChatInputField).evaluate().isNotEmpty,
    );

    expect(find.byKey(TestKeys.chatInputVoiceToggleButton), findsOneWidget);
    expect(find.byKey(TestKeys.chatInputMoreButton), findsOneWidget);
    expect(find.byKey(TestKeys.assistantSendButton), findsNothing);

    await tester.enterText(
      find.byKey(TestKeys.assistantChatInputField),
      '帮我整理一下这个问题',
    );
    await tester.pump();
    await _pumpUntil(
      tester,
      condition: () =>
          find.byKey(TestKeys.assistantSendButton).evaluate().isNotEmpty,
    );

    expect(find.byKey(TestKeys.assistantSendButton), findsOneWidget);
    expect(find.byKey(TestKeys.chatInputMoreButton), findsNothing);
  });

  testWidgets('远端未配置时 assistant 对话页会自动回落本地 backend', (tester) async {
    final localEntry = _ControlledLocalAssistantEntry();
    addTearDown(localEntry.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatRepositoryProvider.overrideWithValue(
            _EmptyAssistantChatRepository(),
          ),
          relationshipCapabilityRepositoryProvider.overrideWithValue(
            _AssistantCapabilityRepository(),
          ),
          assistantGatewayProvider.overrideWithValue(
            _ImmediateAssistantGateway(
              const AssistantRunResponse(
                finalText: '',
                traces: <AssistantTraceEvent>[],
              ),
            ),
          ),
          localAssistantEntryProvider.overrideWithValue(localEntry),
        ],
        child: MaterialApp(
          home: Scaffold(body: AssistantConversationPage(onBack: _noop)),
        ),
      ),
    );
    await _pumpUntil(
      tester,
      condition: () => find.byType(TextField).evaluate().isNotEmpty,
    );

    await tester.tap(find.byType(TextField).last);
    await tester.pump();
    await tester.enterText(find.byType(TextField).last, 'Shenzhen tian qi');
    await _pumpUntil(
      tester,
      condition: () =>
          find.byIcon(Icons.arrow_upward_rounded).evaluate().isNotEmpty,
    );
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await localEntry.waitUntilSubscribed();
    localEntry.emit(AssistantRunStreamEvent.answerDelta('深圳今天天气晴，适合出行。'));
    localEntry.emit(
      AssistantRunStreamEvent.completed(
        const AssistantRunResponse(
          finalText: '深圳今天天气晴，适合出行。',
          traces: <AssistantTraceEvent>[],
          structuredResponse: <String, dynamic>{
            'runArtifacts': <String, dynamic>{
              'displayMarkdown': '深圳今天天气晴，适合出行。',
              'displayPlainText': '深圳今天天气晴，适合出行。',
            },
          },
        ),
      ),
    );
    await _pumpUntil(
      tester,
      condition: () => find
          .byWidgetPredicate(
            (widget) =>
                widget is AssistantMessageBubble &&
                (widget.message['senderId'] as String?) ==
                    AppConceptConstants.assistantSenderId &&
                (((widget.message['content'] as String?) ?? '').contains(
                      '深圳今天天气晴，适合出行。',
                    ) ||
                    _assistantAnswerMarkdownFromBubble(
                      widget,
                    ).contains('深圳今天天气晴，适合出行。')),
          )
          .evaluate()
          .isNotEmpty,
    );

    final bubble = _latestAssistantBubble(tester);
    final content = (bubble.message['content'] as String?) ?? '';
    final mergedAnswer =
        '$content${_assistantAnswerMarkdownFromBubble(bubble)}';
    expect(mergedAnswer, contains('深圳今天天气晴，适合出行。'));
    expect(mergedAnswer, isNot(contains('remote_stream_incomplete')));
  });

  testWidgets('assistant answerDelta 会逐步追加，completed 不重建 message id', (
    tester,
  ) async {
    final gateway = _ControlledRemoteAssistantEntry();
    addTearDown(gateway.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatRepositoryProvider.overrideWithValue(
            _EmptyAssistantChatRepository(),
          ),
          relationshipCapabilityRepositoryProvider.overrideWithValue(
            _AssistantCapabilityRepository(),
          ),
          assistantRemoteConfiguredProvider.overrideWith((ref) => true),
          remoteAssistantEntryProvider.overrideWithValue(gateway),
        ],
        child: MaterialApp(
          home: Scaffold(body: AssistantConversationPage(onBack: _noop)),
        ),
      ),
    );
    await _pumpUntil(
      tester,
      condition: () => find.byType(TextField).evaluate().isNotEmpty,
    );

    await tester.tap(find.byType(TextField).last);
    await tester.pump();
    await tester.enterText(
      find.byType(TextField).last,
      '如果把九寨沟方向考虑进去，多给我几个备选方案',
    );
    await _pumpUntil(
      tester,
      condition: () =>
          find.byIcon(Icons.arrow_upward_rounded).evaluate().isNotEmpty,
    );
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    await gateway.waitUntilSubscribed();

    gateway.emit(
      AssistantRunStreamEvent.journey(
        _journeySnapshot(
          activeStage: JourneyStageId.analyze,
          analyzeHeadline: '先把九寨沟方向的候选路线和适用条件分开核对。',
        ),
      ),
    );
    await tester.pump();

    gateway.emit(
      AssistantRunStreamEvent.journey(
        _journeySnapshot(
          activeStage: JourneyStageId.search,
          analyzeHeadline: '先把九寨沟方向的候选路线和适用条件分开核对。',
          searchHeadline: '我在核对九寨沟方向的最新约束',
        ),
      ),
    );
    await tester.pump();

    gateway.emit(AssistantRunStreamEvent.answerDelta('```md'));
    await tester.pump();
    expect(
      _assistantAnswerMarkdownFromBubble(_latestAssistantBubble(tester)),
      isEmpty,
      reason: '未闭合 markdown 包装不应先把 md/fence 残片写进气泡',
    );

    gateway.emit(AssistantRunStreamEvent.answerDelta('\n九寨沟方向'));
    await tester.pump();
    expect(
      _assistantAnswerMarkdownFromBubble(_latestAssistantBubble(tester)),
      '九寨沟方向',
    );
    expect(
      find.textContaining('九寨沟方向', findRichText: true),
      findsAtLeastNWidgets(1),
      reason: '收到可见 answer chunk 后，正文应立即开始流式显示给用户',
    );

    gateway.emit(AssistantRunStreamEvent.answerDelta('九寨沟方向'));
    await tester.pump();
    expect(
      _assistantAnswerMarkdownFromBubble(_latestAssistantBubble(tester)),
      '九寨沟方向',
      reason: '重复到达的 answer chunk 不应再次把同一段正文追加一遍',
    );

    gateway.emit(
      AssistantRunStreamEvent.journey(
        _journeySnapshot(
          activeStage: JourneyStageId.answer,
          analyzeHeadline: '先把九寨沟方向的候选路线和适用条件分开核对。',
          searchHeadline: '我在核对九寨沟方向的最新约束',
          answerHeadline: '我开始整理成最终方案。',
        ),
      ),
    );
    await tester.pump();
    expect(
      _assistantAnswerMarkdownFromBubble(_latestAssistantBubble(tester)),
      '九寨沟方向',
      reason: 'process journal 中的 answerDelta 不应再次把正文追加一遍',
    );
    expect(
      find.textContaining('九寨沟方向', findRichText: true),
      findsAtLeastNWidgets(1),
      reason: '进入 answering 阶段后，缓冲的答案正文应开始对用户可见',
    );
    expect(
      find.text(UITextConstants.assistantPhaseAnswering),
      findsNothing,
      reason: '仅有 journey 信号时，不应再用旧主轨阶段标签驱动用户界面',
    );

    final streamingMessageId =
        _latestAssistantBubble(tester).message['id'] as String? ?? '';

    gateway.emit(AssistantRunStreamEvent.answerDelta('备选方案'));
    await tester.pump();
    expect(
      _assistantAnswerMarkdownFromBubble(_latestAssistantBubble(tester)),
      '九寨沟方向备选方案',
    );

    gateway.emit(AssistantRunStreamEvent.answerDelta('方向备选方案'));
    await tester.pump();
    expect(
      _assistantAnswerMarkdownFromBubble(_latestAssistantBubble(tester)),
      '九寨沟方向备选方案',
      reason: '重叠 chunk 不应把相同尾段重复拼接到正文里',
    );

    gateway.emit(
      AssistantRunStreamEvent.answerDelta(
        '\n```card:compare\n{"title":"路线对比"}',
      ),
    );
    await tester.pump();
    expect(
      _assistantAnswerMarkdownFromBubble(_latestAssistantBubble(tester)),
      '九寨沟方向备选方案',
      reason: '未闭合 card fence 不应提前把 payload 写进答案显示块',
    );

    gateway.emit(AssistantRunStreamEvent.answerDelta('<function=web_'));
    await tester.pump();
    expect(
      _assistantAnswerMarkdownFromBubble(_latestAssistantBubble(tester)),
      '九寨沟方向备选方案',
      reason: '拆包的 function 开头不应污染答案显示块',
    );

    gateway.emit(
      AssistantRunStreamEvent.answerDelta(
        'search><parameter=query>九寨沟若尔盖黄龙串联路线 方案',
      ),
    );
    await tester.pump();
    expect(
      _assistantAnswerMarkdownFromBubble(_latestAssistantBubble(tester)),
      '九寨沟方向备选方案',
      reason: 'function 参数正文不应在流式阶段落入用户答案',
    );

    gateway.emit(
      AssistantRunStreamEvent.answerDelta(
        '</parameter><parameter=queryTasks>[{"id":"plan_options"}]',
      ),
    );
    await tester.pump();
    expect(
      _assistantAnswerMarkdownFromBubble(_latestAssistantBubble(tester)),
      '九寨沟方向备选方案',
      reason: 'queryTasks 这类内部协议字段不应通过拆包追加进正文',
    );

    gateway.emit(
      AssistantRunStreamEvent.answerDelta('</parameter></function>'),
    );
    await tester.pump();
    expect(
      _assistantAnswerMarkdownFromBubble(_latestAssistantBubble(tester)),
      '九寨沟方向备选方案',
      reason: 'function 关闭标签不应残留到答案显示块',
    );

    gateway.emit(
      AssistantRunStreamEvent.completed(
        AssistantRunResponse(
          finalText: '九寨沟方向备选方案\n1. 九寨沟 + 黄龙\n2. 川主寺中转',
          traces: const [],
          structuredResponse: <String, dynamic>{
            'runArtifacts': const <String, dynamic>{
              'displayMarkdown':
                  '## 九寨沟方向备选方案\n\n1. **九寨沟 + 黄龙**\n   适合：第一次走经典主线。\n2. **川主寺中转**\n   适合：更看重交通节奏。',
              'displayPlainText':
                  '九寨沟方向备选方案\n1. 九寨沟 + 黄龙 适合：第一次走经典主线。\n2. 川主寺中转 适合：更看重交通节奏。',
              'journey': <String, dynamic>{
                'stages': <Map<String, dynamic>>[
                  <String, dynamic>{
                    'stageId': 'analyze',
                    'status': 'completed',
                    'order': 0,
                    'summary': '先把九寨沟方向的候选路线和适用条件分开核对。',
                  },
                  <String, dynamic>{
                    'stageId': 'search',
                    'status': 'completed',
                    'order': 1,
                    'summary': '我在核对九寨沟方向的最新约束',
                    'referenceCount': 1,
                  },
                  <String, dynamic>{
                    'stageId': 'answer',
                    'status': 'completed',
                    'order': 3,
                    'summary': '我开始整理成最终方案。',
                  },
                ],
                'entries': <Map<String, dynamic>>[
                  <String, dynamic>{
                    'entryId': 'journey.analyze.plan',
                    'stageId': 'analyze',
                    'kind': 'narrative',
                    'status': 'completed',
                    'order': 0,
                    'headline': '先把九寨沟方向的候选路线和适用条件分开核对。',
                  },
                  <String, dynamic>{
                    'entryId': 'journey.search.verify',
                    'stageId': 'search',
                    'kind': 'reference_bundle',
                    'status': 'completed',
                    'order': 1,
                    'headline': '我在核对九寨沟方向的最新约束',
                    'references': <Map<String, dynamic>>[
                      <String, dynamic>{
                        'title': '九寨沟景区公告',
                        'url': 'https://example.com/jiuzhaigou',
                        'source': '官方',
                      },
                    ],
                  },
                  <String, dynamic>{
                    'entryId': 'journey.answer.final',
                    'stageId': 'answer',
                    'kind': 'narrative',
                    'status': 'completed',
                    'order': 2,
                    'headline': '我开始整理成最终方案。',
                  },
                ],
                'summary': '我开始整理成最终方案。',
                'referenceSummary': <String, dynamic>{
                  'count': 1,
                  'references': <Map<String, dynamic>>[
                    <String, dynamic>{
                      'title': '九寨沟景区公告',
                      'url': 'https://example.com/jiuzhaigou',
                      'source': '官方',
                    },
                  ],
                },
                'readiness': <String, dynamic>{
                  'nextAction': 'answer',
                  'finalAnswerMode': 'direct',
                  'answerEligibility': 'ready',
                  'finalAnswerReady': true,
                },
              },
            },
            'qualityMetrics': const <String, dynamic>{
              'heuristicFallbackUsed': false,
            },
            'uiUsageStats': const <String, dynamic>{
              'runModelCallCount': 3,
              'runTotalTokens': 880,
            },
          },
        ),
      ),
    );
    unawaited(gateway.dispose());
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));

    final completedBubble = _latestAssistantBubble(tester);
    final finalAnswer =
        ((completedBubble.message['content'] as String?)?.trim().isNotEmpty ==
                true
            ? completedBubble.message['content']
            : _assistantAnswerMarkdownFromBubble(completedBubble)) ??
        '';
    expect(completedBubble.message['id'], streamingMessageId);
    expect(finalAnswer, contains('九寨沟方向备选方案'));
    final persistedJourney =
        ((completedBubble.message['journey'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{});
    final mergedJourneyEntries =
        ((persistedJourney['entries'] as List?)?.whereType<Map>().toList(
          growable: false,
        )) ??
        const <Map>[];
    expect(
      mergedJourneyEntries
          .where((item) => item['entryId'] == 'journey.search.verify')
          .length,
      1,
      reason: 'completed 合并后不应把同一语义的 journey entry 重复写两遍',
    );
    expect(persistedJourney, isNotEmpty);
    final persistedEntries =
        ((persistedJourney['entries'] as List?)?.whereType<Map>().toList(
          growable: false,
        )) ??
        const <Map>[];
    expect(
      persistedEntries.any((entry) => entry['headline'] == '我在核对九寨沟方向的最新约束'),
      isTrue,
    );
  });

  testWidgets('assistant 答案轨会直接追加到 displayState.answer.blocks', (tester) async {
    final gateway = _ControlledRemoteAssistantEntry();
    addTearDown(gateway.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatRepositoryProvider.overrideWithValue(
            _EmptyAssistantChatRepository(),
          ),
          relationshipCapabilityRepositoryProvider.overrideWithValue(
            _AssistantCapabilityRepository(),
          ),
          assistantRemoteConfiguredProvider.overrideWith((ref) => true),
          remoteAssistantEntryProvider.overrideWithValue(gateway),
        ],
        child: MaterialApp(
          home: Scaffold(body: AssistantConversationPage(onBack: _noop)),
        ),
      ),
    );
    await _pumpUntil(
      tester,
      condition: () => find.byType(TextField).evaluate().isNotEmpty,
    );

    await tester.tap(find.byType(TextField).last);
    await tester.pump();
    await tester.enterText(find.byType(TextField).last, '请帮我整理九寨沟路线');
    await _pumpUntil(
      tester,
      condition: () =>
          find.byIcon(Icons.arrow_upward_rounded).evaluate().isNotEmpty,
    );
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    await gateway.waitUntilSubscribed();

    gateway.emit(
      AssistantRunStreamEvent.answerDelta('## 问题理解\n\n用户在比较九寨沟方向的几个周末路线。'),
    );
    await tester.pump();

    var bubble = _latestAssistantBubble(tester);
    expect(
      _assistantAnswerMarkdownFromBubble(bubble),
      '## 问题理解\n\n用户在比较九寨沟方向的几个周末路线。',
    );
    expect(
      find.textContaining('问题理解', findRichText: true),
      findsAtLeastNWidgets(1),
    );
    expect(find.textContaining('关键观点', findRichText: true), findsNothing);
    final streamingMessageId = bubble.message['id'] as String? ?? '';

    gateway.emit(AssistantRunStreamEvent.answerDelta('\n\n## 关键'));
    await tester.pump();

    bubble = _assistantBubbleByMessageId(tester, streamingMessageId);
    expect(
      _assistantAnswerMarkdownFromBubble(bubble),
      '## 问题理解\n\n用户在比较九寨沟方向的几个周末路线。\n\n## 关键',
      reason: '答案轨不再维护 section reveal 状态，增量会直接进入预览内容',
    );

    gateway.emit(
      AssistantRunStreamEvent.answerDelta('观点\n\n- 经典线更稳妥\n- 黄龙可按天气补充'),
    );
    await tester.pump();

    bubble = _assistantBubbleByMessageId(tester, streamingMessageId);
    final secondStagePreview = _assistantAnswerMarkdownFromBubble(bubble);
    expect(secondStagePreview, contains('## 问题理解'));
    expect(secondStagePreview, contains('## 关键观点'));
    expect(secondStagePreview, isNot(contains('## 回答概要')));
    expect(
      find.textContaining('关键观点', findRichText: true),
      findsAtLeastNWidgets(1),
    );
    expect(find.textContaining('回答概要', findRichText: true), findsNothing);

    gateway.emit(
      AssistantRunStreamEvent.answerDelta(
        '\n\n## 回答概要\n\n建议先走经典线，再按天气决定是否串黄龙。',
      ),
    );
    await tester.pump();

    bubble = _assistantBubbleByMessageId(tester, streamingMessageId);
    expect(_assistantAnswerMarkdownFromBubble(bubble), contains('## 回答概要'));
  });

  testWidgets('无真实 journey 信号时不展示 seeded 假过程抽屉', (tester) async {
    final gateway = _ControlledRemoteAssistantEntry();
    addTearDown(gateway.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatRepositoryProvider.overrideWithValue(
            _EmptyAssistantChatRepository(),
          ),
          relationshipCapabilityRepositoryProvider.overrideWithValue(
            _AssistantCapabilityRepository(),
          ),
          assistantRemoteConfiguredProvider.overrideWith((ref) => true),
          remoteAssistantEntryProvider.overrideWithValue(gateway),
        ],
        child: MaterialApp(
          home: Scaffold(body: AssistantConversationPage(onBack: _noop)),
        ),
      ),
    );
    await _pumpUntil(
      tester,
      condition: () => find.byType(TextField).evaluate().isNotEmpty,
    );

    await tester.tap(find.byType(TextField).last);
    await tester.pump();
    await tester.enterText(find.byType(TextField).last, '帮我看下深圳天气');
    await _pumpUntil(
      tester,
      condition: () =>
          find.byIcon(Icons.arrow_upward_rounded).evaluate().isNotEmpty,
    );
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    await gateway.waitUntilSubscribed();

    expect(find.byType(AssistantProcessDrawer), findsNothing);

    gateway.emit(
      AssistantRunStreamEvent.journey(
        _journeySnapshot(
          activeStage: JourneyStageId.analyze,
          analyzeHeadline: '我先确认这是天气查询。',
        ),
      ),
    );
    await tester.pump();

    expect(
      find.byType(AssistantProcessDrawer),
      findsNothing,
      reason: 'journey-only 信号不应再驱动过程抽屉，必须等待 processTimeline 主轨',
    );
  });

  testWidgets('structured answer stream 在成答前不应闪出内部 JSON 字段', (tester) async {
    final gateway = _ControlledRemoteAssistantEntry();
    addTearDown(gateway.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatRepositoryProvider.overrideWithValue(
            _EmptyAssistantChatRepository(),
          ),
          relationshipCapabilityRepositoryProvider.overrideWithValue(
            _AssistantCapabilityRepository(),
          ),
          assistantRemoteConfiguredProvider.overrideWith((ref) => true),
          remoteAssistantEntryProvider.overrideWithValue(gateway),
        ],
        child: MaterialApp(
          home: Scaffold(body: AssistantConversationPage(onBack: _noop)),
        ),
      ),
    );
    await _pumpUntil(
      tester,
      condition: () => find.byType(TextField).evaluate().isNotEmpty,
    );

    await tester.tap(find.byType(TextField).last);
    await tester.pump();
    await tester.enterText(find.byType(TextField).last, 'Shenzhen tian qi');
    await _pumpUntil(
      tester,
      condition: () =>
          find.byIcon(Icons.arrow_upward_rounded).evaluate().isNotEmpty,
    );
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    await gateway.waitUntilSubscribed();

    gateway.emit(
      AssistantRunStreamEvent.journey(
        _journeySnapshot(
          activeStage: JourneyStageId.answer,
          analyzeHeadline: '我先确认这是天气查询，不是行程规划。',
          answerHeadline: '我开始整理成最终答案。',
        ),
      ),
    );
    await tester.pump();

    gateway.emit(
      AssistantRunStreamEvent.answerDelta(
        '{"contractId":"assistant_turn","decision":{"nextAction":"answer"},"messageKind":"answer","userMar',
      ),
    );
    await tester.pump();

    expect(
      _assistantAnswerMarkdownFromBubble(_latestAssistantBubble(tester)),
      isEmpty,
      reason: '结构化 envelope 尚未进入 userMarkdown 前，不应把 JSON 前缀写进气泡',
    );
    expect(find.textContaining('contractId'), findsNothing);
    expect(find.textContaining('assistant_turn'), findsNothing);

    gateway.emit(AssistantRunStreamEvent.answerDelta('kdown":"深圳今天天气晴'));
    await tester.pump();
    expect(
      _assistantAnswerMarkdownFromBubble(_latestAssistantBubble(tester)),
      '深圳今天天气晴',
    );
    expect(find.text('深圳今天天气晴'), findsAtLeastNWidgets(1));
    expect(find.textContaining('contractId'), findsNothing);

    gateway.emit(
      AssistantRunStreamEvent.answerDelta(
        '，适合出行。","result":{"text":"深圳今天天气晴，适合出行。"}}',
      ),
    );
    await tester.pump();
    expect(
      _assistantAnswerMarkdownFromBubble(_latestAssistantBubble(tester)),
      '深圳今天天气晴，适合出行。',
    );
    expect(find.textContaining('assistant_turn'), findsNothing);

    gateway.emit(
      AssistantRunStreamEvent.completed(
        const AssistantRunResponse(
          finalText: '深圳今天天气晴，适合出行。',
          traces: <AssistantTraceEvent>[],
          structuredResponse: <String, dynamic>{
            'runArtifacts': <String, dynamic>{
              'displayMarkdown': '深圳今天天气晴，适合出行。',
              'displayPlainText': '深圳今天天气晴，适合出行。',
            },
          },
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));

    final finalBubble = _latestAssistantBubble(tester);
    final finalAnswer =
        ((finalBubble.message['content'] as String?)?.trim().isNotEmpty == true
            ? finalBubble.message['content']
            : _assistantAnswerMarkdownFromBubble(finalBubble)) ??
        '';
    expect(finalAnswer, contains('深圳今天天气晴，适合出行。'));
    expect(find.textContaining('contractId'), findsNothing);
    expect(find.textContaining('machineEnvelope'), findsNothing);
  });

  testWidgets('assistant 引用角标点击后打开应用内网页页', (tester) async {
    final message = <String, dynamic>{
      'id': 'assistant_reference_seed',
      'conversationId': AppConceptConstants.assistantConversationId,
      'type': 'text',
      'content': 'Flutter 官方仓库可作为参考来源。',
      'senderId': AppConceptConstants.assistantSenderId,
      'senderName': AppConceptConstants.assistantLabel,
      'senderAvatar': '',
      'timestamp': '10:10',
      'isRead': true,
      'isSelf': false,
      'displayMarkdown':
          'Flutter 官方仓库可作为参考来源。[来源1](https://github.com/flutter/flutter)',
      'displayPlainText': 'Flutter 官方仓库可作为参考来源。',
      'runArtifacts': <String, dynamic>{
        'displayMarkdown':
            'Flutter 官方仓库可作为参考来源。[来源1](https://github.com/flutter/flutter)',
        'displayPlainText': 'Flutter 官方仓库可作为参考来源。',
        'answerEvidenceBindings': <Map<String, dynamic>>[
          <String, dynamic>{
            'bindingId': 'binding_1',
            'label': '来源1',
            'claim': 'Flutter 官方仓库可作为参考来源。',
            'evidenceId': 'evidence_1',
            'url': 'https://github.com/flutter/flutter',
            'title': 'Flutter GitHub 仓库',
            'source': 'github.com',
            'snippet': 'Flutter SDK 与框架源码仓库',
          },
        ],
      },
    };

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) {
              return AssistantMessageBubble(
                message: message,
                isRight: false,
                bubbleColor: Colors.grey.shade200,
                textColor: Colors.black,
                isSelectionMode: false,
                isSelected: false,
                onLongPressStart: (_) {},
                hideAvatarAndName: true,
                useFullWidth: true,
                renderSelfTextWithoutBubble: true,
                answerGateOpen: true,
                onReferenceTap: (reference) {
                  Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => AssistantReferenceWebViewPage(
                        initialUrl: (reference['url'] as String?) ?? '',
                        title: (reference['title'] as String?) ?? '',
                        source: (reference['source'] as String?) ?? '',
                      ),
                    ),
                  );
                },
              );
            },
          ),
        ),
      ),
    );
    await _pumpUntil(
      tester,
      condition: () => find
          .byKey(const ValueKey<String>('assistant_reference_chip_1'))
          .evaluate()
          .isNotEmpty,
    );

    final runArtifacts =
        (message['runArtifacts'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    expect(
      (runArtifacts['displayMarkdown'] as String?) ?? '',
      contains('[来源1](https://github.com/flutter/flutter)'),
    );
    final bindings =
        (runArtifacts['answerEvidenceBindings'] as List?)
            ?.whereType<Map>()
            .toList(growable: false) ??
        const <Map>[];
    expect(bindings, hasLength(1));

    expect(
      find.byKey(const ValueKey<String>('assistant_reference_chip_1')),
      findsOneWidget,
    );

    await tester.tap(
      find.byKey(const ValueKey<String>('assistant_reference_chip_1')),
    );
    await tester.pumpAndSettle();

    expect(find.text('https://github.com/flutter/flutter'), findsOneWidget);
    expect(find.text('Flutter GitHub 仓库'), findsOneWidget);
  });
}

void _noop() {}

JourneyStageStatus _statusForStage(
  JourneyStageId stageId,
  JourneyStageId activeStage,
) {
  const order = <JourneyStageId, int>{
    JourneyStageId.analyze: 0,
    JourneyStageId.search: 1,
    JourneyStageId.verify: 2,
    JourneyStageId.answer: 3,
  };
  final stageOrder = order[stageId] ?? 0;
  final activeOrder = order[activeStage] ?? 0;
  if (stageId == activeStage) return JourneyStageStatus.active;
  if (stageOrder < activeOrder) return JourneyStageStatus.completed;
  return JourneyStageStatus.pending;
}

AssistantJourney _journeySnapshot({
  required JourneyStageId activeStage,
  String analyzeHeadline = '',
  String searchHeadline = '',
  String answerHeadline = '',
}) {
  final analyzeStatus = _statusForStage(JourneyStageId.analyze, activeStage);
  final searchStatus = _statusForStage(JourneyStageId.search, activeStage);
  final answerStatus = _statusForStage(JourneyStageId.answer, activeStage);
  final entries = <AssistantJourneyEntry>[
    if (analyzeHeadline.isNotEmpty)
      AssistantJourneyEntry(
        entryId: 'journey.analyze.plan',
        stageId: JourneyStageId.analyze,
        kind: JourneyEntryKind.narrative,
        status: analyzeStatus,
        order: 0,
        headline: analyzeHeadline,
      ),
    if (searchHeadline.isNotEmpty)
      AssistantJourneyEntry(
        entryId: 'journey.search.verify',
        stageId: JourneyStageId.search,
        kind: JourneyEntryKind.referenceBundle,
        status: searchStatus,
        order: 1,
        headline: searchHeadline,
        references: const <AssistantJourneyReference>[
          AssistantJourneyReference(
            title: '九寨沟景区公告',
            url: 'https://example.com/jiuzhaigou',
            source: '官方',
          ),
        ],
      ),
    if (answerHeadline.isNotEmpty)
      AssistantJourneyEntry(
        entryId: 'journey.answer.final',
        stageId: JourneyStageId.answer,
        kind: JourneyEntryKind.narrative,
        status: answerStatus,
        order: 2,
        headline: answerHeadline,
      ),
  ];
  return AssistantJourney(
    stages: <AssistantJourneyStage>[
      AssistantJourneyStage(
        stageId: JourneyStageId.analyze,
        status: analyzeStatus,
        order: 0,
        summary: analyzeHeadline,
      ),
      AssistantJourneyStage(
        stageId: JourneyStageId.search,
        status: searchStatus,
        order: 1,
        summary: searchHeadline,
        referenceCount: searchHeadline.isNotEmpty ? 1 : 0,
      ),
      AssistantJourneyStage(
        stageId: JourneyStageId.verify,
        status: _statusForStage(JourneyStageId.verify, activeStage),
        order: 2,
      ),
      AssistantJourneyStage(
        stageId: JourneyStageId.answer,
        status: answerStatus,
        order: 3,
        summary: answerHeadline,
      ),
    ],
    entries: entries,
    summary: answerHeadline.isNotEmpty ? answerHeadline : searchHeadline,
    referenceSummary: searchHeadline.isNotEmpty
        ? const AssistantJourneyReferenceSummary(
            count: 1,
            references: <AssistantJourneyReference>[
              AssistantJourneyReference(
                title: '九寨沟景区公告',
                url: 'https://example.com/jiuzhaigou',
                source: '官方',
              ),
            ],
          )
        : const AssistantJourneyReferenceSummary(),
    readiness: AssistantJourneyReadiness(
      nextAction: activeStage == JourneyStageId.answer
          ? AssistantNextAction.answer
          : AssistantNextAction.toolCall,
      finalAnswerMode: activeStage == JourneyStageId.answer
          ? FinalAnswerMode.full
          : FinalAnswerMode.blocked,
      answerEligibility: activeStage == JourneyStageId.answer
          ? AnswerEligibility.eligible
          : AnswerEligibility.unknown,
      finalAnswerReady: activeStage == JourneyStageId.answer,
    ),
  );
}

class _ControlledRemoteAssistantEntry extends RemoteAssistantEntry {
  _ControlledRemoteAssistantEntry()
    : _subscribed = Completer<void>(),
      super(
        openClawBridge: OpenClawBridge(baseUrl: ''),
        requestPolicy: const AssistantRequestPolicy(),
      ) {
    _controller = StreamController<AssistantRunStreamEvent>(
      onListen: () {
        if (!_subscribed.isCompleted) {
          _subscribed.complete();
        }
      },
    );
  }

  late final StreamController<AssistantRunStreamEvent> _controller;
  final Completer<void> _subscribed;

  void emit(AssistantRunStreamEvent event) => _controller.add(event);

  Future<void> waitUntilSubscribed({
    Duration timeout = const Duration(seconds: 10),
  }) => _subscribed.future.timeout(timeout);

  @override
  Stream<AssistantRunStreamEvent> runStream({
    required AssistantRunRequest request,
  }) => _controller.stream;

  Future<void> dispose() async {
    if (_controller.isClosed) {
      return;
    }
    unawaited(_controller.close());
  }
}

class _ControlledLocalAssistantEntry extends LocalAssistantEntry {
  _ControlledLocalAssistantEntry()
    : _subscribed = Completer<void>(),
      super(
        assistantGateway: _ImmediateAssistantGateway(
          const AssistantRunResponse(
            finalText: '',
            traces: <AssistantTraceEvent>[],
          ),
        ),
        requestPolicy: const AssistantRequestPolicy(),
      ) {
    _controller = StreamController<AssistantRunStreamEvent>(
      onListen: () {
        if (!_subscribed.isCompleted) {
          _subscribed.complete();
        }
      },
    );
  }

  late final StreamController<AssistantRunStreamEvent> _controller;
  final Completer<void> _subscribed;

  void emit(AssistantRunStreamEvent event) => _controller.add(event);

  Future<void> waitUntilSubscribed({
    Duration timeout = const Duration(seconds: 10),
  }) => _subscribed.future.timeout(timeout);

  @override
  Stream<AssistantRunStreamEvent> runStream({
    required AssistantRunRequest request,
  }) => _controller.stream;

  Future<void> dispose() async {
    if (_controller.isClosed) {
      return;
    }
    unawaited(_controller.close());
  }
}

class _ImmediateAssistantGateway extends AssistantGateway {
  _ImmediateAssistantGateway(this._response)
    : super(AssistantRuntime.createForTest());

  final AssistantRunResponse _response;

  @override
  Future<AssistantRunResponse> run(AssistantRunRequest request) async {
    return _response;
  }

  @override
  Future<AssistantRunResponse> runWithTraceStream(
    AssistantRunRequest request, {
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    return _response;
  }

  @override
  Future<void> ensureRemoteConfigLoaded() async {}

  @override
  Future<List<Map<String, dynamic>>> listSessions() async {
    return const <Map<String, dynamic>>[];
  }

  @override
  Future<Map<String, dynamic>?> sessionDetail(String sessionId) async {
    return null;
  }
}

class _EmptyAssistantChatRepository extends MockChatRepository {
  @override
  Future<List<Map<String, dynamic>>> listMessages({
    required String conversationId,
    String? before,
    int limit = 20,
  }) async {
    return const <Map<String, dynamic>>[];
  }
}

class _AssistantCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) async {
    return RelationshipCapabilityDto.fromMap(<String, dynamic>{
      'canCallVoice': true,
      'canCallVideo': true,
      'canAddAsFriend': false,
      'relationshipType': 'friend',
    });
  }
}

AssistantMessageBubble _latestAssistantBubble(WidgetTester tester) {
  final finder = find.byWidgetPredicate(
    (widget) =>
        widget is AssistantMessageBubble &&
        (widget.message['senderId'] as String?) ==
            AppConceptConstants.assistantSenderId,
    description: 'assistant bubble',
  );
  return tester.widget<AssistantMessageBubble>(finder.last);
}

AssistantMessageBubble _assistantBubbleByMessageId(
  WidgetTester tester,
  String messageId,
) {
  final finder = find.byWidgetPredicate(
    (widget) =>
        widget is AssistantMessageBubble &&
        (widget.message['id'] as String?) == messageId,
    description: 'assistant bubble $messageId',
  );
  return tester.widget<AssistantMessageBubble>(finder.last);
}

String _assistantAnswerMarkdownFromBubble(AssistantMessageBubble bubble) {
  final displayState = resolvePersistedAssistantDisplayState(bubble.message);
  return renderAnswerBlocksToMarkdown(displayState.answer.blocks);
}

Future<void> _pumpUntil(
  WidgetTester tester, {
  required bool Function() condition,
  Duration timeout = const Duration(seconds: 10),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 100));
    if (condition()) return;
  }
  throw TestFailure('等待条件超时: $timeout');
}

class _FakeWebViewPlatform extends WebViewPlatform {
  @override
  PlatformNavigationDelegate createPlatformNavigationDelegate(
    PlatformNavigationDelegateCreationParams params,
  ) {
    return _FakePlatformNavigationDelegate(params);
  }

  @override
  PlatformWebViewController createPlatformWebViewController(
    PlatformWebViewControllerCreationParams params,
  ) {
    return _FakePlatformWebViewController(params);
  }

  @override
  PlatformWebViewWidget createPlatformWebViewWidget(
    PlatformWebViewWidgetCreationParams params,
  ) {
    return _FakePlatformWebViewWidget(params);
  }
}

class _FakePlatformNavigationDelegate extends PlatformNavigationDelegate {
  _FakePlatformNavigationDelegate(super.params) : super.implementation();

  PageEventCallback? onPageStarted;
  PageEventCallback? onPageFinished;
  WebResourceErrorCallback? onWebResourceError;
  NavigationRequestCallback? onNavigationRequest;

  @override
  Future<void> setOnPageStarted(PageEventCallback callback) async {
    onPageStarted = callback;
  }

  @override
  Future<void> setOnPageFinished(PageEventCallback callback) async {
    onPageFinished = callback;
  }

  @override
  Future<void> setOnWebResourceError(WebResourceErrorCallback callback) async {
    onWebResourceError = callback;
  }

  @override
  Future<void> setOnNavigationRequest(
    NavigationRequestCallback callback,
  ) async {
    onNavigationRequest = callback;
  }

  @override
  Future<void> setOnHttpError(HttpResponseErrorCallback onHttpError) async {}

  @override
  Future<void> setOnProgress(ProgressCallback onProgress) async {}

  @override
  Future<void> setOnUrlChange(UrlChangeCallback onUrlChange) async {}

  @override
  Future<void> setOnHttpAuthRequest(
    HttpAuthRequestCallback onHttpAuthRequest,
  ) async {}

  @override
  Future<void> setOnSSlAuthError(SslAuthErrorCallback onSslAuthError) async {}
}

class _FakePlatformWebViewController extends PlatformWebViewController {
  _FakePlatformWebViewController(super.params) : super.implementation();

  _FakePlatformNavigationDelegate? _delegate;
  Uri? _currentUri;

  @override
  Future<void> setJavaScriptMode(JavaScriptMode javaScriptMode) async {}

  @override
  Future<void> setBackgroundColor(Color color) async {}

  @override
  Future<void> setPlatformNavigationDelegate(
    PlatformNavigationDelegate handler,
  ) async {
    _delegate = handler is _FakePlatformNavigationDelegate ? handler : null;
  }

  @override
  Future<void> loadRequest(LoadRequestParams params) async {
    _currentUri = params.uri;
    final url = params.uri.toString();
    _delegate?.onPageStarted?.call(url);
    _delegate?.onPageFinished?.call(url);
  }

  @override
  Future<void> reload() async {
    final uri = _currentUri;
    if (uri == null) return;
    final url = uri.toString();
    _delegate?.onPageStarted?.call(url);
    _delegate?.onPageFinished?.call(url);
  }

  @override
  Future<String?> currentUrl() async => _currentUri?.toString();
}

class _FakePlatformWebViewWidget extends PlatformWebViewWidget {
  _FakePlatformWebViewWidget(super.params) : super.implementation();

  @override
  Widget build(BuildContext context) {
    return const ColoredBox(color: Colors.white);
  }
}
