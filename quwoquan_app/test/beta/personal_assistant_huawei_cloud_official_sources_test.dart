import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/assistant/pages/personal_assistant_conversation_page.dart';
import 'package:quwoquan_app/ui/assistant/providers/personal_assistant_stream_controller.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  final directoryController = _PathProviderDirectoryController();
  _installPathProviderMock(directoryController);

  testWidgets('找私助 beta 权威来源问答回归', (tester) async {
    for (final promptCase in _authorityPromptCases) {
      directoryController.reset();
      final state = await _runPromptCase(tester, promptCase);
      expect(state.running, isFalse, reason: promptCase.name);
      expect(state.errorMessage, isEmpty, reason: promptCase.name);
      expect(state.answer.trim(), isNotEmpty, reason: promptCase.name);
      expect(
        state.answer.length,
        greaterThanOrEqualTo(120),
        reason: promptCase.name,
      );
      expect(
        state.processSummary.processingSummary.trim(),
        isNotEmpty,
        reason: promptCase.name,
      );
      expect(
        state.processSummary.acceptedReferences.length,
        greaterThanOrEqualTo(promptCase.minimumReferenceCount),
        reason: promptCase.name,
      );
      if (promptCase.requireKnowledgeSourcesSection) {
        expect(state.answer, contains('知识来源'), reason: promptCase.name);
      }
      for (final keyword in promptCase.expectedKeywords) {
        expect(state.answer, contains(keyword), reason: promptCase.name);
      }
      final hosts = <String>{};
      for (final reference in state.processSummary.acceptedReferences) {
        final uri = Uri.tryParse(reference.url);
        final host = (uri?.host ?? '').toLowerCase();
        expect(
          uri?.scheme,
          'https',
          reason: '${promptCase.name} source scheme',
        );
        expect(host, isNotEmpty, reason: '${promptCase.name} missing host');
        hosts.add(host);
      }
      if (promptCase.minimumDistinctHosts > 1) {
        expect(
          hosts.length,
          greaterThanOrEqualTo(promptCase.minimumDistinctHosts),
          reason: '${promptCase.name} distinct hosts=$hosts',
        );
      }
    }
  });
}

class _AuthorityPromptCase {
  const _AuthorityPromptCase({
    required this.name,
    required this.prompt,
    required this.expectedKeywords,
    this.minimumReferenceCount = 2,
    this.minimumDistinctHosts = 1,
    this.requireKnowledgeSourcesSection = true,
  });

  final String name;
  final String prompt;
  final List<String> expectedKeywords;
  final int minimumReferenceCount;
  final int minimumDistinctHosts;
  final bool requireKnowledgeSourcesSection;
}

const _authorityPromptCases = <_AuthorityPromptCase>[
  _AuthorityPromptCase(
    name: '生产式AI资源清单',
    prompt:
        '假如你是位资深运营规划架构师，现在需要创建一个生产式AI应用，需要购买哪些云资源，基于性价比考虑，请给出具体的资源清单列表，要有具体的规格和价格信息。请优先检索权威/官方资料，并标注知识来源；如有必要，可以引用多家官方资料做对比。',
    expectedKeywords: <String>['规格', '价格'],
  ),
  _AuthorityPromptCase(
    name: '奇迹MU配置推荐',
    prompt:
        '我打算和朋友一起玩的游戏是奇迹mus20，给我推荐一套云上配置，人数最多8人。请基于权威资料给出服务器规格、网络与计费建议，并标注知识来源。',
    expectedKeywords: <String>['云服务器', '带宽'],
  ),
  _AuthorityPromptCase(
    name: '云桌面按需计费关机',
    prompt:
        '你好，我想问下云桌面的按需计费问题，假如云桌面主机关机的情况下，还会计费吗？如果不同厂商官方规则有差异，可以一起对比说明，并标注知识来源。',
    expectedKeywords: <String>['关机', '计费'],
  ),
  _AuthorityPromptCase(
    name: '模型调试学习规划',
    prompt: '我是一个开发者，想学习打模型调试，请帮我规划一个合适的云服务，并提供一个购买指引。请优先使用权威资料，并标注知识来源。',
    expectedKeywords: <String>['模型', '购买'],
  ),
];

