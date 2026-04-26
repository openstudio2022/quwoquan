library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:quwoquan_app/assistant/persistence/assistant_storage_path.dart';
import 'package:quwoquan_app/components/assistant/petal_mark.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/main.dart' as app;
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_message_bubble.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('native system context keeps iPhone weather query alive', (
    tester,
  ) async {
    final originalOnError = FlutterError.onError;
    try {
      await _resetAssistantApp(tester);
      await _wipeAssistantStorage();
      _suppressNetworkImageErrors();

      app.main();
      await _waitForMainEntry(tester);
      await _openAssistantConversation(tester);
      await _waitForChatInput(tester);

      final answer = await _sendQueryAndWaitForAnswer(
        tester,
        query: 'shen Zheng tian qi',
      );

      expect(answer.trim(), isNotEmpty);
      expect(answer, isNot(contains('系统上下文暂不可用')));
      expect(answer, isNot(contains('这次生成答案失败')));
      expect(answer, contains('深圳'));
      expect(
        answer.contains('天气') || answer.contains('气温') || answer.contains('降雨'),
        isTrue,
      );
    } finally {
      FlutterError.onError = originalOnError;
      await _resetAssistantApp(tester);
    }
  });
}

Future<void> _resetAssistantApp(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump(const Duration(milliseconds: 300));
}

Future<void> _wipeAssistantStorage() async {
  final sessionsPath = await getPersonalAssistantStoragePath('sessions.json');
  final storageDir = Directory(sessionsPath).parent;
  if (await storageDir.exists()) {
    await storageDir.delete(recursive: true);
  }
}

void _suppressNetworkImageErrors() {
  final original = FlutterError.onError;
  FlutterError.onError = (FlutterErrorDetails details) {
    final message = details.exception.toString();
    if (message.contains('HTTP request failed') ||
        message.contains('NetworkImageLoadException') ||
        message.contains('HandshakeException') ||
        message.contains('Connection terminated during handshake')) {
      return;
    }
    original?.call(details);
  };
}

Future<void> _waitForMainEntry(WidgetTester tester) async {
  await _pumpUntil(
    tester,
    condition: () =>
        find.text(AppConceptConstants.assistantTabLabel).evaluate().isNotEmpty ||
        find.byType(PetalMark).evaluate().isNotEmpty ||
        find.text('微趣').evaluate().isNotEmpty,
    timeout: const Duration(seconds: 20),
  );
}

Future<void> _openAssistantConversation(WidgetTester tester) async {
  final assistantTabEntry = find.text(AppConceptConstants.assistantTabLabel);
  await _pumpUntil(
    tester,
    condition: () => assistantTabEntry.evaluate().isNotEmpty,
    timeout: const Duration(seconds: 20),
  );

  final tappableAssistantTab = assistantTabEntry.hitTestable();
  await _pumpUntil(
    tester,
    condition: () => tappableAssistantTab.evaluate().isNotEmpty,
    timeout: const Duration(seconds: 10),
  );

  await tester.ensureVisible(tappableAssistantTab.first);
  await tester.tap(tappableAssistantTab.first, warnIfMissed: false);
  await tester.pump();

  await _pumpUntil(
    tester,
    condition: () =>
        find.byKey(TestKeys.assistantTabPage).evaluate().isNotEmpty,
    timeout: const Duration(seconds: 10),
  );
  await _ensureAssistantDialogReady(tester);
}

Future<void> _waitForChatInput(WidgetTester tester) async {
  await _pumpUntil(
    tester,
    condition: () => find
        .byKey(TestKeys.assistantChatInputField)
        .hitTestable()
        .evaluate()
        .isNotEmpty,
    timeout: const Duration(seconds: 20),
  );
}

Future<void> _ensureAssistantDialogReady(WidgetTester tester) async {
  final dialogTab = find.byKey(TestKeys.assistantDialogTab).hitTestable();
  await _pumpUntil(
    tester,
    condition: () => dialogTab.evaluate().isNotEmpty,
    timeout: const Duration(seconds: 10),
  );
  await tester.ensureVisible(dialogTab.first);
  await tester.tap(dialogTab.first, warnIfMissed: false);
  await tester.pump(const Duration(milliseconds: 400));
  await _pumpUntil(
    tester,
    condition: () =>
        find.byKey(TestKeys.assistantDialogPage).evaluate().isNotEmpty &&
        find
            .byKey(TestKeys.assistantChatInputField)
            .hitTestable()
            .evaluate()
            .isNotEmpty,
    timeout: const Duration(seconds: 10),
  );
}

