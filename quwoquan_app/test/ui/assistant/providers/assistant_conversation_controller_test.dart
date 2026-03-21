import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/application/assistant_backend.dart';
import 'package:quwoquan_app/assistant/application/assistant_gateway.dart';
import 'package:quwoquan_app/assistant/application/assistant_providers.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/ui/assistant/providers/assistant_conversation_controller.dart';

void main() {
  group('AssistantConversationController', () {
    testWidgets('initialize 会按分页窗口拆分本地历史并支持继续上拉加载', (
      tester,
    ) async {
      final sessionId = 'local_assistant_test_history';
      final gateway = _FakeAssistantGateway(
        sessions: <Map<String, dynamic>>[
          <String, dynamic>{
            'sessionId': sessionId,
            'topicTitle': '川西路线',
            'isActive': true,
          },
        ],
        sessionDetails: <String, Map<String, dynamic>>{
          sessionId: <String, dynamic>{
            'topicTitle': '川西路线',
            'messages': _buildHistoryMessages(20),
          },
        },
      );

      final controller = await _mountController(
        tester,
        overrides: [
          assistantRemoteConfiguredProvider.overrideWith((ref) => false),
          assistantGatewayProvider.overrideWithValue(gateway),
        ],
      );

      await controller.initialize();
      await tester.pump();

      expect(controller.assistantBackend, AssistantBackend.local);
      expect(controller.assistantTopicTitle, '川西路线');
      expect(controller.messages, hasLength(18));
      expect(controller.assistantHiddenHistory, hasLength(2));
      expect(controller.showAssistantHistoryPeek, isTrue);
      expect(controller.messages.first['content'], '用户2');

      await controller.loadOlderHistory();
      await tester.pump();

      expect(controller.messages, hasLength(20));
      expect(controller.assistantHiddenHistory, isEmpty);
      expect(controller.showAssistantHistoryPeek, isFalse);
      expect(controller.messages.first['content'], '用户0');
      expect(controller.messages[1]['content'], '助理1');
    });

    testWidgets('initialize 会保留 canonical persisted assistant turn 并过滤空白脏消息', (
      tester,
    ) async {
      final sessionId = 'local_assistant_persisted_turn';
      final gateway = _FakeAssistantGateway(
        sessions: <Map<String, dynamic>>[
          <String, dynamic>{
            'sessionId': sessionId,
            'topicTitle': '周末出行',
            'isActive': true,
          },
        ],
        sessionDetails: <String, Map<String, dynamic>>{
          sessionId: <String, dynamic>{
            'topicTitle': '周末出行',
            'messages': <Map<String, dynamic>>[
              <String, dynamic>{'role': 'user', 'content': '周末去哪玩？'},
              _canonicalHistoryAssistantMessage('可以优先看川西短线。'),
              <String, dynamic>{'role': 'assistant', 'content': ''},
            ],
          },
        },
      );

      final controller = await _mountController(
        tester,
        overrides: [
          assistantRemoteConfiguredProvider.overrideWith((ref) => false),
          assistantGatewayProvider.overrideWithValue(gateway),
        ],
      );

      await controller.initialize();
      await tester.pump();

      expect(controller.messages, hasLength(2));
      expect(controller.messages.last['senderId'], AppConceptConstants.assistantSenderId);
      expect(controller.messages.last['content'], '可以优先看川西短线。');
      expect(controller.assistantHiddenHistory, isEmpty);
      expect(controller.showAssistantHistoryPeek, isFalse);
    });
  });
}

Future<AssistantConversationController> _mountController(
  WidgetTester tester, {
  required dynamic overrides,
}) async {
  final completer = Completer<AssistantConversationController>();

  await tester.pumpWidget(
    ProviderScope(
      overrides: overrides,
      child: MaterialApp(
        home: _ControllerHarness(
          onReady: (controller) {
            if (!completer.isCompleted) {
              completer.complete(controller);
            }
          },
        ),
      ),
    ),
  );

  return completer.future;
}

List<Map<String, dynamic>> _buildHistoryMessages(int count) {
  return List<Map<String, dynamic>>.generate(count, (index) {
    final isUser = index.isEven;
    return <String, dynamic>{
      'role': isUser ? 'user' : 'assistant',
      'content': isUser ? '用户$index' : '助理$index',
    };
  });
}

Map<String, dynamic> _canonicalHistoryAssistantMessage(String content) {
  return <String, dynamic>{
    'role': 'assistant',
    'content': '',
    ...buildPersistedAssistantTurnFields(
      journey: const AssistantJourney(),
      displayMarkdown: content,
      displayPlainText: content,
      followupPrompt: '',
      actionHints: const <String>[],
      elapsedMs: 800,
    ),
  };
}

class _ControllerHarness extends ConsumerStatefulWidget {
  const _ControllerHarness({required this.onReady});

  final ValueChanged<AssistantConversationController> onReady;

  @override
  ConsumerState<_ControllerHarness> createState() => _ControllerHarnessState();
}

class _ControllerHarnessState extends ConsumerState<_ControllerHarness> {
  late final AssistantConversationController controller;

  @override
  void initState() {
    super.initState();
    controller = AssistantConversationController(ref: ref);
    widget.onReady(controller);
  }

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return const SizedBox.shrink();
  }
}

class _FakeAssistantGateway extends AssistantGateway {
  _FakeAssistantGateway({
    required this.sessions,
    required this.sessionDetails,
  }) : super(AssistantRuntime.createForTest());

  final List<Map<String, dynamic>> sessions;
  final Map<String, Map<String, dynamic>> sessionDetails;

  @override
  Future<List<Map<String, dynamic>>> listSessions() async => sessions;

  @override
  Future<Map<String, dynamic>?> sessionDetail(String sessionId) async {
    return sessionDetails[sessionId];
  }
}
