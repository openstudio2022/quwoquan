library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:quwoquan_app/components/assistant/petal_mark.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/main.dart' as app;
import 'package:quwoquan_app/ui/chat/widgets/message/chat_message_bubble.dart';

const _firstQuery = '如果把九寨沟方向考虑进去，多给我几个备选方案';
const _secondQuery = '土拨鼠观赏最佳时间';

const _phaseHints = <String>[
  '我先帮你理清问题',
  '我在替你核对资料',
  '我在帮你整理判断',
  '我在组织最终回答',
  '我在确认现在的信息够不够回答',
  '已为你整理好',
  '正在搜索',
  '正在整理',
  '正在回答',
];

const _forbiddenFragments = <String>[
  'assistant_turn',
  'contractVersion',
  'queryTasks',
  '<tool_call>',
  'tool_call',
  '```md',
  '```card:',
  'machineEnvelope',
  'runArtifactsV1',
  'historySummarySnippet',
  'longtermMemorySummary":"{',
  '我先帮你把',
  '我先把收敛框架给你',
  '收一收',
  '检索完成但信息不足',
  '当前模型服务不可用',
  '安全降级模式',
  '先给你当前最稳的部分',
  '可以问：这张图有什么亮点？',
];

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('真实两轮助理问答界面联调', (tester) async {
    final originalOnError = FlutterError.onError;
    addTearDown(() {
      FlutterError.onError = originalOnError;
    });
    _suppressNetworkImageErrors();
    app.main();

    await _waitForMainEntry(tester);
    await _openAssistantConversation(tester);
    await _waitForChatInput(tester);

    final firstResult = await _sendQueryWithSingleRetry(
      tester,
      query: _firstQuery,
    );
    debugPrint('FIRST_RESULT: ${firstResult.toJson()}');
    _expectReplayResult(firstResult);

    final secondResult = await _sendQueryWithSingleRetry(
      tester,
      query: _secondQuery,
    );
    debugPrint('SECOND_RESULT: ${secondResult.toJson()}');
    _expectReplayResult(secondResult);

    binding.reportData = <String, dynamic>{
      'firstQuery': firstResult.toJson(),
      'secondQuery': secondResult.toJson(),
    };
  });
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

  final recentConversationTitle = find.text('最近对话');
  final openConversationHint = find.text('点击开始对话');
  await _pumpUntil(
    tester,
    condition: () =>
        recentConversationTitle.evaluate().isNotEmpty &&
        openConversationHint.evaluate().isNotEmpty,
    timeout: const Duration(seconds: 20),
  );

  final tappableConversationHint = openConversationHint.hitTestable();
  await _pumpUntil(
    tester,
    condition: () => tappableConversationHint.evaluate().isNotEmpty,
    timeout: const Duration(seconds: 10),
  );
  await tester.ensureVisible(tappableConversationHint.first);
  await tester.tap(tappableConversationHint.first, warnIfMissed: false);
  await tester.pump();
}

Future<void> _waitForChatInput(WidgetTester tester) async {
  await _pumpUntil(
    tester,
    condition: () => find.byType(TextField).evaluate().isNotEmpty,
    timeout: const Duration(seconds: 20),
  );
}