Future<PersonalAssistantStreamState> _runPromptCase(
  WidgetTester tester,
  _AuthorityPromptCase promptCase,
) async {
  Future<PersonalAssistantStreamState> sendOnce() async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(home: PersonalAssistantConversationPage()),
      ),
    );
    await _pumpFrames(tester, count: 8);
    expect(find.byKey(TestKeys.assistantChatInputField), findsOneWidget);
    await tester.ensureVisible(find.byKey(TestKeys.assistantChatInputField));
    await tester.pump(const Duration(milliseconds: 100));
    await tester.enterText(
      find.byKey(TestKeys.assistantChatInputField),
      promptCase.prompt,
    );
    tester.testTextInput.updateEditingValue(
      TextEditingValue(
        text: promptCase.prompt,
        selection: TextSelection.collapsed(offset: promptCase.prompt.length),
      ),
    );
    await _tapSend(tester, promptCase.prompt);
    await _pumpUntilSettled(tester);
    final context = tester.element(
      find.byType(PersonalAssistantConversationPage),
    );
    return ProviderScope.containerOf(
      context,
    ).read(personalAssistantStreamControllerProvider);
  }

  var state = await sendOnce();
  final retryNeeded =
      state.errorMessage.isNotEmpty ||
      state.answer.trim().isEmpty ||
      state.processSummary.acceptedReferences.length < 2;
  if (!retryNeeded) {
    return state;
  }
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump(const Duration(milliseconds: 200));
  final retryState = await sendOnce();
  return _pickBetterState(state, retryState);
}

Future<void> _tapSend(WidgetTester tester, String question) async {
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
  final context = tester.element(
    find.byType(PersonalAssistantConversationPage),
  );
  await ProviderScope.containerOf(
    context,
  ).read(personalAssistantStreamControllerProvider.notifier).send(question);
}

Future<void> _pumpUntilSettled(WidgetTester tester) async {
  for (var i = 0; i < 1800; i++) {
    await tester.pump(const Duration(milliseconds: 100));
    final context = tester.element(
      find.byType(PersonalAssistantConversationPage),
    );
    final state = ProviderScope.containerOf(
      context,
    ).read(personalAssistantStreamControllerProvider);
    if (!state.running) {
      return;
    }
  }
  fail('找私助 beta 权威来源问答未在预期时间内结束');
}

Future<void> _pumpFrames(WidgetTester tester, {int count = 6}) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

class _PathProviderDirectoryController {
  Directory _directory = Directory.systemTemp.createTempSync(
    'assistant-huawei-cloud-beta-',
  );

  String get path => _directory.path;

  void reset() {
    if (_directory.existsSync()) {
      _directory.deleteSync(recursive: true);
    }
    _directory = Directory.systemTemp.createTempSync(
      'assistant-huawei-cloud-beta-',
    );
  }
}

void _installPathProviderMock(_PathProviderDirectoryController controller) {
  const channel = MethodChannel('plugins.flutter.io/path_provider');
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(channel, (call) async {
        switch (call.method) {
          case 'getApplicationDocumentsDirectory':
          case 'getApplicationSupportDirectory':
          case 'getTemporaryDirectory':
            return controller.path;
          default:
            return null;
        }
      });
}

PersonalAssistantStreamState _pickBetterState(
  PersonalAssistantStreamState current,
  PersonalAssistantStreamState retry,
) {
  int score(PersonalAssistantStreamState state) {
    var total = 0;
    if (state.errorMessage.isEmpty) {
      total += 10;
    }
    total += state.processSummary.acceptedReferences.length * 3;
    total += state.answer.trim().isNotEmpty ? 2 : 0;
    total += state.answer.length ~/ 80;
    return total;
  }

  return score(retry) > score(current) ? retry : current;
}
