import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_tab_page.dart';
import 'package:quwoquan_app/ui/assistant/providers/personal_assistant_stream_controller.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  _mockPathProviderForIntegrationTest();

  testWidgets('找私助 beta 多轮继承上下文并可切到找小趣', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: MaterialApp(home: AssistantTabPage())),
    );
    await _pumpFrames(tester, count: 8);

    await tester.tap(find.text('找私助'));
    await _pumpFrames(tester, count: 4);
    expect(find.byKey(TestKeys.assistantChatInputField), findsOneWidget);

    await _send(tester, 'Shen zhen tian qi');
    final firstState = _controllerState(tester);
    expect(firstState.errorMessage, isEmpty);
    expect(firstState.answer, contains('深圳'));
    expect(firstState.processSummary.searchCount, greaterThanOrEqualTo(1));

    await _sendThroughController(tester, '剩下2天有什么外出推荐，四口之家');
    final secondState = _controllerState(tester);
    expect(secondState.errorMessage, isEmpty);
    expect(secondState.answer, isNotEmpty);
    expect(secondState.processSummary.searchCount, 3);
    expect(secondState.processSummary.acceptedCount, greaterThanOrEqualTo(1));
    expect(
      secondState.processSummary.acceptedReferences.first.url,
      startsWith('https://open-meteo.com'),
    );

    final prompts = secondState.events
        .where((event) => event.eventType == 'assistant.model.interaction')
        .map((event) => event.payload['requestUserPrompt']?.toString() ?? '')
        .where((prompt) => prompt.isNotEmpty)
        .toList(growable: false);
    expect(prompts.any((prompt) => prompt.contains('同一会话前文')), isTrue);
    expect(
      prompts.any(
        (prompt) => prompt.contains('深圳') || prompt.contains('Shen zhen'),
      ),
      isTrue,
    );
    expect(prompts.any((prompt) => prompt.contains('四口之家')), isTrue);

    await tester.tap(find.text('找小趣'));
    await _pumpFrames(tester, count: 8);
    expect(find.byKey(TestKeys.assistantDialogPage), findsOneWidget);
  });
}

PersonalAssistantStreamState _controllerState(WidgetTester tester) {
  final context = tester.element(find.byType(AssistantTabPage));
  return ProviderScope.containerOf(
    context,
  ).read(personalAssistantStreamControllerProvider);
}

Future<void> _send(WidgetTester tester, String text) async {
  await tester.ensureVisible(find.byKey(TestKeys.assistantChatInputField));
  await tester.pump(const Duration(milliseconds: 100));
  await tester.enterText(find.byKey(TestKeys.assistantChatInputField), text);
  tester.testTextInput.updateEditingValue(
    TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: text.length),
    ),
  );
  await _tapSend(tester);
  await _pumpUntilSettled(tester);
}

Future<void> _sendThroughController(WidgetTester tester, String text) async {
  final context = tester.element(find.byType(AssistantTabPage));
  await ProviderScope.containerOf(
    context,
  ).read(personalAssistantStreamControllerProvider.notifier).send(text);
  await _pumpUntilSettled(tester);
}

Future<void> _tapSend(WidgetTester tester) async {
  for (var i = 0; i < 40; i++) {
    await tester.pump(const Duration(milliseconds: 100));
    await tester.ensureVisible(find.byKey(TestKeys.assistantChatInputField));
    final keyed = find.byKey(TestKeys.assistantSendButton);
    if (keyed.evaluate().isNotEmpty) {
      await tester.tap(keyed, warnIfMissed: false);
      return;
    }
    final textButtons = find.text('发送');
    if (textButtons.evaluate().isNotEmpty) {
      await tester.tap(textButtons.last, warnIfMissed: false);
      return;
    }
  }
  fail('找私助发送按钮不可用');
}

Future<void> _pumpUntilSettled(WidgetTester tester) async {
  for (var i = 0; i < 700; i++) {
    await tester.pump(const Duration(milliseconds: 100));
    final state = _controllerState(tester);
    if (!state.running && state.turnId.isNotEmpty) {
      return;
    }
  }
  fail('找私助流式响应未在预期时间内结束');
}

Future<void> _pumpFrames(WidgetTester tester, {int count = 4}) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

void _mockPathProviderForIntegrationTest() {
  const channel = MethodChannel('plugins.flutter.io/path_provider');
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(channel, (call) async {
        final directory = Directory.systemTemp.createTempSync(
          'quwoquan-assistant-multiturn-',
        );
        addTearDown(() {
          if (directory.existsSync()) {
            directory.deleteSync(recursive: true);
          }
        });
        switch (call.method) {
          case 'getApplicationDocumentsDirectory':
          case 'getApplicationSupportDirectory':
          case 'getTemporaryDirectory':
            return directory.path;
          default:
            return null;
        }
      });
}