Future<_ReplayResult> _sendQueryAndWaitForAnswer(
  WidgetTester tester, {
  required String query,
}) async {
  final inputFields = find.byType(TextField).hitTestable();
  final snapshots = <String>[];
  var phaseLabelSeen = false;
  var degraded = false;
  var heuristicFallbackUsed = false;

  await _pumpUntil(
    tester,
    condition: () => inputFields.evaluate().isNotEmpty,
    timeout: const Duration(seconds: 10),
  );
  final inputField = inputFields.last;
  await tester.ensureVisible(inputField);
  await tester.tap(inputField, warnIfMissed: false);
  await tester.pump();
  await tester.showKeyboard(inputField);
  await tester.pump();
  await tester.enterText(inputField, query);
  await tester.pump(const Duration(milliseconds: 300));
  final sendButtons = find.byIcon(Icons.arrow_upward_rounded).hitTestable();
  await _pumpUntil(
    tester,
    condition: () => sendButtons.evaluate().isNotEmpty,
    timeout: const Duration(seconds: 10),
  );
  final sendButton = sendButtons.last;
  await tester.ensureVisible(sendButton);
  await tester.tap(sendButton, warnIfMissed: false);
  await tester.pump();

  await _pumpUntil(
    tester,
    condition: () => find.text(query).evaluate().isNotEmpty,
    timeout: const Duration(seconds: 15),
  );

  String latestText = '';
  String latestAnswer = '';
  var matchedExpected = false;
  var stableTicks = 0;
  String previousAnswer = '';
  final deadline = DateTime.now().add(const Duration(seconds: 80));
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(seconds: 1));
    final snapshot = _latestAssistantSnapshot(tester);
    if (snapshot == null) {
      continue;
    }
    latestText = snapshot.bubbleText;
    latestAnswer = snapshot.answerText;
    degraded = snapshot.degraded;
    heuristicFallbackUsed = snapshot.heuristicFallbackUsed;
    snapshots.add(latestText);
    _throwIfForbidden(latestText);
    if (_phaseHints.any(latestText.contains)) {
      phaseLabelSeen = true;
    }
    if (_matchesExpectation(query, latestAnswer)) {
      matchedExpected = true;
    }
    if (latestAnswer == previousAnswer) {
      stableTicks += 1;
    } else {
      stableTicks = 0;
      previousAnswer = latestAnswer;
    }
    if (matchedExpected &&
        !degraded &&
        !heuristicFallbackUsed &&
        latestAnswer.trim().isNotEmpty &&
        stableTicks >= 2) {
      break;
    }
  }

  return _ReplayResult(
    query: query,
    phaseLabelSeen: phaseLabelSeen,
    matchedExpected: matchedExpected,
    degraded: degraded,
    heuristicFallbackUsed: heuristicFallbackUsed,
    finalAnswerText: latestAnswer,
    finalVisibleText: latestText,
    snapshotsObserved: snapshots.length,
  );
}

Future<_ReplayResult> _sendQueryWithSingleRetry(
  WidgetTester tester, {
  required String query,
}) async {
  final first = await _sendQueryAndWaitForAnswer(tester, query: query);
  if (!_shouldRetryReplay(first)) {
    return first;
  }
  debugPrint('RETRY_RESULT_TRIGGERED: ${first.toJson()}');
  return _sendQueryAndWaitForAnswer(tester, query: query);
}

bool _shouldRetryReplay(_ReplayResult result) {
  final answer = result.finalAnswerText.trim();
  if (answer.isEmpty) return true;
  return answer.contains('模型输出无效，已停止本轮回答。') ||
      answer.contains('没有生成可展示结果');
}

Future<void> _pumpUntil(
  WidgetTester tester, {
  required bool Function() condition,
  required Duration timeout,
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 250));
    if (condition()) return;
  }
  throw TestFailure('条件等待超时: $timeout');
}

_AssistantBubbleSnapshot? _latestAssistantSnapshot(WidgetTester tester) {
  final assistantBubbleFinder = find.byWidgetPredicate(
    (widget) =>
        widget is ChatMessageBubble &&
        (widget.message['senderId'] as String?) ==
            AppConceptConstants.assistantSenderId,
    description: 'assistant bubble',
  );
  if (assistantBubbleFinder.evaluate().isEmpty) return null;
  final latestBubbleFinder = assistantBubbleFinder.last;
  final bubble = tester.widget<ChatMessageBubble>(latestBubbleFinder);
  final bubbleText = _collectVisibleText(tester, scope: latestBubbleFinder);
  return _AssistantBubbleSnapshot(
    message: bubble.message,
    bubbleText: bubbleText,
  );
}

String _collectVisibleText(WidgetTester tester, {Finder? scope}) {
  final lines = <String>[];
  final textFinder = scope == null
      ? find.byType(Text).hitTestable()
      : find.descendant(of: scope, matching: find.byType(Text)).hitTestable();
  final richTextFinder = scope == null
      ? find.byType(RichText).hitTestable()
      : find
            .descendant(of: scope, matching: find.byType(RichText))
            .hitTestable();
  final selectableTextFinder = scope == null
      ? find.byType(SelectableText).hitTestable()
      : find
            .descendant(of: scope, matching: find.byType(SelectableText))
            .hitTestable();

  for (final widget in tester.widgetList<Text>(textFinder)) {
    _appendLine(lines, widget.data ?? widget.textSpan?.toPlainText() ?? '');
  }
  for (final widget in tester.widgetList<RichText>(richTextFinder)) {
    _appendLine(lines, widget.text.toPlainText());
  }
  for (final widget in tester.widgetList<SelectableText>(
    selectableTextFinder,
  )) {
    _appendLine(lines, widget.data ?? widget.textSpan?.toPlainText() ?? '');
  }

  return lines.join('\n');
}

void _appendLine(List<String> lines, String raw) {
  final normalized = raw.replaceAll(RegExp(r'\s+'), ' ').trim();
  if (normalized.isEmpty) return;
  if (lines.contains(normalized)) return;
  lines.add(normalized);
}

