library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/components/assistant/petal_mark.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/main.dart' as app;
import 'package:quwoquan_app/ui/chat/widgets/message/chat_message_bubble.dart';

const _firstQuery = '如果把九寨沟方向考虑进去，多给我几个备选方案';
const _secondQuery = '如果我只有4天，优先哪条路线？';
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
  '<function=',
  '</function',
  '<parameter=',
  '</parameter',
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
        find
            .text(AppConceptConstants.assistantTabLabel)
            .evaluate()
            .isNotEmpty ||
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

Future<_ReplayResult> _sendQueryAndWaitForAnswer(
  WidgetTester tester, {
  required String query,
}) async {
  await _ensureAssistantDialogReady(tester);
  final snapshots = <String>[];
  _AssistantBubbleSnapshot? latestSnapshot;
  var phaseLabelSeen = false;
  var degraded = false;
  var heuristicFallbackUsed = false;
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
  final inputFieldsInChat = find.descendant(
    of: chatScope.last,
    matching: find.byKey(TestKeys.assistantChatInputField),
  );
  final inputField = inputFieldsInChat.last;
  await tester.ensureVisible(inputField);
  await tester.tap(inputField, warnIfMissed: false);
  await tester.pump();
  await tester.showKeyboard(inputField);
  await tester.pump();
  await tester.enterText(inputField, query);
  await tester.pump(const Duration(milliseconds: 600));
  final sendButtons = find.descendant(
    of: chatScope.last,
    matching: find.byKey(TestKeys.assistantSendButton),
  );
  await _pumpUntil(
    tester,
    condition: () => sendButtons.hitTestable().evaluate().isNotEmpty,
    timeout: const Duration(seconds: 10),
  );
  final sendButton = sendButtons.hitTestable().last;
  await tester.ensureVisible(sendButton);
  await tester.tap(sendButton, warnIfMissed: false);
  await tester.pump();

  await _pumpUntil(
    tester,
    condition: () =>
        (chatScope.evaluate().isNotEmpty &&
            find
                .descendant(of: chatScope.last, matching: find.text(query))
                .evaluate()
                .isNotEmpty) ||
        find.text(query).evaluate().isNotEmpty,
    timeout: const Duration(seconds: 15),
  );

  String latestText = '';
  String latestAnswer = '';
  var matchedExpected = false;
  var stableTicks = 0;
  var finalMessageStreaming = true;
  String previousAnswer = '';
  final deadline = DateTime.now().add(const Duration(seconds: 80));
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(seconds: 1));
    final screenText = chatScope.evaluate().isNotEmpty
        ? _collectVisibleText(tester, scope: chatScope.last)
        : _collectVisibleText(tester);
    if (_phaseHints.any(screenText.contains)) {
      phaseLabelSeen = true;
    }
    final snapshot = _latestAssistantSnapshot(tester);
    if (snapshot == null) {
      continue;
    }
    latestSnapshot = snapshot;
    latestText = snapshot.bubbleText;
    latestAnswer = snapshot.answerText;
    finalMessageStreaming = snapshot.streaming;
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
        stableTicks >= 2 &&
        !finalMessageStreaming) {
      break;
    }
  }

  final processHeaderText = await _latestAssistantProcessHeaderText(tester);

  return _ReplayResult(
    query: query,
    phaseLabelSeen: phaseLabelSeen,
    matchedExpected: matchedExpected,
    degraded: degraded,
    heuristicFallbackUsed: heuristicFallbackUsed,
    finalAnswerText: latestAnswer,
    finalVisibleText: latestText,
    snapshotsObserved: snapshots.length,
    finalMessageStreaming: finalMessageStreaming,
    modelCallCount: latestSnapshot?.modelCallCount ?? 0,
    nextAction: latestSnapshot?.nextAction ?? '',
    finalAnswerMode: latestSnapshot?.finalAnswerMode ?? '',
    expandSignalCount: latestSnapshot?.expandSignalCount ?? 0,
    evidenceLedgerCount: latestSnapshot?.evidenceLedgerCount ?? 0,
    answerEvidenceBindingCount: latestSnapshot?.answerEvidenceBindingCount ?? 0,
    processHeaderText: processHeaderText,
    templateVersionUsed: latestSnapshot?.templateVersionUsed ?? '',
    phaseOneRoutingDiagnostics:
        latestSnapshot?.phaseOneRoutingDiagnostics ?? const <String, dynamic>{},
    timelinePhases: latestSnapshot?.timelinePhaseIds ?? const <String>[],
    journalStages: latestSnapshot?.journalStages ?? const <String>[],
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
  return answer.contains('模型输出无效，已停止本轮回答。') || answer.contains('没有生成可展示结果');
}

