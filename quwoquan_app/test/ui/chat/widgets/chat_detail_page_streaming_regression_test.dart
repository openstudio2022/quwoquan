import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/application/assistant_gateway.dart';
import 'package:quwoquan_app/assistant/application/assistant_providers.dart';
import 'package:quwoquan_app/assistant/application/capability_gateway.dart';
import 'package:quwoquan_app/assistant/domain/channel/channel.dart';
import 'package:quwoquan_app/assistant/domain/conversation/conversation.dart';
import 'package:quwoquan_app/assistant/infrastructure/infrastructure.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_detail_page.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/chat_message_bubble.dart';

void main() {
  testWidgets('assistant answerDelta 会逐步追加，completed 不重建 message id', (
    tester,
  ) async {
    final gateway = _ControlledCapabilityGateway();
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
          capabilityGatewayProvider.overrideWithValue(gateway),
        ],
        child: MaterialApp(
          home: Scaffold(
            body: ChatDetailPage(
              conversationId: AppConceptConstants.assistantConversationId,
              onBack: _noop,
            ),
          ),
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
      AssistantRunStreamEvent.processJournal(
        const ProcessJournalEvent(
          eventId: 'stream.plan.1',
          type: ProcessJournalEventType.narrativeCommit,
          stage: 'understanding',
          phaseId: 'understanding',
          actionCode: 'frame_problem',
          reasonCode: 'align_goal',
          reasonShort: '先把九寨沟方向的候选路线和适用条件分开核对。',
          nodeId: 'root.intent.plan',
        ),
      ),
    );
    await tester.pump();

    gateway.emit(
      AssistantRunStreamEvent.explainableFlow(
        const ExplainableFlowEvent(
          phaseId: PhaseId.execute,
          phaseOrder: 1,
          phaseStatus: ExplainablePhaseStatus.active,
          headline: '我在核对九寨沟方向的最新约束',
          references: <FlowReference>[
            FlowReference(
              title: '九寨沟景区公告',
              url: 'https://example.com/jiuzhaigou',
              source: '官方',
            ),
          ],
        ),
      ),
    );
    await tester.pump();

    gateway.emit(AssistantRunStreamEvent.answerDelta('```md'));
    await tester.pump();
    expect(
      _latestAssistantBubble(tester).message['streamFinalAnswer'],
      isEmpty,
      reason: '未闭合 markdown 包装不应先把 md/fence 残片写进气泡',
    );

    gateway.emit(AssistantRunStreamEvent.answerDelta('\n九寨沟方向'));
    await tester.pump();
    expect(
      _latestAssistantBubble(tester).message['streamFinalAnswer'],
      '九寨沟方向',
    );
    expect(
      find.text('九寨沟方向'),
      findsNothing,
      reason: '进入 answering 阶段前，不应先把最终答案正文暴露到界面',
    );

    gateway.emit(AssistantRunStreamEvent.answerDelta('九寨沟方向'));
    await tester.pump();
    expect(
      _latestAssistantBubble(tester).message['streamFinalAnswer'],
      '九寨沟方向',
      reason: '重复到达的 answer chunk 不应再次把同一段正文追加一遍',
    );

    gateway.emit(
      AssistantRunStreamEvent.processJournal(
        const ProcessJournalEvent(
          eventId: 'stream.answer.1',
          type: ProcessJournalEventType.answerDelta,
          stage: 'answering',
          phaseId: 'answering',
          actionCode: 'stream_answer',
          reasonCode: 'deliver_increment',
          nodeId: 'answer.stream',
          message: '九寨沟方向',
        ),
      ),
    );
    await tester.pump();
    expect(
      _latestAssistantBubble(tester).message['streamFinalAnswer'],
      '九寨沟方向',
      reason: 'process journal 中的 answerDelta 不应再次把正文追加一遍',
    );
    expect(
      find.text('九寨沟方向'),
      findsAtLeastNWidgets(1),
      reason: '进入 answering 阶段后，缓冲的答案正文应开始对用户可见',
    );
    expect(
      find.text(UITextConstants.assistantPhaseAnswering),
      findsAtLeastNWidgets(1),
      reason: '开始展示答案后，界面仍应保留用户可理解的阶段提示',
    );

    final streamingMessageId =
        _latestAssistantBubble(tester).message['id'] as String? ?? '';

    gateway.emit(AssistantRunStreamEvent.answerDelta('备选方案'));
    await tester.pump();
    expect(
      _latestAssistantBubble(tester).message['streamFinalAnswer'],
      '九寨沟方向备选方案',
    );

    gateway.emit(AssistantRunStreamEvent.answerDelta('方向备选方案'));
    await tester.pump();
    expect(
      _latestAssistantBubble(tester).message['streamFinalAnswer'],
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
      _latestAssistantBubble(tester).message['streamFinalAnswer'],
      '九寨沟方向备选方案\n',
      reason: '未闭合 card fence 不应提前把 payload 写进 streamFinalAnswer',
    );

    gateway.emit(AssistantRunStreamEvent.answerDelta('<function=web_'));
    await tester.pump();
    expect(
      _latestAssistantBubble(tester).message['streamFinalAnswer'],
      '九寨沟方向备选方案\n',
      reason: '拆包的 function 开头不应污染 streamFinalAnswer',
    );

    gateway.emit(
      AssistantRunStreamEvent.answerDelta(
        'search><parameter=query>九寨沟若尔盖黄龙串联路线 方案',
      ),
    );
    await tester.pump();
    expect(
      _latestAssistantBubble(tester).message['streamFinalAnswer'],
      '九寨沟方向备选方案\n',
      reason: 'function 参数正文不应在流式阶段落入用户答案',
    );

    gateway.emit(
      AssistantRunStreamEvent.answerDelta(
        '</parameter><parameter=queryTasks>[{"id":"plan_options"}]',
      ),
    );
    await tester.pump();
    expect(
      _latestAssistantBubble(tester).message['streamFinalAnswer'],
      '九寨沟方向备选方案\n',
      reason: 'queryTasks 这类内部协议字段不应通过拆包追加进正文',
    );

    gateway.emit(
      AssistantRunStreamEvent.answerDelta('</parameter></function>'),
    );
    await tester.pump();
    expect(
      _latestAssistantBubble(tester).message['streamFinalAnswer'],
      '九寨沟方向备选方案\n',
      reason: 'function 关闭标签不应残留到 streamFinalAnswer',
    );

    gateway.emit(
      AssistantRunStreamEvent.completed(
        AssistantRunResponse(
          finalText: '九寨沟方向备选方案\n1. 九寨沟 + 黄龙\n2. 川主寺中转',
          traces: const [],
          structuredResponse: <String, dynamic>{
            'uiAnswer': const <String, dynamic>{
              'markdownText':
                  '## 九寨沟方向备选方案\n\n1. **九寨沟 + 黄龙**\n   适合：第一次走经典主线。\n2. **川主寺中转**\n   适合：更看重交通节奏。',
            },
            'runArtifacts': const <String, dynamic>{
              'processJournal': <Map<String, dynamic>>[
                <String, dynamic>{
                  'eventId': 'structured.plan.1',
                  'type': 'narrative_commit',
                  'stage': 'understanding',
                  'phaseId': 'understanding',
                  'actionCode': 'frame_problem',
                  'reasonCode': 'align_goal',
                  'reasonShort': '先把九寨沟方向的候选路线和适用条件分开核对。',
                  'nodeId': 'root.intent.plan',
                },
              ],
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
            : completedBubble.message['streamFinalAnswer']) ??
        '';
    expect(completedBubble.message['id'], streamingMessageId);
    expect(finalAnswer, contains('九寨沟方向备选方案'));
    final mergedJournal =
        (((completedBubble.message['runArtifacts'] as Map?)?['processJournal']
                as List?)
            ?.whereType<Map>()
            .toList(growable: false)) ??
        const <Map>[];
    expect(
      mergedJournal
          .where(
            (item) =>
                item['nodeId'] == 'root.intent.plan' &&
                item['reasonCode'] == 'align_goal',
          )
          .length,
      1,
      reason: 'completed 合并后不应把同一语义的过程事件重复写两遍',
    );
    final flowEvents =
        ((completedBubble.message['uiExplainableFlow'] as List?)
            ?.whereType<Map>()
            .toList(growable: false)) ??
        const <Map>[];
    expect(flowEvents, isNotEmpty);
    expect(flowEvents.first['headline'], '我在核对九寨沟方向的最新约束');
  });
}

void _noop() {}

class _ControlledCapabilityGateway extends CapabilityGateway {
  _ControlledCapabilityGateway()
    : _controller = StreamController<AssistantRunStreamEvent>(),
      _subscribed = Completer<void>(),
      super(
        assistantGateway: AssistantGateway(AssistantRuntime.createDefault()),
        openClawBridge: OpenClawBridge(baseUrl: ''),
      );

  final StreamController<AssistantRunStreamEvent> _controller;
  final Completer<void> _subscribed;

  void emit(AssistantRunStreamEvent event) => _controller.add(event);

  Future<void> waitUntilSubscribed({
    Duration timeout = const Duration(seconds: 10),
  }) => _subscribed.future.timeout(timeout);

  @override
  Stream<AssistantRunStreamEvent> runStream({
    required AssistantRunRequest request,
    CapabilityRouteMode mode = CapabilityRouteMode.hybrid,
  }) {
    if (!_subscribed.isCompleted) {
      _subscribed.complete();
    }
    return _controller.stream;
  }

  Future<void> dispose() async {
    if (_controller.isClosed) {
      return;
    }
    unawaited(_controller.close());
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

ChatMessageBubble _latestAssistantBubble(WidgetTester tester) {
  final finder = find.byWidgetPredicate(
    (widget) =>
        widget is ChatMessageBubble &&
        (widget.message['senderId'] as String?) ==
            AppConceptConstants.assistantSenderId,
    description: 'assistant bubble',
  );
  return tester.widget<ChatMessageBubble>(finder.last);
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