void _throwIfForbidden(String text) {
  for (final fragment in _forbiddenFragments) {
    if (text.contains(fragment)) {
      final snippet = text.length > 220 ? '${text.substring(0, 220)}…' : text;
      throw TestFailure('界面出现内部协议/旧话术片段: $fragment | $snippet');
    }
  }
}

bool _matchesExpectation(String query, String text) {
  if (query == _firstQuery) {
    return _matchesTravelAlternativeAnswer(text);
  }
  if (query == _secondQuery) {
    return _matchesWildlifeBestTimeAnswer(text);
  }
  return text.trim().isNotEmpty;
}

bool _matchesTravelAlternativeAnswer(String text) {
  final normalized = _normalizeLoose(text);
  final hasTopic = normalized.contains('九寨沟');
  final routeSignals = RegExp(
    r'(路线|行程|方案|备选|四日游|五日游|自由行|成都|黄龙|川主寺|若尔盖|藏寨)',
  ).allMatches(normalized).length;
  final hasSubstance = normalized.length >= 24;
  return hasTopic && routeSignals >= 2 && hasSubstance;
}

bool _matchesWildlifeBestTimeAnswer(String text) {
  final normalized = _normalizeLoose(text);
  final hasTopic =
      normalized.contains('土拨鼠') &&
      (normalized.contains('观赏') || normalized.contains('看到'));
  final hasTiming = RegExp(
    r'(最佳|时间|月份|季节|窗口|5月|6月|7月|8月|9月|早上|上午|傍晚|下午|天气)',
  ).hasMatch(normalized);
  return hasTopic && hasTiming;
}

String _normalizeLoose(String text) {
  return text.replaceAll(RegExp(r'\s+'), ' ').trim();
}

void _expectReplayResult(_ReplayResult result) {
  expect(result.phaseLabelSeen, isTrue, reason: '过程区必须先出现用户可理解的阶段提示');
  expect(result.degraded, isFalse, reason: '真实回放不允许进入 degraded');
  expect(
    result.heuristicFallbackUsed,
    isFalse,
    reason: '真实回放不允许由 heuristic fallback 覆盖对题答案',
  );
  expect(
    result.finalAnswerText.trim(),
    isNotEmpty,
    reason: '最终 assistant answer 不得为空',
  );
  expect(
    result.matchedExpected,
    isTrue,
    reason: '最终 assistant answer 必须满足该问题的对题锚点',
  );
}

class _ReplayResult {
  const _ReplayResult({
    required this.query,
    required this.phaseLabelSeen,
    required this.matchedExpected,
    required this.degraded,
    required this.heuristicFallbackUsed,
    required this.finalAnswerText,
    required this.finalVisibleText,
    required this.snapshotsObserved,
  });

  final String query;
  final bool phaseLabelSeen;
  final bool matchedExpected;
  final bool degraded;
  final bool heuristicFallbackUsed;
  final String finalAnswerText;
  final String finalVisibleText;
  final int snapshotsObserved;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'query': query,
      'phaseLabelSeen': phaseLabelSeen,
      'matchedExpected': matchedExpected,
      'degraded': degraded,
      'heuristicFallbackUsed': heuristicFallbackUsed,
      'finalAnswerText': finalAnswerText,
      'snapshotsObserved': snapshotsObserved,
      'finalVisibleText': finalVisibleText,
    };
  }
}

class _AssistantBubbleSnapshot {
  const _AssistantBubbleSnapshot({
    required this.message,
    required this.bubbleText,
  });

  final Map<String, dynamic> message;
  final String bubbleText;

  String get answerText {
    final displayPlain = (message['displayPlainText'] as String?)?.trim() ?? '';
    if (displayPlain.isNotEmpty) return displayPlain;
    final displayMarkdown = (message['displayMarkdown'] as String?)?.trim() ?? '';
    if (displayMarkdown.isNotEmpty) return displayMarkdown;
    final visible = bubbleText.trim();
    if (visible.isNotEmpty) return visible;
    final streamed = (message['streamFinalAnswer'] as String?)?.trim() ?? '';
    if (streamed.isNotEmpty) return streamed;
    return (message['content'] as String?)?.trim() ?? '';
  }

  bool get degraded => message['degraded'] == true;

  bool get heuristicFallbackUsed =>
      message['heuristicFallbackUsed'] == true ||
      (((message['qualityMetrics'] as Map?)
              ?.cast<String, dynamic>())?['heuristicFallbackUsed']) ==
          true;
}