Future<String> _sendQueryAndWaitForAnswer(
  WidgetTester tester, {
  required String query,
}) async {
  await _ensureAssistantDialogReady(tester);
  final chatScope = find.byKey(TestKeys.assistantDialogPage);
  await _pumpUntil(
    tester,
    condition: () =>
        chatScope.evaluate().isNotEmpty &&
        find
            .descendant(
              of: chatScope.last,
              matching: find.byKey(TestKeys.assistantChatInputField),
            )
            .hitTestable()
            .evaluate()
            .isNotEmpty,
    timeout: const Duration(seconds: 10),
  );

  final inputField = find
      .descendant(
        of: chatScope.last,
        matching: find.byKey(TestKeys.assistantChatInputField),
      )
      .last;
  await tester.ensureVisible(inputField);
  await tester.tap(inputField, warnIfMissed: false);
  await tester.pump();
  await tester.showKeyboard(inputField);
  await tester.pump();
  await tester.enterText(inputField, query);
  await tester.pump(const Duration(milliseconds: 600));

  final sendButton = find
      .descendant(
        of: chatScope.last,
        matching: find.byKey(TestKeys.assistantSendButton),
      )
      .hitTestable()
      .last;
  await tester.ensureVisible(sendButton);
  await tester.tap(sendButton, warnIfMissed: false);
  await tester.pump();

  await _pumpUntil(
    tester,
    condition: () =>
        find.descendant(of: chatScope.last, matching: find.text(query)).evaluate().isNotEmpty ||
        find.text(query).evaluate().isNotEmpty,
    timeout: const Duration(seconds: 15),
  );

  var stableTicks = 0;
  var previousAnswer = '';
  final deadline = DateTime.now().add(const Duration(seconds: 90));
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(seconds: 1));
    final snapshot = _latestAssistantSnapshot(tester);
    if (snapshot == null) {
      continue;
    }
    final currentAnswer = snapshot.answerText.trim();
    if (currentAnswer.isEmpty) {
      continue;
    }
    if (currentAnswer == previousAnswer) {
      stableTicks += 1;
    } else {
      stableTicks = 0;
      previousAnswer = currentAnswer;
    }
    if (!snapshot.streaming && stableTicks >= 2) {
      return currentAnswer;
    }
  }
  throw TestFailure('等待天气回答超时');
}

Future<void> _pumpUntil(
  WidgetTester tester, {
  required bool Function() condition,
  required Duration timeout,
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
    if (condition()) return;
  }
  throw TestFailure('条件等待超时: $timeout');
}

_AssistantBubbleSnapshot? _latestAssistantSnapshot(WidgetTester tester) {
  final dialogScope = find.byKey(TestKeys.assistantDialogPage);
  final assistantBubbleFinder = dialogScope.evaluate().isNotEmpty
      ? find.descendant(
          of: dialogScope.last,
          matching: find.byWidgetPredicate(
            (widget) =>
                widget is AssistantMessageBubble &&
                (widget.asTimelineProtocolMap['senderId'] as String?) ==
                    AppConceptConstants.assistantSenderId,
          ),
        )
      : find.byWidgetPredicate(
          (widget) =>
              widget is AssistantMessageBubble &&
              (widget.asTimelineProtocolMap['senderId'] as String?) ==
                  AppConceptConstants.assistantSenderId,
        );
  if (assistantBubbleFinder.evaluate().isEmpty) return null;
  final bubble = tester.widget<AssistantMessageBubble>(assistantBubbleFinder.last);
  return _AssistantBubbleSnapshot(message: bubble.asTimelineProtocolMap);
}

class _AssistantBubbleSnapshot {
  const _AssistantBubbleSnapshot({required this.message});

  final Map<String, dynamic> message;

  String get answerText => (message['displayMarkdown'] as String?)?.trim() ?? '';

  bool get streaming => message['streaming'] == true;
}
