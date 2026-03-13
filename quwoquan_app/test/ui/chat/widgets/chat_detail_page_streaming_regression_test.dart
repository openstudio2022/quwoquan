import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_engine_provider.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_gateway.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_runtime.dart';
import 'package:quwoquan_app/personal_assistant/app/capability_gateway.dart';
import 'package:quwoquan_app/personal_assistant/connectors/openclaw_bridge.dart';
import 'package:quwoquan_app/personal_assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_response.dart';
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

    gateway.emit(AssistantRunStreamEvent.answerDelta('九寨沟方向'));
    await tester.pump();
    expect(
      _latestAssistantBubble(tester).message['streamFinalAnswer'],
      '九寨沟方向',
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

    final streamingMessageId =
        _latestAssistantBubble(tester).message['id'] as String? ?? '';

    gateway.emit(AssistantRunStreamEvent.answerDelta('备选方案'));
    await tester.pump();
    expect(
      _latestAssistantBubble(tester).message['streamFinalAnswer'],
      '九寨沟方向备选方案',
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
            'qualityMetrics': const <String, dynamic>{
              'heuristicFallbackUsed': false,
            },
            'processJournalV1': const <Map<String, dynamic>>[
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
            'uiUsageStatsV1': const <String, dynamic>{
              'runModelCallCount': 3,
              'runTotalTokens': 880,
            },
          },
        ),
      ),
    );
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
        (completedBubble.message['processJournalV1'] as List?)
            ?.whereType<Map>()
            .toList(growable: false) ??
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

  Future<void> waitUntilSubscribed() => _subscribed.future;

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
    await _controller.close();
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