Future<void> _pumpUntil(
  WidgetTester tester, {
  required FutureOr<bool> Function() condition,
  required Duration timeout,
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 250));
    if (await condition()) return;
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
                widget is ChatMessageBubble &&
                (widget.message['senderId'] as String?) ==
                    AppConceptConstants.assistantSenderId,
            description: 'assistant bubble in assistant dialog',
          ),
        )
      : find.byWidgetPredicate(
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

Future<String> _latestAssistantProcessHeaderText(WidgetTester tester) async {
  final dialogScope = find.byKey(TestKeys.assistantDialogPage);
  final assistantBubbleFinder = dialogScope.evaluate().isNotEmpty
      ? find.descendant(
          of: dialogScope.last,
          matching: find.byWidgetPredicate(
            (widget) =>
                widget is ChatMessageBubble &&
                (widget.message['senderId'] as String?) ==
                    AppConceptConstants.assistantSenderId,
            description: 'assistant bubble in assistant dialog',
          ),
        )
      : find.byWidgetPredicate(
          (widget) =>
              widget is ChatMessageBubble &&
              (widget.message['senderId'] as String?) ==
                  AppConceptConstants.assistantSenderId,
          description: 'assistant bubble',
        );
  if (assistantBubbleFinder.evaluate().isEmpty) return '';
  final latestBubbleFinder = assistantBubbleFinder.last;
  final headerFinder = find.descendant(
    of: latestBubbleFinder,
    matching: find.byKey(TestKeys.assistantProcessHeader),
  );
  if (headerFinder.evaluate().isEmpty) return '';
  await tester.ensureVisible(headerFinder.last);
  await tester.pump(const Duration(milliseconds: 200));
  return _collectVisibleText(tester, scope: headerFinder.last);
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
  final normalized = raw
      .replaceAll(RegExp(r'[\uE000-\uF8FF]'), '')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();
  if (normalized.isEmpty) return;
  if (lines.contains(normalized)) return;
  lines.add(normalized);
}

void _throwIfForbidden(String text) {
  final fragment = _matchedForbiddenFragment(text);
  if (fragment != null) {
    final snippet = text.length > 220 ? '${text.substring(0, 220)}…' : text;
    throw TestFailure('界面出现内部协议/旧话术片段: $fragment | $snippet');
  }
  if (_containsStructuredLeak(text)) {
    final snippet = text.length > 220 ? '${text.substring(0, 220)}…' : text;
    throw TestFailure('界面出现结构碎片前缀: $snippet');
  }
}

String? _matchedForbiddenFragment(String text) {
  for (final fragment in _forbiddenFragments) {
    if (text.contains(fragment)) return fragment;
  }
  return null;
}

bool _containsInternalProtocolLeak(String text) {
  return _matchedForbiddenFragment(text) != null ||
      _containsStructuredLeak(text);
}

bool _containsStructuredLeak(String text) {
  if (AssistantDisplayTextResolver.hasStructuredPrefixLeak(text)) {
    return true;
  }
  for (final line in text.split('\n')) {
    if (AssistantDisplayTextResolver.hasStructuredPrefixLeak(line)) {
      return true;
    }
  }
  return false;
}

bool _matchesExpectation(String query, String text) {
  if (query == _firstQuery) {
    return _matchesTravelAlternativeAnswer(text);
  }
  if (query == _secondQuery) {
    return _matchesFollowupRouteAnswer(text);
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

bool _matchesFollowupRouteAnswer(String text) {
  final normalized = _normalizeLoose(text);
  final hasDuration =
      normalized.contains('4天') ||
      normalized.contains('四天') ||
      normalized.contains('4日') ||
      normalized.contains('四日');
  final hasRecommendation = RegExp(
    r'(优先|推荐|建议|更适合|首选|西线|东线|高铁|环线|路线)',
  ).hasMatch(normalized);
  final hasSubstance = normalized.length >= 20;
  return hasDuration && hasRecommendation && hasSubstance;
}

String _normalizeLoose(String text) {
  return text.replaceAll(RegExp(r'\s+'), ' ').trim();
}

bool _hasProcessProgressSummary(String text) {
  return RegExp(r'已完成\s+\d+/\d+\s+步').hasMatch(_normalizeLoose(text));
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
    result.finalMessageStreaming,
    isFalse,
    reason: '必须等 completed 落库后再判定最终 assistant answer',
  );
  expect(
    _containsInternalProtocolLeak(result.finalAnswerText),
    isFalse,
    reason: '最终 assistant answer 不得含内部协议或结构碎片',
  );
  expect(
    _containsInternalProtocolLeak(result.finalVisibleText),
    isFalse,
    reason: '最终界面可见文本不得含内部协议或结构碎片',
  );
  expect(
    _hasProcessProgressSummary(result.processHeaderText),
    isTrue,
    reason: '过程区应展示稳定的步骤进度摘要，便于用户感知当前收敛程度',
  );
  expect(
    result.matchedExpected,
    isTrue,
    reason: '最终 assistant answer 必须满足该问题的对题锚点',
  );
  expect(
    result.expandSignalCount,
    0,
    reason: '真实回放不应再落入 expanding/need_more_search 路径',
  );
  expect(
    result.evidenceLedgerCount,
    greaterThan(0),
    reason: '真实回放最终消息必须保留证据账，不能只剩表面答案文本',
  );
  expect(
    result.answerEvidenceBindingCount,
    greaterThan(0),
    reason: '真实回放最终消息必须保留答案来源绑定，避免 grounding 丢失',
  );
  expect(result.nextAction, 'answer', reason: '当前回放最终必须直接进入 answer');
  expect(
    result.finalAnswerMode,
    anyOf(equals('full'), equals('bounded_answer')),
    reason: '最终回答模式必须是 full 或 bounded_answer',
  );
  if (result.query == _firstQuery) {
    expect(
      result.modelCallCount,
      lessThanOrEqualTo(6),
      reason: '首轮应在有限模型调用内完成成答，避免反复扩检',
    );
  }
  if (result.query == _secondQuery) {
    expect(
      (result.phaseOneRoutingDiagnostics['route'] as String?) ?? '',
      'phase_one_direct_answer',
      reason: '第二轮连续追问应尽量直接在 phase-one 收口，不再回退 formal_synthesis',
    );
    expect(
      result.templateVersionUsed,
      'phase_one_direct_answer',
      reason: '第二轮连续追问应直接落到 phase-one direct-answer 模板出口',
    );
    expect(
      result.modelCallCount,
      lessThanOrEqualTo(4),
      reason: '第二轮连续追问应避免额外正式 synthesis 带来的调用膨胀',
    );
  }
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
    required this.finalMessageStreaming,
    required this.modelCallCount,
    required this.nextAction,
    required this.finalAnswerMode,
    required this.expandSignalCount,
    required this.evidenceLedgerCount,
    required this.answerEvidenceBindingCount,
    required this.processHeaderText,
    required this.templateVersionUsed,
    required this.phaseOneRoutingDiagnostics,
    required this.timelinePhases,
    required this.journalStages,
  });

  final String query;
  final bool phaseLabelSeen;
  final bool matchedExpected;
  final bool degraded;
  final bool heuristicFallbackUsed;
  final String finalAnswerText;
  final String finalVisibleText;
  final int snapshotsObserved;
  final bool finalMessageStreaming;
  final int modelCallCount;
  final String nextAction;
  final String finalAnswerMode;
  final int expandSignalCount;
  final int evidenceLedgerCount;
  final int answerEvidenceBindingCount;
  final String processHeaderText;
  final String templateVersionUsed;
  final Map<String, dynamic> phaseOneRoutingDiagnostics;
  final List<String> timelinePhases;
  final List<String> journalStages;

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
      'finalMessageStreaming': finalMessageStreaming,
      'modelCallCount': modelCallCount,
      'nextAction': nextAction,
      'finalAnswerMode': finalAnswerMode,
      'expandSignalCount': expandSignalCount,
      'evidenceLedgerCount': evidenceLedgerCount,
      'answerEvidenceBindingCount': answerEvidenceBindingCount,
      'processHeaderText': processHeaderText,
      'templateVersionUsed': templateVersionUsed,
      'phaseOneRoutingDiagnostics': phaseOneRoutingDiagnostics,
      'timelinePhases': timelinePhases,
      'journalStages': journalStages,
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
    final displayMarkdown =
        (message['displayMarkdown'] as String?)?.trim() ?? '';
    if (displayMarkdown.isNotEmpty) return displayMarkdown;
    final content = (message['content'] as String?)?.trim() ?? '';
    if (content.isNotEmpty) return content;
    final streamed = (message['streamFinalAnswer'] as String?)?.trim() ?? '';
    if (streamed.isNotEmpty) return streamed;
    final visible = bubbleText.trim();
    if (visible.isNotEmpty) return visible;
    return '';
  }

  bool get degraded => message['degraded'] == true;

  bool get heuristicFallbackUsed =>
      message['heuristicFallbackUsed'] == true ||
      (((message['qualityMetrics'] as Map?)
              ?.cast<String, dynamic>())?['heuristicFallbackUsed']) ==
          true;

  bool get streaming => message['streaming'] == true;

  int get modelCallCount =>
      (((message['uiUsageStats'] as Map?) ??
                  (message['uiUsageStatsV1'] as Map?))
              ?.cast<String, dynamic>())?['modelCallCount']
          is num
      ? (((message['uiUsageStats'] as Map?) ??
                        (message['uiUsageStatsV1'] as Map?))!
                    .cast<String, dynamic>()['modelCallCount']
                as num)
            .toInt()
      : 0;

  String get templateVersionUsed =>
      (message['templateVersionUsed'] as String?)?.trim() ?? '';

  Map<String, dynamic> get phaseOneRoutingDiagnostics =>
      (message['phaseOneRoutingDiagnostics'] as Map?)
          ?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  String get nextAction {
    final answerDecision =
        ((message['runArtifacts'] as Map?)?['answerDecision'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return (answerDecision['nextAction'] as String?)?.trim() ?? '';
  }

  String get finalAnswerMode {
    final answerDecision =
        ((message['runArtifacts'] as Map?)?['answerDecision'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final mode = (answerDecision['finalAnswerMode'] as String?)?.trim() ?? '';
    if (mode.isNotEmpty) return mode;
    final aggregation =
        (message['aggregationState'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return (aggregation['finalAnswerMode'] as String?)?.trim() ?? '';
  }

  List<String> get timelinePhaseIds {
    final raw =
        ((message['uiProcessTimeline'] as List?) ??
                (message['uiProcessTimelineV2'] as List?))
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    return _uniqueNonEmpty(
      raw.map(
        (item) =>
            (item['phaseId'] as String?)?.trim() ??
            (item['stage'] as String?)?.trim() ??
            '',
      ),
    );
  }

  List<String> get journalStages {
    final raw =
        (((message['runArtifacts'] as Map?)?['processJournal'] as List?) ??
                (message['processJournalV1'] as List?))
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    return _uniqueNonEmpty(
      raw.map(
        (item) => (item['stage'] as String?)?.trim().isNotEmpty == true
            ? (item['stage'] as String).trim()
            : (item['phaseId'] as String?)?.trim() ?? '',
      ),
    );
  }

  int get expandSignalCount {
    final raw =
        (((message['runArtifacts'] as Map?)?['processJournal'] as List?) ??
                (message['processJournalV1'] as List?))
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    var count = 0;
    for (final item in raw) {
      final stage = (item['stage'] as String?)?.trim() ?? '';
      final phaseId = (item['phaseId'] as String?)?.trim() ?? '';
      final actionCode = (item['actionCode'] as String?)?.trim() ?? '';
      final reasonCode = (item['reasonCode'] as String?)?.trim() ?? '';
      if (stage == 'expanding' ||
          phaseId == 'expanding' ||
          actionCode == 'expand_search' ||
          reasonCode == 'need_more_search' ||
          reasonCode == 'need_more_evidence') {
        count += 1;
      }
    }
    return count;
  }

  int get evidenceLedgerCount {
    final raw =
        (((message['runArtifacts'] as Map?)?['evidenceLedger'] as List?) ??
                const <dynamic>[])
            .whereType<Map>()
            .length;
    return raw;
  }

  int get answerEvidenceBindingCount {
    final raw =
        (((message['runArtifacts'] as Map?)?['answerEvidenceBindings']
                    as List?) ??
                const <dynamic>[])
            .whereType<Map>()
            .length;
    return raw;
  }
}

List<String> _uniqueNonEmpty(Iterable<String> values) {
  final seen = <String>{};
  final out = <String>[];
  for (final raw in values) {
    final value = raw.trim();
    if (value.isEmpty || !seen.add(value)) continue;
    out.add(value);
  }
  return out;
}
