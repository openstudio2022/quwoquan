library;

import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_plan_view.dart';
import 'package:quwoquan_app/assistant/contracts/retrieval_outcome.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/search_plan_contract.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';
import 'package:quwoquan_app/assistant/contracts/understanding_result_contract.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/persistence/assistant_storage_path.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/components/assistant/petal_mark.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/main.dart' as app;
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_message_bubble.dart';

import 'support/assistant_replay_baseline.dart';

const _defaultFirstQuery = '如果把九寨沟方向考虑进去，多给我几个备选方案';
const _defaultSecondQuery = '如果我只有4天，优先哪条路线？';
const _firstQuery = String.fromEnvironment(
  'ASSISTANT_REPLAY_FIRST_QUERY',
  defaultValue: _defaultFirstQuery,
);
const _secondQuery = String.fromEnvironment(
  'ASSISTANT_REPLAY_SECOND_QUERY',
  defaultValue: _defaultSecondQuery,
);
const _temporalReplayCaseFilter = String.fromEnvironment(
  'ASSISTANT_TEMPORAL_CASE_FILTER',
  defaultValue: '',
);
const _replayCaseFilter = String.fromEnvironment(
  'ASSISTANT_REPLAY_CASE_FILTER',
  defaultValue: '',
);
const _replayRepeatCount = int.fromEnvironment(
  'ASSISTANT_REPLAY_REPEAT_COUNT',
  defaultValue: 3,
);
const _enableLegacyReplayCases = bool.fromEnvironment(
  'ASSISTANT_ENABLE_LEGACY_REPLAY_CASES',
  defaultValue: false,
);
const _knownFailureClasses = <String>[
  'none',
  'degraded_fail_closed',
  'heuristic_fallback_used',
  'tool_progress_as_answer',
  'internal_protocol_leak',
  'generic_fallback_answer',
  'empty_final_answer',
  'missing_query_design',
  'weak_evidence_answered',
  'next_action_not_answer',
  'final_answer_not_ready',
  'timeline_not_canonical',
  'reload_state_lost',
  'exception',
];
const _weatherFirstQuery = '深圳今天天气怎么样？需要带外套吗？';
const _weatherSecondQuery = '明天会下雨吗，要带伞还是外套？';
const _canonicalVisibleReplayTimeline = <String>[
  'understanding',
  'retrieval_design',
  'retrieval_processing',
];
const _m0ReplayCases = <_M0ReplayCase>[
  _M0ReplayCase(
    caseId: 'yesterday_stock_reason',
    turnShape: _M0ReplayTurnShape.singleTurn,
    expectedScope: 'stock_reason',
    expectedTemporalAnchor: 'explicit_date_from_yesterday',
    expectedOutcomeClass: 'answer_ready',
    turns: <_M0ReplayTurnSpec>[
      _M0ReplayTurnSpec(
        turnId: 'turn_1',
        query: '昨天股票为什么大涨',
        expectedScope: 'stock_reason',
        expectedOutcomeClass: 'answer_ready',
        temporalExpectation: _M0TemporalExpectation.yesterday,
      ),
    ],
  ),
  _M0ReplayCase(
    caseId: 'followup_a_stock_reason',
    turnShape: _M0ReplayTurnShape.followup,
    expectedScope: 'stock_reason',
    expectedTemporalAnchor: 'followup_after_explicit_yesterday_anchor',
    expectedOutcomeClass: 'answer_ready',
    turns: <_M0ReplayTurnSpec>[
      _M0ReplayTurnSpec(
        turnId: 'turn_1',
        query: '昨天股票为什么大涨',
        expectedScope: 'stock_reason',
        expectedOutcomeClass: 'answer_ready',
        temporalExpectation: _M0TemporalExpectation.yesterday,
      ),
      _M0ReplayTurnSpec(
        turnId: 'turn_2',
        query: 'a股大涨原因是什么',
        expectedScope: 'stock_reason',
        expectedOutcomeClass: 'answer_ready',
        temporalExpectation: _M0TemporalExpectation.none,
      ),
    ],
  ),
  _M0ReplayCase(
    caseId: 'yesterday_a_stock_reason',
    turnShape: _M0ReplayTurnShape.singleTurn,
    expectedScope: 'stock_reason',
    expectedTemporalAnchor: 'explicit_date_from_yesterday',
    expectedOutcomeClass: 'answer_ready',
    turns: <_M0ReplayTurnSpec>[
      _M0ReplayTurnSpec(
        turnId: 'turn_1',
        query: '昨天A股为什么大涨',
        expectedScope: 'stock_reason',
        expectedOutcomeClass: 'answer_ready',
        temporalExpectation: _M0TemporalExpectation.yesterday,
      ),
    ],
  ),
  _M0ReplayCase(
    caseId: 'wednesday_a_stock_reason',
    turnShape: _M0ReplayTurnShape.singleTurn,
    expectedScope: 'stock_reason',
    expectedTemporalAnchor: 'explicit_calendar_anchor_from_weekday',
    expectedOutcomeClass: 'answer_ready',
    turns: <_M0ReplayTurnSpec>[
      _M0ReplayTurnSpec(
        turnId: 'turn_1',
        query: '周三A股为什么大涨',
        expectedScope: 'stock_reason',
        expectedOutcomeClass: 'answer_ready',
        temporalExpectation: _M0TemporalExpectation.weekday,
      ),
    ],
  ),
  _M0ReplayCase(
    caseId: 'tomorrow_weather',
    turnShape: _M0ReplayTurnShape.singleTurn,
    expectedScope: 'weather_forecast',
    expectedTemporalAnchor: 'explicit_date_from_tomorrow',
    expectedOutcomeClass: 'answer_ready',
    turns: <_M0ReplayTurnSpec>[
      _M0ReplayTurnSpec(
        turnId: 'turn_1',
        query: '明天天气怎么样？需要带外套吗？',
        expectedScope: 'weather_forecast',
        expectedOutcomeClass: 'answer_ready',
        temporalExpectation: _M0TemporalExpectation.tomorrow,
      ),
    ],
  ),
  _M0ReplayCase(
    caseId: 'cold_start_reload',
    turnShape: _M0ReplayTurnShape.coldStartReload,
    expectedScope: 'weather_forecast',
    expectedTemporalAnchor: 'explicit_date_from_tomorrow',
    expectedOutcomeClass: 'reload_recovered',
    turns: <_M0ReplayTurnSpec>[
      _M0ReplayTurnSpec(
        turnId: 'seed_turn',
        query: '明天天气怎么样？需要带外套吗？',
        expectedScope: 'weather_forecast',
        expectedOutcomeClass: 'answer_ready',
        temporalExpectation: _M0TemporalExpectation.tomorrow,
      ),
    ],
  ),
];
const _temporalReplayCases = <_TemporalReplayCase>[
  _TemporalReplayCase(
    caseName: 'last_wednesday_stock',
    query: '上周三A股为什么大涨',
    kind: _TemporalReplayExpectationKind.lastWednesday,
  ),
  _TemporalReplayCase(
    caseName: 'next_wednesday_weather',
    query: '下周三深圳天气怎么样？要带外套吗？',
    kind: _TemporalReplayExpectationKind.nextWednesday,
  ),
  _TemporalReplayCase(
    caseName: 'day_after_tomorrow_weather',
    query: '深圳后天天气怎么样，要带伞还是外套？',
    kind: _TemporalReplayExpectationKind.dayAfterTomorrow,
  ),
  _TemporalReplayCase(
    caseName: 'recent_market_window',
    query: '最近股市走向怎么样？',
    kind: _TemporalReplayExpectationKind.recentWindow,
  ),
  _TemporalReplayCase(
    caseName: 'future_market_forecast',
    query: '结合最近股市走向及国际经济形势，预测下未来股市走向',
    kind: _TemporalReplayExpectationKind.futureForecast,
  ),
];
const _skeletalProcessHeaders = <String>[
  '理解问题',
  '结果处理',
  '整理答案',
  '已完成处理',
  '正在搜索',
  '正在整理',
  '正在回答',
];

const _forbiddenFragments = <String>[
  'assistant_turn',
  'contractId',
  'query'
      'Tasks',
  'searchPlans',
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
  'MissingPluginException',
  'personalassistant/nativeapi',
  'Local context failed',
  'Unsupported content type',
  'application/pdf',
  '这个操作我暂时还没拿到可展示结果',
  '本次任务已完成，但没有生成可展示结果',
];
const MethodChannel _nativeApiChannel = MethodChannel(
  'personal_assistant/native_api',
);
const Map<String, dynamic> _replayLocalContext = <String, dynamic>{
  'city': '深圳',
  'currentCity': '深圳',
  'locationSource': 'integration_test',
  'timezone': 'Asia/Shanghai',
  'locale': 'zh_CN',
  'location': <String, dynamic>{
    'city': '深圳',
    'latitude': 22.5431,
    'longitude': 114.0579,
    'accuracyM': 1200,
    'source': 'integration_test',
  },
  'permissions': <String, dynamic>{
    'location': true,
    'photos': false,
    'camera': false,
    'notification': false,
  },
  'device': <String, dynamic>{
    'os': 'iOS',
    'model': 'iPhone Simulator',
    'locale': 'zh_CN',
    'timezone': 'Asia/Shanghai',
  },
};

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(_nativeApiChannel, (call) async {
        switch (call.method) {
          case 'getLocalContext':
            return _replayLocalContext;
          default:
            return <String, dynamic>{'error': 'unsupported_test_method'};
        }
      });

  testWidgets(
    'Assistant M0 replay baseline',
    (tester) async {
      await _runM0ReplayBaseline(tester, binding: binding);
    },
    timeout: Timeout(Duration(minutes: _m0ReplayBaselineTimeoutMinutes())),
  );

  if (_enableLegacyReplayCases) {
    testWidgets('助理回放与天气问答回归', (tester) async {
      await _runReplayCase(
        tester,
        binding: binding,
        caseName: 'manual_replay',
        firstQuery: _firstQuery,
        secondQuery: _secondQuery,
      );
      await _runReplayCase(
        tester,
        binding: binding,
        caseName: 'weather_replay',
        firstQuery: _weatherFirstQuery,
        secondQuery: _weatherSecondQuery,
      );
    }, timeout: const Timeout(Duration(minutes: 20)));

    testWidgets('时间锚点真实回放回归', (tester) async {
      for (final replayCase in _selectedTemporalReplayCases()) {
        await _runSingleQueryReplayCase(
          tester,
          binding: binding,
          replayCase: replayCase,
        );
      }
    }, timeout: const Timeout(Duration(minutes: 20)));

    testWidgets(
      '冷启动 reload 后仍恢复最后一条 assistant canonical state',
      (tester) async {
        await _runColdStartReloadCase(tester, binding: binding);
      },
      timeout: const Timeout(Duration(minutes: 20)),
    );
  }
}

int _m0ReplayBaselineTimeoutMinutes() {
  final selectedCaseCount = _selectedM0ReplayCases().length;
  final estimatedMinutes = 6 + (selectedCaseCount * _replayRepeatCount * 3);
  if (estimatedMinutes < 20) return 20;
  if (estimatedMinutes > 60) return 60;
  return estimatedMinutes;
}

Future<void> _runM0ReplayBaseline(
  WidgetTester tester, {
  required IntegrationTestWidgetsFlutterBinding binding,
}) async {
  final selectedCases = _selectedM0ReplayCases();
  final caseReports = <String, dynamic>{};
  final caseGateResults = <String, bool>{};
  final packs = <AssistantReplayBaselinePack>[];
  final blockingMessages = <String>[];
  for (final replayCase in selectedCases) {
    final pack = await _runM0BaselineCase(tester, replayCase: replayCase);
    final artifactPath = await writeAssistantReplayBaselinePack(pack);
    packs.add(pack);
    caseGateResults[replayCase.caseId] = pack.m1Entry.eligible;
    caseReports[replayCase.caseId] = <String, dynamic>{
      'artifactPath': artifactPath,
      'pack': pack.toJson(),
      'm1Entry': pack.m1Entry.toJson(),
      'stability': pack.stability.toJson(),
      'attemptOutcomeClasses': pack.attempts
          .map((item) => item.outcomeClass)
          .toList(growable: false),
      'attemptFailureClasses': pack.attempts
          .map((item) => item.failureClass)
          .toList(growable: false),
    };
    if (!pack.m1Entry.eligible) {
      blockingMessages.add(
        '${replayCase.caseId}: ${_summarizePackBlocking(pack)} | $artifactPath',
      );
    }
  }
  final corpusEntry = _buildM0CorpusM1Entry(
    packs: packs,
    selectedCases: selectedCases,
  );
  final indexPayload = <String, dynamic>{
    'schemaVersion': assistantReplayM0BaselinePackVersion,
    'generatedAt': DateTime.now().toIso8601String(),
    'repeatCount': _replayRepeatCount,
    'selectedCaseIds': selectedCases
        .map((item) => item.caseId)
        .toList(growable: false),
    'knownFailureClasses': _knownFailureClasses,
    'caseGateResults': caseGateResults,
    'cases': caseReports,
    'm1Entry': corpusEntry.toJson(),
  };
  final indexPath = await writeAssistantReplayBaselineIndex(
    fileName: 'assistant_m0_index.json',
    payload: indexPayload,
  );
  final existingReportData = switch (binding.reportData) {
    final Map<Object?, Object?> map => map.map(
      (key, value) => MapEntry(key.toString(), value),
    ),
    _ => <String, dynamic>{},
  };
  binding.reportData = <String, dynamic>{
    ...existingReportData,
    'assistant_m0_baseline': <String, dynamic>{
      ...indexPayload,
      'artifactPath': indexPath,
    },
  };
  if (!corpusEntry.eligible) {
    fail(
      'Assistant M0 replay baseline 未准出。\n'
      '索引: $indexPath\n'
      '${blockingMessages.join('\n')}',
    );
  }
}

String _summarizePackBlocking(AssistantReplayBaselinePack pack) {
  final attemptSummaries = pack.attempts
      .map(
        (attempt) =>
            'attempt${attempt.attemptIndex}'
            '[outcome=${attempt.outcomeClass}, failure=${attempt.failureClass}, issues=${attempt.issues.join(',')}]',
      )
      .join(' ; ');
  final blocking = pack.m1Entry.blockingReasons.join('；');
  final fieldDiffs = pack.stability.fieldDiffs.isEmpty
      ? ''
      : ' | fieldDiffs=${pack.stability.fieldDiffs}';
  return '$blocking | $attemptSummaries$fieldDiffs';
}

List<_M0ReplayCase> _selectedM0ReplayCases() {
  final filterValues = <String>{
    ..._splitCaseFilter(_replayCaseFilter),
    ..._splitCaseFilter(_temporalReplayCaseFilter),
  };
  if (filterValues.isEmpty) {
    return _m0ReplayCases;
  }
  return _m0ReplayCases
      .where((item) => filterValues.contains(item.caseId))
      .toList(growable: false);
}

Set<String> _splitCaseFilter(String raw) {
  return raw
      .split(',')
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .toSet();
}

Future<AssistantReplayBaselinePack> _runM0BaselineCase(
  WidgetTester tester, {
  required _M0ReplayCase replayCase,
}) async {
  final attempts = <AssistantReplayBaselineAttempt>[];
  for (var i = 0; i < _replayRepeatCount; i++) {
    final attempt = replayCase.turnShape == _M0ReplayTurnShape.coldStartReload
        ? await _runM0ReloadAttempt(
            tester,
            replayCase: replayCase,
            attemptIndex: i + 1,
          )
        : await _runM0StandardAttempt(
            tester,
            replayCase: replayCase,
            attemptIndex: i + 1,
          );
    attempts.add(attempt);
  }
  final stability = _buildM0Stability(attempts);
  final m1Entry = _buildM0CaseM1Entry(
    replayCase: replayCase,
    attempts: attempts,
    stability: stability,
  );
  return AssistantReplayBaselinePack(
    caseId: replayCase.caseId,
    turnShape: replayCase.turnShape.name,
    expectedScope: replayCase.expectedScope,
    expectedTemporalAnchor: replayCase.expectedTemporalAnchor,
    expectedOutcomeClass: replayCase.expectedOutcomeClass,
    repeatCount: _replayRepeatCount,
    knownFailureClasses: _knownFailureClasses,
    attempts: attempts,
    stability: stability,
    m1Entry: m1Entry,
    generatedAt: DateTime.now().toIso8601String(),
    softEvidence: const <String, dynamic>{
      'visualReviewMode': 'text_snapshot_only',
      'screenshotGate': 'soft_evidence_only',
    },
  );
}

Future<AssistantReplayBaselineAttempt> _runM0StandardAttempt(
  WidgetTester tester, {
  required _M0ReplayCase replayCase,
  required int attemptIndex,
}) async {
  final originalOnError = FlutterError.onError;
  final referenceNow = DateTime.now();
  final turns = <AssistantReplayBaselineTurn>[];
  final issues = <String>[];
  try {
    await _resetAssistantApp(tester);
    await _wipeAssistantStorage();
    _suppressNetworkImageErrors();
    app.main();

    await _waitForMainEntry(tester);
    await _openAssistantConversation(tester);
    await _waitForChatInput(tester);

    for (final turn in replayCase.turns) {
      final result = await _sendQueryWithSingleRetry(
        tester,
        query: turn.query,
        expectedScope: turn.expectedScope,
      );
      final snapshot = _latestAssistantSnapshot(tester);
      final artifact = await _buildM0TurnArtifact(
        result: result,
        snapshot: snapshot,
        turn: turn,
        referenceNow: referenceNow,
      );
      turns.add(artifact);
      issues.addAll(artifact.issues.map((item) => '${turn.turnId}: $item'));
      if (artifact.issues.isNotEmpty) {
        final snapshotDiag = snapshot == null
            ? const <String, dynamic>{}
            : <String, dynamic>{
                'messageId': snapshot.messageId,
                'runId': snapshot.runId,
                'traceId': snapshot.traceId,
                'answerText': snapshot.answerText,
                'bubbleText': snapshot.bubbleText,
                'streaming': snapshot.streaming,
                'finalAnswerReady': snapshot.finalAnswerReady,
                'nextAction': snapshot.nextAction,
                'finalAnswerMode': snapshot.finalAnswerMode,
                'timelinePhaseIds': snapshot.timelinePhaseIds,
                'journalStages': snapshot.journalStages,
                'canonicalProcessSteps': snapshot.canonicalProcessSteps,
                'queryDesignLines': snapshot.queryDesignLines,
              };
        debugPrint(
          'M0_REPLAY_DIAG case=${replayCase.caseId} turn=${turn.turnId} '
          'result=${result.toJson()} '
          'snapshot=$snapshotDiag '
          'artifact=${artifact.toJson()}',
        );
      }
    }
  } catch (error) {
    issues.add('exception: $error');
  } finally {
    FlutterError.onError = originalOnError;
    await _resetAssistantApp(tester);
  }
  final failureClass = _resolveAttemptFailureClass(
    turns: turns,
    issues: issues,
  );
  final outcomeClass = _resolveAttemptOutcomeClass(
    replayCase: replayCase,
    turns: turns,
    failureClass: failureClass,
  );
  final finalTurn = turns.isEmpty ? null : turns.last;
  debugPrint(
    'M0_REPLAY_ATTEMPT case=${replayCase.caseId} '
    'attempt=$attemptIndex '
    'outcome=$outcomeClass '
    'failure=$failureClass '
    'nextAction=${(finalTurn?.report['nextAction'] as String?)?.trim() ?? ''} '
    'finalAnswerReady=${finalTurn?.finalAnswerReady ?? false} '
    'queryDesignSignature=${_stableQueryDesignSignature(finalTurn?.queryDesignLines ?? const <String>[])}',
  );
  return AssistantReplayBaselineAttempt(
    attemptIndex: attemptIndex,
    outcomeClass: outcomeClass,
    failureClass: failureClass,
    gatePassed:
        issues.isEmpty &&
        failureClass == 'none' &&
        outcomeClass == replayCase.expectedOutcomeClass,
    issues: issues,
    turns: turns,
    details: <String, dynamic>{
      'referenceNow': referenceNow.toIso8601String(),
      'turnCount': turns.length,
    },
  );
}

Future<AssistantReplayBaselineAttempt> _runM0ReloadAttempt(
  WidgetTester tester, {
  required _M0ReplayCase replayCase,
  required int attemptIndex,
}) async {
  final originalOnError = FlutterError.onError;
  final referenceNow = DateTime.now();
  final turns = <AssistantReplayBaselineTurn>[];
  final issues = <String>[];
  Map<String, dynamic> beforeReload = const <String, dynamic>{};
  Map<String, dynamic> afterReload = const <String, dynamic>{};
  try {
    await _resetAssistantApp(tester);
    await _wipeAssistantStorage();
    _suppressNetworkImageErrors();
    app.main();

    await _waitForMainEntry(tester);
    await _openAssistantConversation(tester);
    await _waitForChatInput(tester);

    final seedTurn = replayCase.turns.first;
    final result = await _sendQueryWithSingleRetry(
      tester,
      query: seedTurn.query,
      expectedScope: seedTurn.expectedScope,
    );
    final seedSnapshot = _latestAssistantSnapshot(tester);
    final seedArtifact = await _buildM0TurnArtifact(
      result: result,
      snapshot: seedSnapshot,
      turn: seedTurn,
      referenceNow: referenceNow,
    );
    turns.add(seedArtifact);
    issues.addAll(
      seedArtifact.issues.map((item) => '${seedTurn.turnId}: $item'),
    );
    beforeReload = _reloadStateFromSnapshot(seedSnapshot);

    await _resetAssistantApp(tester);
    app.main();

    await _waitForMainEntry(tester);
    await _openAssistantConversation(tester);
    await _waitForChatInput(tester);
    await _pumpUntil(
      tester,
      condition: () {
        final snapshot = _latestAssistantSnapshot(tester);
        return snapshot != null && snapshot.answerText.trim().isNotEmpty;
      },
      timeout: const Duration(seconds: 20),
    );
    final recoveredSnapshot = _latestAssistantSnapshot(tester);
    afterReload = _reloadStateFromSnapshot(recoveredSnapshot);
    final reloadIssues = _collectReloadIssues(
      beforeReload: beforeReload,
      afterReload: afterReload,
    );
    if (reloadIssues.isNotEmpty) {
      debugPrint(
        'M0_RELOAD_DIAG case=${replayCase.caseId} '
        'attempt=$attemptIndex '
        'before=$beforeReload '
        'after=$afterReload '
        'issues=$reloadIssues',
      );
    }
    issues.addAll(reloadIssues);
  } catch (error) {
    issues.add('exception: $error');
  } finally {
    FlutterError.onError = originalOnError;
    await _resetAssistantApp(tester);
  }
  final failureClass = issues.any((item) => item.startsWith('reload_'))
      ? 'reload_state_lost'
      : _resolveAttemptFailureClass(turns: turns, issues: issues);
  final outcomeClass = failureClass == 'none' && issues.isEmpty
      ? 'reload_recovered'
      : 'reload_state_lost';
  return AssistantReplayBaselineAttempt(
    attemptIndex: attemptIndex,
    outcomeClass: outcomeClass,
    failureClass: failureClass,
    gatePassed:
        issues.isEmpty &&
        failureClass == 'none' &&
        outcomeClass == replayCase.expectedOutcomeClass,
    issues: issues,
    turns: turns,
    details: <String, dynamic>{
      'referenceNow': referenceNow.toIso8601String(),
      'beforeReload': beforeReload,
      'afterReload': afterReload,
    },
  );
}

Future<AssistantReplayBaselineTurn> _buildM0TurnArtifact({
  required _ReplayResult result,
  required _AssistantBubbleSnapshot? snapshot,
  required _M0ReplayTurnSpec turn,
  required DateTime referenceNow,
}) async {
  final queryDesignLines =
      snapshot?.queryDesignLines ?? result.queryDesignLines;
  final issues = <String>[
    ..._collectReplayGateIssues(result),
    ..._collectTurnScopeIssues(
      result: result,
      turn: turn,
      queryDesignLines: queryDesignLines,
    ),
    ..._collectTemporalAnchorIssues(
      result: result,
      turn: turn,
      referenceNow: referenceNow,
    ),
  ];
  final finalAnswerReady =
      (snapshot?.finalAnswerReady ?? false) ||
      _replayResultSignalsReady(result);
  if (!finalAnswerReady) {
    issues.add('final_answer_not_ready');
  }
  final runId = snapshot?.runId ?? '';
  final traceId = snapshot?.traceId ?? '';
  final messageId = snapshot?.messageId ?? '';
  final runLogPath = await resolveAssistantRunLogPath(runId) ?? '';
  final runLog = await loadAssistantRunLog(runLogPath);
  final replayRecord = runLogPath.isEmpty
      ? null
      : await buildAssistantReplayRecordFromRunLog(
          messageId: messageId,
          query: turn.query,
          answerText: snapshot?.answerText ?? result.finalAnswerText,
          displayPlainText: snapshot?.answerText ?? result.finalAnswerText,
          runLogPath: runLogPath,
        );
  final canonicalState = snapshot == null
      ? const <String, dynamic>{}
      : _buildCanonicalBaselineState(snapshot);
  if (runLogPath.isEmpty) {
    issues.add('missing_run_log_path');
  }
  if (canonicalState.isEmpty) {
    issues.add('missing_canonical_state');
  }
  final failureClass = _resolveTurnFailureClass(result: result, issues: issues);
  final outcomeClass = _resolveTurnOutcomeClass(
    failureClass: failureClass,
    finalAnswerReady: finalAnswerReady,
  );
  return AssistantReplayBaselineTurn(
    turnId: turn.turnId,
    query: turn.query,
    runId: runId,
    traceId: traceId,
    runLogPath: runLogPath,
    expectedOutcomeClass: turn.expectedOutcomeClass,
    outcomeClass: outcomeClass,
    failureClass: failureClass,
    gatePassed:
        issues.isEmpty &&
        failureClass == 'none' &&
        finalAnswerReady &&
        outcomeClass == turn.expectedOutcomeClass,
    finalAnswerReady: finalAnswerReady,
    issues: issues,
    queryDesignLines: queryDesignLines,
    report: <String, dynamic>{
      ...result.toJson(),
      'messageId': messageId,
      'runId': runId,
      'traceId': traceId,
      'finalAnswerReady': finalAnswerReady,
    },
    canonicalState: canonicalState,
    runLogMeta: _extractRunLogMeta(runLog),
    replayRecord: replayRecord?.toJson() ?? const <String, dynamic>{},
  );
}

List<String> _collectReplayGateIssues(_ReplayResult result) {
  final issues = <String>[];
  if (!result.phaseLabelSeen) {
    issues.add('missing_process_header');
  }
  if (result.degraded) {
    issues.add('degraded_fail_closed');
  }
  if (result.heuristicFallbackUsed) {
    issues.add('heuristic_fallback_used');
  }
  if (result.finalAnswerText.trim().isEmpty) {
    issues.add('empty_final_answer');
  }
  if (_isGenericAssistantFallback(result.finalAnswerText)) {
    issues.add('generic_fallback_answer');
  }
  if (AssistantContentFilters.isProgressPlaceholder(result.finalAnswerText) ||
      AssistantContentFilters.isProgressPlaceholder(result.finalVisibleText)) {
    issues.add('tool_progress_as_answer');
  }
  if (result.finalMessageStreaming) {
    issues.add('final_message_still_streaming');
  }
  if (_containsInternalProtocolLeak(result.finalAnswerText)) {
    issues.add('internal_protocol_answer');
  }
  if (_containsInternalProtocolLeak(result.finalVisibleText)) {
    issues.add('internal_protocol_visible');
  }
  if (!_isCompletedProcessHeader(result.processHeaderText)) {
    issues.add('process_header_not_completed');
  }
  if (!result.matchedExpected) {
    issues.add('answer_missing_expected_anchor');
  }
  if (_completedHeaderHasDocumentCount(result.processHeaderText) &&
      result.evidenceLedgerCount <= 0) {
    issues.add('missing_evidence_ledger');
  }
  if (_completedHeaderHasDocumentCount(result.processHeaderText) &&
      result.answerEvidenceBindingCount <= 0) {
    issues.add('missing_answer_evidence_binding');
  }
  if (result.nextAction != 'answer') {
    issues.add('next_action_not_answer');
  }
  if (!_hasCanonicalVisibleReplayTimeline(result.timelinePhases)) {
    issues.add('timeline_phases_not_canonical');
  }
  if (!_hasCanonicalVisibleReplayTimeline(result.journalStages)) {
    issues.add('journal_stages_not_canonical');
  }
  if (result.finalAnswerMode != 'full' &&
      result.finalAnswerMode != 'bounded_answer') {
    issues.add('unexpected_final_answer_mode');
  }
  return issues;
}

List<String> _collectTurnScopeIssues({
  required _ReplayResult result,
  required _M0ReplayTurnSpec turn,
  required List<String> queryDesignLines,
}) {
  final issues = <String>[];
  if (queryDesignLines.isEmpty && result.structuredTaskToolNames.isEmpty) {
    issues.add('missing_query_design');
  }
  switch (turn.expectedScope) {
    case 'stock_reason':
      if (!_hasStructuredScopeMatch(result, turn.expectedScope)) {
        issues.add('scope_answer_not_stock_reason');
      }
      break;
    case 'weather_forecast':
      if (!_hasStructuredScopeMatch(result, turn.expectedScope)) {
        issues.add('scope_answer_not_weather');
      }
      if (!_hasReplayStructuredGeoScope(result.structuredResolvedGeoScope) &&
          !_hasStructuredLocationEntity(result)) {
        issues.add('resolved_geo_scope_missing');
      }
      break;
  }
  return issues;
}

bool _hasStructuredLocationEntity(_ReplayResult result) {
  final entityTypes = result.structuredEntityTypes
      .map((item) => item.trim().toLowerCase())
      .toSet();
  if (!entityTypes.contains('location') &&
      !entityTypes.contains('geo') &&
      !entityTypes.contains('place') &&
      !entityTypes.contains('city') &&
      !entityTypes.contains('admin_area')) {
    return false;
  }
  return result.structuredEntityKeys.any((item) => item.trim().isNotEmpty);
}

bool _hasStructuredScopeMatch(_ReplayResult result, String expectedScope) {
  final scopeTokens = <String>{
    ...result.structuredIntentTypes,
    ...result.structuredEntityTypes,
    ...result.structuredEntityKeys,
    ...result.structuredTaskToolNames,
    ...result.structuredTaskIntentIds,
  }.map((item) => item.trim().toLowerCase()).where((item) => item.isNotEmpty);
  switch (expectedScope) {
    case 'weather_forecast':
      return scopeTokens.any(
        (item) =>
            item == 'weather' ||
            item.startsWith('weather.') ||
            item.contains('weather_forecast'),
      );
    case 'stock_reason':
      return scopeTokens.any(
        (item) =>
            item == 'finance' ||
            item.startsWith('finance.') ||
            item == 'stock' ||
            item.startsWith('stock.') ||
            item.contains('stock_reason') ||
            item.contains('market'),
      );
    default:
      return true;
  }
}

List<String> _collectTemporalAnchorIssues({
  required _ReplayResult result,
  required _M0ReplayTurnSpec turn,
  required DateTime referenceNow,
}) {
  if (turn.temporalExpectation == _M0TemporalExpectation.none) {
    return const <String>[];
  }
  final issues = <String>[];
  switch (turn.temporalExpectation) {
    case _M0TemporalExpectation.yesterday:
      final targetDate = _startOfDay(
        referenceNow,
      ).subtract(const Duration(days: 1));
      if (!_structuredTemporalAnchorsContainDate(
        result.structuredTemporalAnchors,
        targetDate,
      )) {
        issues.add('query_design_missing_explicit_date');
      }
      return issues;
    case _M0TemporalExpectation.tomorrow:
      final targetDate = _startOfDay(referenceNow).add(const Duration(days: 1));
      if (!_structuredTemporalAnchorsContainDate(
        result.structuredTemporalAnchors,
        targetDate,
      )) {
        issues.add('query_design_missing_explicit_date');
      }
      return issues;
    case _M0TemporalExpectation.weekday:
      if (!_hasStructuredCalendarAnchor(result.structuredTemporalAnchors)) {
        issues.add('query_design_missing_calendar_anchor');
      }
      return issues;
    case _M0TemporalExpectation.none:
      return issues;
  }
}

String _resolveTurnFailureClass({
  required _ReplayResult result,
  required List<String> issues,
}) {
  if (issues.any((item) => item.startsWith('exception'))) {
    return 'exception';
  }
  if (result.degraded) {
    return 'degraded_fail_closed';
  }
  if (result.heuristicFallbackUsed) {
    return 'heuristic_fallback_used';
  }
  if (AssistantContentFilters.isProgressPlaceholder(result.finalAnswerText) ||
      AssistantContentFilters.isProgressPlaceholder(result.finalVisibleText)) {
    return 'tool_progress_as_answer';
  }
  if (_containsInternalProtocolLeak(result.finalAnswerText) ||
      _containsInternalProtocolLeak(result.finalVisibleText)) {
    return 'internal_protocol_leak';
  }
  if (result.finalAnswerText.trim().isEmpty) {
    return 'empty_final_answer';
  }
  if (_isGenericAssistantFallback(result.finalAnswerText)) {
    return 'generic_fallback_answer';
  }
  if (issues.contains('missing_query_design') ||
      issues.any((item) => item.startsWith('query_design_'))) {
    return 'missing_query_design';
  }
  if (issues.contains('next_action_not_answer')) {
    return 'next_action_not_answer';
  }
  if (issues.contains('final_answer_not_ready')) {
    return 'final_answer_not_ready';
  }
  if (issues.contains('timeline_phases_not_canonical') ||
      issues.contains('journal_stages_not_canonical')) {
    return 'timeline_not_canonical';
  }
  if (issues.contains('answer_missing_expected_anchor') ||
      issues.contains('missing_evidence_ledger') ||
      issues.contains('missing_answer_evidence_binding') ||
      issues.any((item) => item.startsWith('scope_answer_not_')) ||
      issues.any((item) => item.startsWith('visible_text_missing_')) ||
      issues.any((item) => item.startsWith('final_answer_missing_'))) {
    return 'weak_evidence_answered';
  }
  return 'none';
}

String _resolveTurnOutcomeClass({
  required String failureClass,
  required bool finalAnswerReady,
}) {
  if (failureClass == 'none' && finalAnswerReady) {
    return 'answer_ready';
  }
  switch (failureClass) {
    case 'weak_evidence_answered':
      return 'weak_evidence_answered';
    case 'tool_progress_as_answer':
      return 'tool_progress_as_answer';
    case 'internal_protocol_leak':
      return 'internal_protocol_leak';
    default:
      return 'answer_failed';
  }
}

String _resolveAttemptFailureClass({
  required List<AssistantReplayBaselineTurn> turns,
  required List<String> issues,
}) {
  if (issues.any((item) => item.startsWith('exception'))) {
    return 'exception';
  }
  for (final turn in turns) {
    if (turn.failureClass != 'none') {
      return turn.failureClass;
    }
  }
  return 'none';
}

String _resolveAttemptOutcomeClass({
  required _M0ReplayCase replayCase,
  required List<AssistantReplayBaselineTurn> turns,
  required String failureClass,
}) {
  if (replayCase.turnShape == _M0ReplayTurnShape.coldStartReload) {
    return failureClass == 'none' ? 'reload_recovered' : 'reload_state_lost';
  }
  if (failureClass == 'none' &&
      turns.length == replayCase.turns.length &&
      turns.every((item) => item.outcomeClass == item.expectedOutcomeClass)) {
    return replayCase.expectedOutcomeClass;
  }
  if (turns.isNotEmpty) {
    return turns.last.outcomeClass;
  }
  return 'answer_failed';
}

AssistantReplayBaselineStability _buildM0Stability(
  List<AssistantReplayBaselineAttempt> attempts,
) {
  const comparedFields = <String>[
    'outcomeClass',
    'nextAction',
    'finalAnswerReady',
    'queryDesignSignature',
  ];
  final fieldDiffs = <Map<String, dynamic>>[];
  for (final field in comparedFields) {
    final values = attempts
        .map((attempt) => _stabilityFieldValue(attempt, field))
        .toList(growable: false);
    if (values.toSet().length > 1) {
      fieldDiffs.add(<String, dynamic>{'field': field, 'values': values});
    }
  }
  return AssistantReplayBaselineStability(
    stable: attempts.isNotEmpty && fieldDiffs.isEmpty,
    repeatCount: attempts.length,
    comparedFields: comparedFields,
    fieldDiffs: fieldDiffs,
  );
}

String _stabilityFieldValue(
  AssistantReplayBaselineAttempt attempt,
  String field,
) {
  final finalTurn = attempt.turns.isEmpty ? null : attempt.turns.last;
  switch (field) {
    case 'outcomeClass':
      return attempt.outcomeClass;
    case 'nextAction':
      return (finalTurn?.report['nextAction'] as String?)?.trim() ?? '';
    case 'finalAnswerReady':
      return (finalTurn?.finalAnswerReady ?? false).toString();
    case 'queryDesignSignature':
      return _stableQueryDesignSignature(
        finalTurn?.queryDesignLines ?? const <String>[],
      );
  }
  return '';
}

String _stableQueryDesignSignature(List<String> lines) {
  final normalized =
      lines
          .map(_normalizeQueryDesignLineForStability)
          .where((item) => item.isNotEmpty)
          .toSet()
          .toList(growable: false)
        ..sort();
  return normalized.join(' | ');
}

final RegExp _stabilityExplicitDateTokenRe = RegExp(
  r'(20\d{2})[-年/](\d{1,2})(?:[-月/])(\d{1,2})(?:日)?',
);

String _normalizeQueryDesignLineForStability(String raw) {
  final canonicalDate = raw.replaceAllMapped(_stabilityExplicitDateTokenRe, (
    match,
  ) {
    final year = match.group(1) ?? '';
    final month = int.tryParse(match.group(2) ?? '')?.toString() ?? '';
    final day = int.tryParse(match.group(3) ?? '')?.toString() ?? '';
    if (year.isEmpty || month.isEmpty || day.isEmpty) {
      return match.group(0) ?? '';
    }
    return '$year年$month月$day日';
  });
  var normalized = canonicalDate
      .replaceAll(RegExp(r'^[•\-]\s*'), '')
      .replaceAll(RegExp(r'\s+'), '')
      .replaceAll(RegExp(r'[，,。；;：:、（）()【】\[\]]'), '')
      .trim();
  normalized = normalized.replaceAll(_stabilityExplicitDateTokenRe, '');
  normalized = normalized
      .replaceAll(RegExp(r'[Aa]股'), 'A股')
      .replaceAll('中国', '')
      .replaceAll('市场', '')
      .replaceAll('驱动因素', '原因')
      .replaceAll('驱动板块', '原因')
      .replaceAll('成因', '原因')
      .replaceAll('主要原因', '原因')
      .replaceAll('具体原因', '原因')
      .replaceAll('天气详情', '天气预报')
      .replaceAll('天气情况', '天气预报')
      .replaceAll('天气信息', '天气预报')
      .replaceAll('穿衣建议', '带外套建议')
      .replaceAll('外套建议', '带外套建议')
      .replaceAll('穿搭建议', '带外套建议')
      .replaceAll('是否需要带外套', '带外套')
      .replaceAll('要不要带外套', '带外套')
      .replaceAll('是否要带外套', '带外套')
      .replaceAll('是否带外套', '带外套')
      .replaceAll('需不需要带外套', '带外套')
      .replaceAll('穿衣', '带外套')
      .replaceAll(RegExp(r'(主要|具体|直接|核心|关键)'), '')
      .replaceAll(
        RegExp(r'^(了解|确认|判断|分析|梳理|聚焦|追踪|查询|检索|获取|锁定|查明|弄清楚?|搞清楚?)+'),
        '',
      )
      .replaceAll('并根据温度判断', '')
      .replaceAll('并根据气温判断', '')
      .replaceAll('并判断', '')
      .replaceAll('并得到', '')
      .replaceAll('并获得', '')
      .replaceAll('并给出', '')
      .replaceAll('预报和', '预报')
      .replaceAll('在大涨', '大涨')
      .replaceAll('的原因', '原因')
      .replaceAll('和原因', '原因')
      .replaceAll('原因原因', '原因')
      .replaceAll('的', '');
  if (_looksLikeStockJumpReasonSignature(normalized)) {
    return 'A股大涨原因';
  }
  if (_looksLikeWeatherOuterwearSignature(normalized)) {
    return '天气预报带外套建议';
  }
  return normalized.trim();
}

bool _looksLikeStockJumpReasonSignature(String normalized) {
  final compact = normalized.trim();
  if (compact.isEmpty) return false;
  final mentionsStock =
      compact.contains('A股') ||
      compact.contains('股票') ||
      compact.contains('股市');
  final mentionsJump = compact.contains('大涨');
  final mentionsReason =
      compact.contains('原因') ||
      compact.contains('驱动') ||
      compact.contains('板块');
  return mentionsStock && mentionsJump && mentionsReason;
}

bool _looksLikeWeatherOuterwearSignature(String normalized) {
  final compact = normalized.trim();
  if (compact.isEmpty) return false;
  final weatherSignals = RegExp(
    r'(天气|预报|气温|温度|体感|降水|下雨|风力)',
  ).allMatches(compact).length;
  final adviceSignals = RegExp(r'(外套|穿衣|建议|雨伞|带伞)').allMatches(compact).length;
  return weatherSignals >= 2 || adviceSignals >= 1;
}

AssistantReplayM1EntryAssessment _buildM0CaseM1Entry({
  required _M0ReplayCase replayCase,
  required List<AssistantReplayBaselineAttempt> attempts,
  required AssistantReplayBaselineStability stability,
}) {
  final satisfied = <String>[];
  final blocking = <String>[];
  if (attempts.length == _replayRepeatCount) {
    satisfied.add('repeat_count_met');
  } else {
    blocking.add('repeat_count_mismatch');
  }
  final hasArtifacts = attempts.every(
    (attempt) => attempt.turns.every(
      (turn) =>
          turn.runLogPath.trim().isNotEmpty &&
          turn.canonicalState.isNotEmpty &&
          turn.failureClass.trim().isNotEmpty,
    ),
  );
  if (hasArtifacts) {
    satisfied.add('artifacts_linked');
  } else {
    blocking.add('missing_artifacts');
  }
  final outcomesMatch = attempts.every(
    (attempt) =>
        attempt.gatePassed &&
        attempt.outcomeClass == replayCase.expectedOutcomeClass,
  );
  if (outcomesMatch) {
    satisfied.add('expected_outcome_stable');
  } else {
    blocking.add('unexpected_outcome_or_gate_failure');
  }
  if (stability.stable) {
    satisfied.add('replay_stable');
  } else {
    blocking.add('replay_unstable');
  }
  return AssistantReplayM1EntryAssessment(
    eligible: blocking.isEmpty,
    satisfiedChecks: satisfied,
    blockingReasons: blocking,
  );
}

AssistantReplayM1EntryAssessment _buildM0CorpusM1Entry({
  required List<AssistantReplayBaselinePack> packs,
  required List<_M0ReplayCase> selectedCases,
}) {
  final satisfied = <String>[];
  final blocking = <String>[];
  if (packs.length == selectedCases.length) {
    satisfied.add('all_selected_cases_emitted_pack');
  } else {
    blocking.add('missing_case_pack');
  }
  if (_knownFailureClasses.contains('weak_evidence_answered') &&
      _knownFailureClasses.contains('tool_progress_as_answer')) {
    satisfied.add('failure_signatures_frozen');
  } else {
    blocking.add('failure_signature_taxonomy_incomplete');
  }
  if (packs.every((pack) => pack.attempts.length == _replayRepeatCount)) {
    satisfied.add('all_cases_repeat_count_met');
  } else {
    blocking.add('case_repeat_count_incomplete');
  }
  if (packs.every((pack) => pack.m1Entry.eligible)) {
    satisfied.add('all_cases_ready_for_m1');
  } else {
    blocking.add('cases_not_ready_for_m1');
  }
  return AssistantReplayM1EntryAssessment(
    eligible: blocking.isEmpty,
    satisfiedChecks: satisfied,
    blockingReasons: blocking,
  );
}

Map<String, dynamic> _reloadStateFromSnapshot(
  _AssistantBubbleSnapshot? snapshot,
) {
  if (snapshot == null) {
    return const <String, dynamic>{};
  }
  return <String, dynamic>{'queryDesignLines': snapshot.queryDesignLines};
}

List<String> _collectReloadIssues({
  required Map<String, dynamic> beforeReload,
  required Map<String, dynamic> afterReload,
}) {
  final issues = <String>[];
  if (beforeReload.isEmpty) {
    issues.add('reload_missing_before_state');
    return issues;
  }
  if (afterReload.isEmpty) {
    issues.add('reload_missing_after_state');
    return issues;
  }
  if (_stableQueryDesignSignature(_reloadQueryDesignLines(beforeReload)) !=
      _stableQueryDesignSignature(_reloadQueryDesignLines(afterReload))) {
    issues.add('reload_query_design_changed');
  }
  return issues;
}

List<String> _reloadQueryDesignLines(Map<String, dynamic> state) {
  return ((state['queryDesignLines'] as List?) ?? const <dynamic>[])
      .map((item) => item.toString())
      .where((item) => item.trim().isNotEmpty)
      .toList(growable: false);
}

Map<String, dynamic> _buildCanonicalBaselineState(
  _AssistantBubbleSnapshot snapshot,
) {
  final normalized = snapshot.normalizedMessage;
  final displayState = resolvePersistedAssistantDisplayState(
    normalized,
  ).toJson();
  final answerState =
      (displayState['answer'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final understanding =
      (normalized[assistantUnderstandingSnapshotField] as Map?)
          ?.cast<String, dynamic>() ??
      (((normalized['runArtifacts']
                  as Map?)?[assistantUnderstandingSnapshotField]
              as Map?)
          ?.cast<String, dynamic>()) ??
      const <String, dynamic>{};
  final answerProcessing =
      (normalized[assistantAnswerProcessingField] as Map?)
          ?.cast<String, dynamic>() ??
      (((normalized['runArtifacts'] as Map?)?[assistantAnswerProcessingField]
              as Map?)
          ?.cast<String, dynamic>()) ??
      const <String, dynamic>{};
  final retrievalProcessing =
      (normalized[assistantRetrievalProcessingField] as Map?)
          ?.cast<String, dynamic>() ??
      (((normalized['runArtifacts'] as Map?)?[assistantRetrievalProcessingField]
              as Map?)
          ?.cast<String, dynamic>()) ??
      const <String, dynamic>{};
  final journey =
      (normalized[assistantJourneyField] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final readiness =
      (journey['readiness'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final processTimeline =
      (normalized[assistantProcessTimelineField] as List?)
          ?.whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .map(
            (item) => <String, dynamic>{
              'stepId': (item['stepId'] as String?)?.trim() ?? '',
              'status': (item['status'] as String?)?.trim() ?? '',
              'headline':
                  (item['headline'] as String?)?.trim() ??
                  (item['summary'] as String?)?.trim() ??
                  '',
            },
          )
          .toList(growable: false) ??
      const <Map<String, dynamic>>[];
  return <String, dynamic>{
    'displayMarkdown': resolvePersistedAssistantDisplayMarkdown(normalized),
    'displayPlainText': resolvePersistedAssistantDisplayPlainText(normalized),
    'displayAnswerBlocks':
        (answerState['blocks'] as List?) ?? const <dynamic>[],
    'processTimeline': processTimeline,
    'understandingSnapshot': <String, dynamic>{
      'userFacingSummary':
          (understanding['userFacingSummary'] as String?)?.trim() ?? '',
      'intentSummary':
          (understanding['intentSummary'] as String?)?.trim() ?? '',
    },
    'answerProcessing': <String, dynamic>{
      'readinessSummary':
          (answerProcessing['readinessSummary'] as String?)?.trim() ?? '',
      'keyFacts': (answerProcessing['keyFacts'] as List?) ?? const <dynamic>[],
      'missingDimensions':
          (answerProcessing['missingDimensions'] as List?) ?? const <dynamic>[],
    },
    'retrievalProcessing': <String, dynamic>{
      'processingSummary':
          (retrievalProcessing['processingSummary'] as String?)?.trim() ?? '',
      'coverageSummary':
          (retrievalProcessing['coverageSummary'] as String?)?.trim() ?? '',
    },
    'journeyReadiness': <String, dynamic>{
      'nextAction': (readiness['nextAction'] ?? '').toString(),
      'finalAnswerReady': readiness['finalAnswerReady'] == true,
      'answerEligibility': (readiness['answerEligibility'] ?? '').toString(),
    },
    'visibleProcessSteps': snapshot.visibleProcessSteps,
    'phaseOneRoutingDiagnostics': snapshot.phaseOneRoutingDiagnostics,
    'queryDesignLines': snapshot.queryDesignLines,
    'messageId': snapshot.messageId,
  };
}

Map<String, dynamic> _extractRunLogMeta(Map<String, dynamic> runLog) {
  final meta =
      (runLog['meta'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final output =
      (runLog['output'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  return <String, dynamic>{
    'generatedAt': (meta['generatedAt'] ?? '').toString(),
    'runId': (meta['runId'] ?? '').toString(),
    'traceId': (meta['traceId'] ?? '').toString(),
    'sessionId': (meta['sessionId'] ?? '').toString(),
    'channel': (meta['channel'] ?? '').toString(),
    'finalText': (output['finalText'] ?? '').toString(),
    'degraded': output['degraded'] == true,
  };
}

bool _listEquals(List<String> left, List<String> right) {
  if (left.length != right.length) {
    return false;
  }
  for (var i = 0; i < left.length; i++) {
    if (left[i] != right[i]) {
      return false;
    }
  }
  return true;
}

Future<void> _runReplayCase(
  WidgetTester tester, {
  required IntegrationTestWidgetsFlutterBinding binding,
  required String caseName,
  required String firstQuery,
  required String secondQuery,
}) async {
  final originalOnError = FlutterError.onError;
  try {
    await _resetAssistantApp(tester);
    await _wipeAssistantStorage();
    _suppressNetworkImageErrors();
    app.main();

    await _waitForMainEntry(tester);
    await _openAssistantConversation(tester);
    await _waitForChatInput(tester);

    final firstResult = await _sendQueryWithSingleRetry(
      tester,
      query: firstQuery,
    );
    debugPrint(
      '${caseName.toUpperCase()}_FIRST_RESULT: ${firstResult.toJson()}',
    );
    _expectReplayResult(firstResult);

    final secondResult = await _sendQueryWithSingleRetry(
      tester,
      query: secondQuery,
    );
    debugPrint(
      '${caseName.toUpperCase()}_SECOND_RESULT: ${secondResult.toJson()}',
    );
    _expectReplayResult(secondResult);

    final existingReportData = switch (binding.reportData) {
      final Map<Object?, Object?> map => map.map(
        (key, value) => MapEntry(key.toString(), value),
      ),
      _ => <String, dynamic>{},
    };
    binding.reportData = <String, dynamic>{
      ...existingReportData,
      caseName: <String, dynamic>{
        'firstQuery': firstResult.toJson(),
        'secondQuery': secondResult.toJson(),
      },
    };
  } finally {
    FlutterError.onError = originalOnError;
    await _resetAssistantApp(tester);
  }
}

Future<void> _runSingleQueryReplayCase(
  WidgetTester tester, {
  required IntegrationTestWidgetsFlutterBinding binding,
  required _TemporalReplayCase replayCase,
}) async {
  final originalOnError = FlutterError.onError;
  final referenceNow = DateTime.now();
  try {
    await _resetAssistantApp(tester);
    await _wipeAssistantStorage();
    _suppressNetworkImageErrors();
    app.main();

    await _waitForMainEntry(tester);
    await _openAssistantConversation(tester);
    await _waitForChatInput(tester);

    final result = await _sendQueryWithSingleRetry(
      tester,
      query: replayCase.query,
    );
    debugPrint(
      '${replayCase.caseName.toUpperCase()}_RESULT: ${result.toJson()}',
    );
    _expectReplayResult(result);
    _expectTemporalReplayResult(
      result,
      replayCase: replayCase,
      referenceNow: referenceNow,
    );

    final existingReportData = switch (binding.reportData) {
      final Map<Object?, Object?> map => map.map(
        (key, value) => MapEntry(key.toString(), value),
      ),
      _ => <String, dynamic>{},
    };
    binding.reportData = <String, dynamic>{
      ...existingReportData,
      replayCase.caseName: result.toJson(),
    };
  } finally {
    FlutterError.onError = originalOnError;
    await _resetAssistantApp(tester);
  }
}

Future<void> _runColdStartReloadCase(
  WidgetTester tester, {
  required IntegrationTestWidgetsFlutterBinding binding,
}) async {
  final originalOnError = FlutterError.onError;
  try {
    await _resetAssistantApp(tester);
    await _wipeAssistantStorage();
    _suppressNetworkImageErrors();
    app.main();

    await _waitForMainEntry(tester);
    await _openAssistantConversation(tester);
    await _waitForChatInput(tester);

    final firstResult = await _sendQueryWithSingleRetry(
      tester,
      query: _weatherFirstQuery,
    );
    debugPrint('COLD_START_RELOAD_FIRST_RESULT: ${firstResult.toJson()}');
    _expectReplayResult(firstResult);

    final beforeReload = _latestAssistantSnapshot(tester);
    expect(beforeReload, isNotNull);
    expect(
      beforeReload!.queryDesignLines,
      isNotEmpty,
      reason: '首轮完成后必须已经展示 query design，reload 才有意义',
    );
    expect(beforeReload.answerText.trim(), isNotEmpty);

    await _resetAssistantApp(tester);
    app.main();

    await _waitForMainEntry(tester);
    await _openAssistantConversation(tester);
    await _waitForChatInput(tester);
    await _pumpUntil(
      tester,
      condition: () {
        final snapshot = _latestAssistantSnapshot(tester);
        return snapshot != null && snapshot.answerText.trim().isNotEmpty;
      },
      timeout: const Duration(seconds: 20),
    );

    final afterReload = _latestAssistantSnapshot(tester);
    expect(afterReload, isNotNull);
    expect(
      _stableQueryDesignSignature(afterReload!.queryDesignLines),
      equals(_stableQueryDesignSignature(beforeReload.queryDesignLines)),
      reason: 'reload 后 query design 不应丢失或被空白 fallback 覆盖',
    );
    expect(
      AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
        afterReload.answerText,
      ),
      equals(
        AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
          beforeReload.answerText,
        ),
      ),
      reason: 'reload 后最后一条 assistant 答案应完整恢复',
    );
    expect(
      afterReload.visibleProcessSteps,
      orderedEquals(beforeReload.visibleProcessSteps),
    );
    expect(afterReload.journalStages, isNotEmpty);

    final existingReportData = switch (binding.reportData) {
      final Map<Object?, Object?> map => map.map(
        (key, value) => MapEntry(key.toString(), value),
      ),
      _ => <String, dynamic>{},
    };
    binding.reportData = <String, dynamic>{
      ...existingReportData,
      'cold_start_reload': <String, dynamic>{
        'beforeReload': <String, dynamic>{
          'answerText': beforeReload.answerText,
          'timelinePhases': beforeReload.timelinePhaseIds,
          'canonicalProcessSteps': beforeReload.canonicalProcessSteps,
          'queryDesignLines': beforeReload.queryDesignLines,
        },
        'afterReload': <String, dynamic>{
          'answerText': afterReload.answerText,
          'timelinePhases': afterReload.timelinePhaseIds,
          'canonicalProcessSteps': afterReload.canonicalProcessSteps,
          'queryDesignLines': afterReload.queryDesignLines,
        },
      },
    };
  } finally {
    FlutterError.onError = originalOnError;
    await _resetAssistantApp(tester);
  }
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
  String expectedScope = '',
}) async {
  await _ensureAssistantDialogReady(tester);
  final baselineSnapshot = _latestAssistantSnapshot(tester);
  final baselineMessageId =
      (baselineSnapshot?.message['id'] as String?)?.trim() ?? '';
  final baselineAnswer = baselineSnapshot?.answerText.trim() ?? '';
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
  var observedNewAssistantTurn = false;
  String latestProcessHeader = '';
  final deadline = DateTime.now().add(const Duration(seconds: 80));
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(seconds: 1));
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
    final currentMessageId = (snapshot.message['id'] as String?)?.trim() ?? '';
    final currentAnswer = latestAnswer.trim();
    if (!observedNewAssistantTurn &&
        (snapshot.streaming ||
            (currentMessageId.isNotEmpty &&
                currentMessageId != baselineMessageId) ||
            (currentAnswer.isNotEmpty && currentAnswer != baselineAnswer))) {
      observedNewAssistantTurn = true;
    }
    if (!observedNewAssistantTurn) {
      continue;
    }
    snapshots.add(latestText);
    _throwIfForbidden(latestText);
    latestProcessHeader = await _latestAssistantProcessHeaderText(tester);
    matchedExpected =
        _matchesReplayExpectation(
          expectedScope: expectedScope,
          query: query,
          answerText: latestAnswer,
          snapshot: snapshot,
        ) &&
        !_isGenericAssistantFallback(latestAnswer);
    if (latestAnswer == previousAnswer) {
      stableTicks += 1;
    } else {
      stableTicks = 0;
      previousAnswer = latestAnswer;
    }
    if (_hasSettledReplayAnswer(
      snapshot: snapshot,
      matchedExpected: matchedExpected,
      degraded: degraded,
      heuristicFallbackUsed: heuristicFallbackUsed,
      latestAnswer: latestAnswer,
      stableTicks: stableTicks,
      finalMessageStreaming: finalMessageStreaming,
      latestProcessHeader: latestProcessHeader,
    )) {
      break;
    }
  }

  if (!_hasSettledReplayAnswer(
        snapshot: latestSnapshot,
        matchedExpected: matchedExpected,
        degraded: degraded,
        heuristicFallbackUsed: heuristicFallbackUsed,
        latestAnswer: latestAnswer,
        stableTicks: stableTicks,
        finalMessageStreaming: finalMessageStreaming,
        latestProcessHeader: latestProcessHeader,
      ) &&
      latestSnapshot != null &&
      latestAnswer.trim().isNotEmpty &&
      !degraded &&
      !heuristicFallbackUsed) {
    final graceDeadline = DateTime.now().add(const Duration(seconds: 20));
    while (DateTime.now().isBefore(graceDeadline)) {
      await tester.pump(const Duration(seconds: 1));
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
      latestProcessHeader = await _latestAssistantProcessHeaderText(tester);
      matchedExpected =
          _matchesReplayExpectation(
            expectedScope: expectedScope,
            query: query,
            answerText: latestAnswer,
            snapshot: snapshot,
          ) &&
          !_isGenericAssistantFallback(latestAnswer);
      if (latestAnswer == previousAnswer) {
        stableTicks += 1;
      } else {
        stableTicks = 0;
        previousAnswer = latestAnswer;
      }
      if (_hasSettledReplayAnswer(
        snapshot: snapshot,
        matchedExpected: matchedExpected,
        degraded: degraded,
        heuristicFallbackUsed: heuristicFallbackUsed,
        latestAnswer: latestAnswer,
        stableTicks: stableTicks,
        finalMessageStreaming: finalMessageStreaming,
        latestProcessHeader: latestProcessHeader,
      )) {
        break;
      }
    }
  }

  final processHeaderText = latestProcessHeader.isNotEmpty
      ? latestProcessHeader
      : await _latestAssistantProcessHeaderText(tester);
  phaseLabelSeen = _isAcceptableProcessHeader(processHeaderText);

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
    timelinePhases: latestSnapshot?.visibleProcessSteps ?? const <String>[],
    journalStages: latestSnapshot?.visibleProcessSteps ?? const <String>[],
    queryDesignLines: latestSnapshot?.queryDesignLines ?? const <String>[],
    structuredTemporalAnchors:
        latestSnapshot?.structuredTemporalAnchors ?? const <String>[],
    structuredResolvedGeoScope:
        latestSnapshot?.structuredResolvedGeoScope ?? const <String, dynamic>{},
    structuredIntentTypes:
        latestSnapshot?.structuredIntentTypes ?? const <String>[],
    structuredEntityTypes:
        latestSnapshot?.structuredEntityTypes ?? const <String>[],
    structuredEntityKeys:
        latestSnapshot?.structuredEntityKeys ?? const <String>[],
    structuredTaskToolNames:
        latestSnapshot?.structuredTaskToolNames ?? const <String>[],
    structuredTaskIntentIds:
        latestSnapshot?.structuredTaskIntentIds ?? const <String>[],
  );
}

bool _hasSettledReplayAnswer({
  required _AssistantBubbleSnapshot? snapshot,
  required bool matchedExpected,
  required bool degraded,
  required bool heuristicFallbackUsed,
  required String latestAnswer,
  required int stableTicks,
  required bool finalMessageStreaming,
  required String latestProcessHeader,
}) {
  if (snapshot == null) {
    return false;
  }
  final finalAnswerMode = snapshot.finalAnswerMode;
  return matchedExpected &&
      !degraded &&
      !heuristicFallbackUsed &&
      snapshot.finalAnswerReady &&
      snapshot.runId.isNotEmpty &&
      latestAnswer.trim().isNotEmpty &&
      stableTicks >= 2 &&
      !finalMessageStreaming &&
      _isCompletedProcessHeader(latestProcessHeader) &&
      _hasCanonicalVisibleReplayTimeline(snapshot.timelinePhaseIds) &&
      _hasCanonicalVisibleReplayTimeline(snapshot.journalStages) &&
      snapshot.nextAction == AssistantNextAction.answer.wireName &&
      (finalAnswerMode == 'full' || finalAnswerMode == 'bounded_answer');
}

bool _replayResultSignalsReady(_ReplayResult result) {
  return result.matchedExpected &&
      !result.degraded &&
      !result.heuristicFallbackUsed &&
      !result.finalMessageStreaming &&
      result.finalAnswerText.trim().isNotEmpty &&
      result.nextAction == AssistantNextAction.answer.wireName &&
      (result.finalAnswerMode == 'full' ||
          result.finalAnswerMode == 'bounded_answer') &&
      _isCompletedProcessHeader(result.processHeaderText) &&
      _hasCanonicalVisibleReplayTimeline(result.timelinePhases) &&
      _hasCanonicalVisibleReplayTimeline(result.journalStages);
}

Future<_ReplayResult> _sendQueryWithSingleRetry(
  WidgetTester tester, {
  required String query,
  String expectedScope = '',
}) async {
  final first = await _sendQueryAndWaitForAnswer(
    tester,
    query: query,
    expectedScope: expectedScope,
  );
  if (!_shouldRetryReplay(first)) {
    return first;
  }
  debugPrint('RETRY_RESULT_TRIGGERED: ${first.toJson()}');
  return _sendQueryAndWaitForAnswer(
    tester,
    query: query,
    expectedScope: expectedScope,
  );
}

bool _shouldRetryReplay(_ReplayResult result) {
  final answer = result.finalAnswerText.trim();
  if (answer.isEmpty) return true;
  if (_isGenericAssistantFallback(answer)) return true;
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
                widget is AssistantMessageBubble &&
                (widget.asTimelineProtocolMap['senderId'] as String?) ==
                    AppConceptConstants.assistantSenderId,
            description: 'assistant bubble in assistant dialog',
          ),
        )
      : find.byWidgetPredicate(
          (widget) =>
              widget is AssistantMessageBubble &&
              (widget.asTimelineProtocolMap['senderId'] as String?) ==
                  AppConceptConstants.assistantSenderId,
          description: 'assistant bubble',
        );
  if (assistantBubbleFinder.evaluate().isEmpty) return null;
  final latestBubbleFinder = assistantBubbleFinder.last;
  final bubble = tester.widget<AssistantMessageBubble>(latestBubbleFinder);
  final bubbleText = _collectVisibleText(tester, scope: latestBubbleFinder);
  return _AssistantBubbleSnapshot(
    message: bubble.asTimelineProtocolMap,
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
                widget is AssistantMessageBubble &&
                (widget.asTimelineProtocolMap['senderId'] as String?) ==
                    AppConceptConstants.assistantSenderId,
            description: 'assistant bubble in assistant dialog',
          ),
        )
      : find.byWidgetPredicate(
          (widget) =>
              widget is AssistantMessageBubble &&
              (widget.asTimelineProtocolMap['senderId'] as String?) ==
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
  await tester.ensureVisible(headerFinder.first);
  await tester.pump(const Duration(milliseconds: 200));
  if (headerFinder.evaluate().isEmpty) return '';
  return _collectVisibleText(tester, scope: headerFinder);
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
  if (_isDefaultFirstReplayQuery(query)) {
    return _matchesTravelAlternativeAnswer(text);
  }
  if (_isDefaultSecondReplayQuery(query)) {
    return _matchesFollowupRouteAnswer(text);
  }
  if (_isStockForecastReplayQuery(query)) {
    return _matchesStockForecastAnswer(text);
  }
  if (_isStockTrendReplayQuery(query)) {
    return _matchesStockTrendAnswer(text);
  }
  if (_isWeatherReplayQuery(query)) {
    return false;
  }
  if (_isStockReplayQuery(query)) {
    return false;
  }
  return text.trim().isNotEmpty;
}

bool _matchesReplayExpectation({
  required String expectedScope,
  required String query,
  required String answerText,
  required _AssistantBubbleSnapshot snapshot,
}) {
  final structuredMatched = _matchesStructuredExpectation(
    expectedScope,
    snapshot,
  );
  if (_requiresStructuredReplayExpectation(expectedScope)) {
    return structuredMatched;
  }
  return structuredMatched || _matchesExpectation(query, answerText);
}

bool _requiresStructuredReplayExpectation(String expectedScope) {
  switch (expectedScope) {
    case 'weather_forecast':
    case 'stock_reason':
      return true;
    default:
      return false;
  }
}

bool _matchesStructuredExpectation(
  String expectedScope,
  _AssistantBubbleSnapshot snapshot,
) {
  if (expectedScope.isEmpty) {
    return false;
  }
  final structured = _ReplayResult.empty(
    query: '',
    structuredIntentTypes: snapshot.structuredIntentTypes,
    structuredEntityTypes: snapshot.structuredEntityTypes,
    structuredEntityKeys: snapshot.structuredEntityKeys,
    structuredTaskToolNames: snapshot.structuredTaskToolNames,
    structuredTaskIntentIds: snapshot.structuredTaskIntentIds,
  );
  return _hasStructuredScopeMatch(structured, expectedScope);
}

bool _isDefaultFirstReplayQuery(String query) {
  return query == _firstQuery && _firstQuery == _defaultFirstQuery;
}

bool _isDefaultSecondReplayQuery(String query) {
  return query == _secondQuery && _secondQuery == _defaultSecondQuery;
}

List<_TemporalReplayCase> _selectedTemporalReplayCases() {
  final normalizedFilter = _temporalReplayCaseFilter
      .split(',')
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .toSet();
  if (normalizedFilter.isEmpty) {
    return _temporalReplayCases;
  }
  return _temporalReplayCases
      .where((item) => normalizedFilter.contains(item.caseName))
      .toList(growable: false);
}

bool _isWeatherReplayQuery(String query) {
  return query.contains('天气') ||
      query.contains('下雨') ||
      query.contains('雨伞') ||
      query.contains('外套');
}

bool _isStockForecastReplayQuery(String query) {
  return _isStockReplayQuery(query) &&
      (query.contains('预测') || query.contains('未来'));
}

bool _isStockTrendReplayQuery(String query) {
  return _isStockReplayQuery(query) &&
      (query.contains('最近') || query.contains('走势') || query.contains('走向'));
}

bool _isStockReplayQuery(String query) {
  return query.contains('A股') ||
      query.contains('股市') ||
      query.contains('上证') ||
      query.contains('深证') ||
      query.contains('创业板');
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

bool _matchesStockTrendAnswer(String text) {
  final normalized = _normalizeLoose(text);
  final hasMarketTopic = RegExp(
    r'(A股|股市|上证|深证|创业板|大盘|市场)',
  ).hasMatch(normalized);
  final trendSignals = RegExp(
    r'(走势|走向|趋势|态势|走强|走弱|高开|上涨|下跌|回落|反弹|回调|震荡|波动|区间|成交|情绪|资金|板块)',
  ).allMatches(normalized).length;
  final hasSubstance = normalized.length >= 28;
  return hasMarketTopic && trendSignals >= 2 && hasSubstance;
}

bool _matchesStockForecastAnswer(String text) {
  final normalized = _normalizeLoose(text);
  final hasMarketTopic = RegExp(
    r'(A股|股市|上证|深证|创业板|大盘|市场)',
  ).hasMatch(normalized);
  final forecastSignals = RegExp(
    r'(预测|预计|可能|大概率|风险|情景|短期|中期|后市|走势)',
  ).allMatches(normalized).length;
  final evidenceSignals = RegExp(
    r'(国际经济|全球经济|海外|美联储|政策|资金|成交|情绪|关税|通胀)',
  ).allMatches(normalized).length;
  final hasSubstance = normalized.length >= 32;
  return hasMarketTopic &&
      forecastSignals >= 2 &&
      evidenceSignals >= 1 &&
      hasSubstance;
}

bool _isGenericAssistantFallback(String text) {
  final normalized = _normalizeLoose(text);
  if (normalized.isEmpty) {
    return true;
  }
  return normalized.contains('这个操作我暂时还没拿到可展示结果') ||
      normalized.contains('本次任务已完成，但没有生成可展示结果') ||
      normalized.contains('Unsupported content type') ||
      normalized.contains('application/pdf');
}

String _normalizeLoose(String text) {
  return text.replaceAll(RegExp(r'\s+'), ' ').trim();
}

List<String> _extractQueryDesignLines(String text) {
  final lines = text
      .split('\n')
      .map(_normalizeLoose)
      .where((line) => line.isNotEmpty)
      .toList(growable: false);
  final queryLines = <String>[];
  for (final line in lines) {
    if (line == '生成答案') {
      break;
    }
    if (line.startsWith('•')) {
      queryLines.add(line);
    }
  }
  return queryLines;
}

DateTime _startOfDay(DateTime value) {
  return DateTime(value.year, value.month, value.day);
}

DateTime _resolveWeekdayDate(
  DateTime referenceNow, {
  required int weekday,
  required int weekOffset,
}) {
  final referenceDate = _startOfDay(referenceNow);
  final weekStart = referenceDate.subtract(
    Duration(days: referenceDate.weekday - DateTime.monday),
  );
  return weekStart.add(Duration(days: weekOffset * 7 + weekday - 1));
}

bool _structuredTemporalAnchorsContainDate(
  List<String> anchors,
  DateTime targetDate,
) {
  for (final anchor in anchors) {
    final parsed = DateTime.tryParse(anchor.trim());
    if (parsed == null) {
      continue;
    }
    final date = _startOfDay(parsed);
    if (date.year == targetDate.year &&
        date.month == targetDate.month &&
        date.day == targetDate.day) {
      return true;
    }
  }
  return false;
}

bool _hasStructuredCalendarAnchor(List<String> anchors) {
  return anchors.any((item) => DateTime.tryParse(item.trim()) != null);
}

bool _hasReplayStructuredGeoScope(Map<String, dynamic> scope) {
  for (final key in const <String>[
    'resolvedText',
    'cityLabel',
    'regionLabel',
    'countryLabel',
    'marketLabel',
    'countryCode',
    'marketCode',
  ]) {
    if ((scope[key] as String?)?.trim().isNotEmpty == true) {
      return true;
    }
  }
  return false;
}

bool _isAcceptableProcessHeader(String text) {
  final normalized = _normalizeLoose(text);
  if (normalized.isEmpty) return false;
  if (_containsInternalProtocolLeak(normalized)) return false;
  if (normalized.contains('模型调用') ||
      normalized.toLowerCase().contains('token') ||
      normalized.contains('{{')) {
    return false;
  }
  if (_isCompletedProcessHeader(normalized)) {
    return true;
  }
  return normalized.length >= 8 &&
      !_skeletalProcessHeaders.contains(normalized);
}

bool _isCompletedProcessHeader(String text) {
  final raw = text.trim();
  if (raw.isEmpty) return false;
  final lines = raw
      .split('\n')
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
  if (lines.isEmpty) return false;
  if (lines.first != '已完成处理') return false;
  return lines
      .skip(1)
      .every(
        (line) => RegExp(r'^(处理 \d+ 篇|接纳 \d+ 篇|耗时 \d+ 秒)$').hasMatch(line),
      );
}

bool _completedHeaderHasDocumentCount(String text) {
  final normalized = _normalizeLoose(text);
  return RegExp(r'处理 \d+ 篇文档').hasMatch(normalized);
}

bool _hasCanonicalVisibleReplayTimeline(List<String> phases) {
  return _listEquals(phases, _canonicalVisibleReplayTimeline);
}

void _expectTemporalReplayResult(
  _ReplayResult result, {
  required _TemporalReplayCase replayCase,
  required DateTime referenceNow,
}) {
  final queryLines = result.queryDesignLines.isNotEmpty
      ? result.queryDesignLines
      : _extractQueryDesignLines(result.finalVisibleText);
  expect(
    queryLines,
    isNotEmpty,
    reason: '${replayCase.caseName} 必须在处理问题阶段展示 query design',
  );
  switch (replayCase.kind) {
    case _TemporalReplayExpectationKind.lastWednesday:
      final targetDate = _resolveWeekdayDate(
        referenceNow,
        weekday: DateTime.wednesday,
        weekOffset: -1,
      );
      _expectExplicitDateAnchor(
        result: result,
        replayCase: replayCase,
        targetDate: targetDate,
      );
      return;
    case _TemporalReplayExpectationKind.nextWednesday:
      final targetDate = _resolveWeekdayDate(
        referenceNow,
        weekday: DateTime.wednesday,
        weekOffset: 1,
      );
      _expectExplicitDateAnchor(
        result: result,
        replayCase: replayCase,
        targetDate: targetDate,
      );
      return;
    case _TemporalReplayExpectationKind.dayAfterTomorrow:
      final targetDate = _startOfDay(referenceNow).add(const Duration(days: 2));
      _expectExplicitDateAnchor(
        result: result,
        replayCase: replayCase,
        targetDate: targetDate,
      );
      return;
    case _TemporalReplayExpectationKind.recentWindow:
      _expectExplicitWindowQueryDesign(
        result: result,
        replayCase: replayCase,
        queryLines: queryLines,
        forbidFutureToken: false,
      );
      return;
    case _TemporalReplayExpectationKind.futureForecast:
      _expectExplicitWindowQueryDesign(
        result: result,
        replayCase: replayCase,
        queryLines: queryLines,
        forbidFutureToken: true,
      );
      expect(
        RegExp(
          r'(预测|预计|可能|风险|走势)',
        ).hasMatch(_normalizeLoose(result.finalAnswerText)),
        isTrue,
        reason: '${replayCase.caseName} 的最终答案必须明确给出预测/走势判断',
      );
      return;
  }
}

void _expectExplicitDateAnchor({
  required _ReplayResult result,
  required _TemporalReplayCase replayCase,
  required DateTime targetDate,
}) {
  expect(
    _structuredTemporalAnchorsContainDate(
      result.structuredTemporalAnchors,
      targetDate,
    ),
    isTrue,
    reason: '${replayCase.caseName} 的 query design 必须落成明确日期锚点',
  );
}

void _expectExplicitWindowQueryDesign({
  required _ReplayResult result,
  required _TemporalReplayCase replayCase,
  required List<String> queryLines,
  required bool forbidFutureToken,
}) {
  expect(
    _hasStructuredCalendarAnchor(result.structuredTemporalAnchors),
    isTrue,
    reason: '${replayCase.caseName} 的 query design 必须包含明确时间范围或年月锚点',
  );
  for (final line in queryLines) {
    expect(
      RegExp(r'(最近|最新|近期)').hasMatch(line),
      isFalse,
      reason: '${replayCase.caseName} 的 query design 不得直接保留模糊相对时间词',
    );
    if (forbidFutureToken) {
      expect(
        line.contains('未来'),
        isFalse,
        reason:
            '${replayCase.caseName} 的 query design 应检索支撑预测的历史/当前依据，而不是直接搜索未来事实',
      );
    }
  }
}

void _expectReplayResult(_ReplayResult result) {
  expect(result.phaseLabelSeen, isTrue, reason: '过程区首行必须是用户语言摘要或完成摘要');
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
    _isGenericAssistantFallback(result.finalAnswerText),
    isFalse,
    reason: '最终 assistant answer 不得退化为通用兜底或工具错误',
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
    _isCompletedProcessHeader(result.processHeaderText),
    isTrue,
    reason: '最终完成态的过程区首行必须收口到统一摘要，不允许停留在运行中文案',
  );
  expect(
    result.matchedExpected,
    isTrue,
    reason: '最终 assistant answer 必须满足该问题的对题锚点',
  );
  if (_completedHeaderHasDocumentCount(result.processHeaderText)) {
    expect(
      result.evidenceLedgerCount,
      greaterThan(0),
      reason: '完成态既然声明处理了文档，就必须保留证据账，不能只剩表面答案文本',
    );
    expect(
      result.answerEvidenceBindingCount,
      greaterThan(0),
      reason: '完成态既然声明处理了文档，就必须保留答案来源绑定，避免 grounding 丢失',
    );
  }
  expect(result.nextAction, 'answer', reason: '当前回放最终必须直接进入 answer');
  expect(
    result.timelinePhases,
    equals(_canonicalVisibleReplayTimeline),
    reason: 'completed 后可见 timeline 必须收口到 understanding → retrieval_processing',
  );
  expect(
    result.journalStages,
    equals(_canonicalVisibleReplayTimeline),
    reason: '历史恢复应与当前可见双阶段完成态一致，不能回退旧阶段命名',
  );
  expect(
    result.finalAnswerMode,
    anyOf(equals('full'), equals('bounded_answer')),
    reason: '最终回答模式必须是 full 或 bounded_answer',
  );
  expect(
    result.modelCallCount,
    lessThanOrEqualTo(5),
    reason: '单轮回放必须遵守总模型阶段不超过 5 次的业务预算',
  );
  if (_isDefaultFirstReplayQuery(result.query)) {
    expect(
      result.modelCallCount,
      lessThanOrEqualTo(5),
      reason: '首轮应在有限模型调用内完成成答，避免反复扩检',
    );
  }
  if (_isDefaultSecondReplayQuery(result.query)) {
    final route =
        (result.phaseOneRoutingDiagnostics['route'] as String?)?.trim() ?? '';
    expect(
      route,
      anyOf(equals('phase_one_direct_answer'), equals('formal_synthesis')),
      reason: '第二轮连续追问必须稳定收口到 answer，不允许掉回扩检或空路由',
    );
    final maxModelCalls = route == 'phase_one_direct_answer' ? 4 : 5;
    expect(
      result.modelCallCount,
      lessThanOrEqualTo(maxModelCalls),
      reason:
          '第二轮连续追问应避免掉回 secondary-skill 扩检；若统一走 formal synthesis 主轨，则允许 1 次额外成答调用',
    );
    if (route == 'phase_one_direct_answer') {
      expect(
        result.templateVersionUsed,
        'phase_one_direct_answer',
        reason: '命中 phase-one direct answer 时，模板出口应与路由一致',
      );
    } else {
      expect(
        result.templateVersionUsed.trim().isNotEmpty,
        isTrue,
        reason: '走 formal_synthesis 时也必须记录实际模板版本，便于回放排障',
      );
    }
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
    required this.queryDesignLines,
    required this.structuredTemporalAnchors,
    required this.structuredResolvedGeoScope,
    required this.structuredIntentTypes,
    required this.structuredEntityTypes,
    required this.structuredEntityKeys,
    required this.structuredTaskToolNames,
    required this.structuredTaskIntentIds,
  });

  const _ReplayResult.empty({
    required this.query,
    this.structuredIntentTypes = const <String>[],
    this.structuredEntityTypes = const <String>[],
    this.structuredEntityKeys = const <String>[],
    this.structuredTaskToolNames = const <String>[],
    this.structuredTaskIntentIds = const <String>[],
  }) : phaseLabelSeen = false,
       matchedExpected = false,
       degraded = false,
       heuristicFallbackUsed = false,
       finalAnswerText = '',
       finalVisibleText = '',
       snapshotsObserved = 0,
       finalMessageStreaming = false,
       modelCallCount = 0,
       nextAction = '',
       finalAnswerMode = '',
       expandSignalCount = 0,
       evidenceLedgerCount = 0,
       answerEvidenceBindingCount = 0,
       processHeaderText = '',
       templateVersionUsed = '',
       phaseOneRoutingDiagnostics = const <String, dynamic>{},
       timelinePhases = const <String>[],
       journalStages = const <String>[],
       queryDesignLines = const <String>[],
       structuredTemporalAnchors = const <String>[],
       structuredResolvedGeoScope = const <String, dynamic>{};

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
  final List<String> queryDesignLines;
  final List<String> structuredTemporalAnchors;
  final Map<String, dynamic> structuredResolvedGeoScope;
  final List<String> structuredIntentTypes;
  final List<String> structuredEntityTypes;
  final List<String> structuredEntityKeys;
  final List<String> structuredTaskToolNames;
  final List<String> structuredTaskIntentIds;

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
      'queryDesignLines': queryDesignLines,
      'structuredTemporalAnchors': structuredTemporalAnchors,
      'structuredResolvedGeoScope': structuredResolvedGeoScope,
      'structuredIntentTypes': structuredIntentTypes,
      'structuredEntityTypes': structuredEntityTypes,
      'structuredEntityKeys': structuredEntityKeys,
      'structuredTaskToolNames': structuredTaskToolNames,
      'structuredTaskIntentIds': structuredTaskIntentIds,
    };
  }
}

enum _M0ReplayTurnShape { singleTurn, followup, coldStartReload }

enum _M0TemporalExpectation { none, yesterday, tomorrow, weekday }

class _M0ReplayTurnSpec {
  const _M0ReplayTurnSpec({
    required this.turnId,
    required this.query,
    required this.expectedScope,
    required this.expectedOutcomeClass,
    required this.temporalExpectation,
  });

  final String turnId;
  final String query;
  final String expectedScope;
  final String expectedOutcomeClass;
  final _M0TemporalExpectation temporalExpectation;
}

class _M0ReplayCase {
  const _M0ReplayCase({
    required this.caseId,
    required this.turnShape,
    required this.expectedScope,
    required this.expectedTemporalAnchor,
    required this.expectedOutcomeClass,
    required this.turns,
  });

  final String caseId;
  final _M0ReplayTurnShape turnShape;
  final String expectedScope;
  final String expectedTemporalAnchor;
  final String expectedOutcomeClass;
  final List<_M0ReplayTurnSpec> turns;
}

enum _TemporalReplayExpectationKind {
  lastWednesday,
  nextWednesday,
  dayAfterTomorrow,
  recentWindow,
  futureForecast,
}

List<String> _queryDesignLineStringsFromFrames(
  List<ProcessTimelineFrame> frames,
) {
  final lines = <String>[];
  for (final frame in frames) {
    if (frame.stepId != ProcessStepId.retrievalDesign) continue;
    final detailLines = _queryDesignLineStringsFromText(frame.detail);
    if (detailLines.isNotEmpty) {
      lines.addAll(detailLines);
      continue;
    }
    lines.addAll(_queryDesignLineStringsFromText(frame.headline));
  }
  return _uniqueNonEmpty(lines);
}

List<String> _queryDesignLineStringsFromRawTimeline(List<dynamic> raw) {
  final lines = <String>[];
  for (final item in raw) {
    if (item is! Map) continue;
    final map = item.cast<String, dynamic>();
    final stepId = (map['stepId'] as String?)?.trim() ?? '';
    if (stepId != 'retrieval_design') continue;
    final detailLines = _queryDesignLineStringsFromText(
      (map['detail'] as String?)?.trim() ?? '',
    );
    if (detailLines.isNotEmpty) {
      lines.addAll(detailLines);
      continue;
    }
    final summaryLines = _queryDesignLineStringsFromText(
      (map['summary'] as String?)?.trim() ?? '',
    );
    if (summaryLines.isNotEmpty) {
      lines.addAll(summaryLines);
      continue;
    }
    lines.addAll(
      _queryDesignLineStringsFromText(
        (map['headline'] as String?)?.trim() ?? '',
      ),
    );
  }
  return _uniqueNonEmpty(lines);
}

List<String> _queryDesignLineStringsFromText(String text) {
  return text
      .split('\n')
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

List<String> _extractExplicitDateAnchorsFromText(String text) {
  final matches = <String>{};
  for (final match in RegExp(r'(\d{4})-(\d{1,2})-(\d{1,2})').allMatches(text)) {
    final year = int.tryParse(match.group(1) ?? '');
    final month = int.tryParse(match.group(2) ?? '');
    final day = int.tryParse(match.group(3) ?? '');
    if (year == null || month == null || day == null) {
      continue;
    }
    matches.add(DateTime(year, month, day).toIso8601String().split('T').first);
  }
  for (final match in RegExp(
    r'(\d{4})年(\d{1,2})月(\d{1,2})日',
  ).allMatches(text)) {
    final year = int.tryParse(match.group(1) ?? '');
    final month = int.tryParse(match.group(2) ?? '');
    final day = int.tryParse(match.group(3) ?? '');
    if (year == null || month == null || day == null) {
      continue;
    }
    matches.add(DateTime(year, month, day).toIso8601String().split('T').first);
  }
  return matches.toList(growable: false);
}

List<String> _queryDesignLineStringsFromSearchPlans(Map<String, dynamic> root) {
  final typedQueryPlan = _typedQueryPlanFromRoot(root);
  final planView =
      (typedQueryPlan['planView'] as Map?)?.cast<String, dynamic>() ??
      (root['planView'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final tasks =
      typedQueryPlan['searchPlans'] ??
      planView['searchPlans'] ??
      root['searchPlans'];
  if (tasks is! List) {
    return const <String>[];
  }
  final queries = <String>[];
  for (final task in tasks) {
    if (task is! Map) continue;
    final query = (task['query'] as String?)?.trim() ?? '';
    if (query.isNotEmpty) {
      queries.add(query);
    }
  }
  return _uniqueNonEmpty(queries);
}

Map<String, dynamic> _typedQueryPlanFromRoot(Map<String, dynamic> root) {
  final understandingRaw =
      (root[assistantUnderstandingResultField] as Map?)
          ?.cast<String, dynamic>() ??
      (((root['runArtifacts'] as Map?)?[assistantUnderstandingResultField])
              as Map?)
          ?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final taskGraphRaw =
      (root[assistantTaskGraphField] as Map?)?.cast<String, dynamic>() ??
      (((root['runArtifacts'] as Map?)?[assistantTaskGraphField]) as Map?)
          ?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  if (understandingRaw.isEmpty || taskGraphRaw.isEmpty) {
    return const <String, dynamic>{};
  }
  try {
    final understanding = UnderstandingResult.fromJson(understandingRaw);
    final taskGraph = TaskGraph.fromJson(taskGraphRaw);
    final planView = assistantPlanViewFromTypedMainline(
      understandingResult: understanding,
      taskGraph: taskGraph,
    );
    if (planView == null) {
      return const <String, dynamic>{};
    }
    return <String, dynamic>{
      'planView': planView.toJson(),
      'searchPlans': SearchPlanItem.toJsonList(planView.searchPlans),
    };
  } catch (_) {
    return const <String, dynamic>{};
  }
}

List<String> _queryDesignLineStringsFromUnderstandingSnapshot(
  Map<String, dynamic> root,
) {
  final candidates = <Map<String, dynamic>?>[
    (root[assistantUnderstandingSnapshotField] as Map?)
        ?.cast<String, dynamic>(),
    ((root['runArtifacts'] as Map?)?[assistantUnderstandingSnapshotField]
            as Map?)
        ?.cast<String, dynamic>(),
  ];
  final lines = <String>[];
  for (final snapshot in candidates) {
    if (snapshot == null) continue;
    for (final candidate in <String>[
      (snapshot['intentSummary'] as String?)?.trim() ?? '',
      (snapshot['userFacingSummary'] as String?)?.trim() ?? '',
    ]) {
      if (_looksLikeQueryDesignFallback(candidate)) {
        lines.add(candidate);
      }
    }
  }
  return _uniqueNonEmpty(lines);
}

bool _looksLikeQueryDesignFallback(String raw) {
  final compact = _normalizeLoose(raw);
  if (compact.length < 8) return false;
  if (RegExp(r'^(获取|查询|检索|确认|判断|分析|了解|核对|锁定)').hasMatch(compact)) {
    return true;
  }
  final normalized = _normalizeQueryDesignLineForStability(compact);
  return _looksLikeStockJumpReasonSignature(normalized) ||
      _looksLikeWeatherOuterwearSignature(normalized);
}

class _TemporalReplayCase {
  const _TemporalReplayCase({
    required this.caseName,
    required this.query,
    required this.kind,
  });

  final String caseName;
  final String query;
  final _TemporalReplayExpectationKind kind;
}

class _AssistantBubbleSnapshot {
  _AssistantBubbleSnapshot({required this.message, required this.bubbleText})
    : _runArtifacts = _tryParseRunArtifacts(message);

  final Map<String, dynamic> message;
  final String bubbleText;
  final RunArtifacts? _runArtifacts;

  static RunArtifacts? _tryParseRunArtifacts(Map<String, dynamic> message) {
    final raw = message['runArtifacts'];
    if (raw is! Map) return null;
    try {
      return RunArtifacts.fromJson(Map<String, dynamic>.from(raw));
    } catch (_) {
      return null;
    }
  }

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
      ((message['uiUsageStats'] as Map?)
              ?.cast<String, dynamic>())?['modelCallCount']
          is num
      ? ((message['uiUsageStats'] as Map?)!
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
    final ra = _runArtifacts;
    if (ra != null) {
      final nextAction = ra.answerDecisionReadView.nextAction;
      if (nextAction.isNotEmpty) {
        return nextAction;
      }
    }
    final conversationStateDecision =
        (message['conversationStateDecision'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final decisionNextAction =
        (conversationStateDecision['nextAction'] as String?)?.trim() ?? '';
    if (decisionNextAction.isNotEmpty) {
      return decisionNextAction;
    }
    final answerDecision =
        ((message['runArtifacts'] as Map?)?['answerDecision'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return (answerDecision['nextAction'] as String?)?.trim() ?? '';
  }

  String get finalAnswerMode {
    final ra = _runArtifacts;
    if (ra != null) {
      final mode = ra.diagnosticsReadView.finalAnswerMode.trim();
      if (mode.isNotEmpty) return mode;
    }
    final conversationStateDecision =
        (message['conversationStateDecision'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final decisionMode =
        (conversationStateDecision['finalAnswerMode'] as String?)?.trim() ?? '';
    if (decisionMode.isNotEmpty) {
      return decisionMode;
    }
    final answerDecision =
        ((message['runArtifacts'] as Map?)?['answerDecision'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final legacyMode =
        (answerDecision['finalAnswerMode'] as String?)?.trim() ?? '';
    if (legacyMode.isNotEmpty) return legacyMode;
    return '';
  }

  Map<String, dynamic> get _journey {
    final timeline = (message['uiProcessTimeline'] as Map?)
        ?.cast<String, dynamic>();
    if (timeline != null && timeline.isNotEmpty) {
      return timeline;
    }
    final direct = (message['journey'] as Map?)?.cast<String, dynamic>();
    if (direct != null && direct.isNotEmpty) {
      return direct;
    }
    final ra = _runArtifacts;
    if (ra != null) {
      return ra.journey.toJson();
    }
    return ((message['runArtifacts'] as Map?)?['journey'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
  }

  List<String> get timelinePhaseIds {
    final raw =
        (_journey['stages'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    return _uniqueNonEmpty(
      raw.map((item) => (item['stageId'] as String?)?.trim() ?? ''),
    );
  }

  List<String> get journalStages {
    final raw =
        ((_journey['stages'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false)) ??
        const <Map<String, dynamic>>[];
    return _uniqueNonEmpty(
      raw.map((item) => (item['stageId'] as String?)?.trim() ?? ''),
    );
  }

  int get expandSignalCount {
    final raw =
        ((_journey['entries'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false)) ??
        const <Map<String, dynamic>>[];
    final readiness =
        (_journey['readiness'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    var count = 0;
    if (readiness['needExpansion'] == true) {
      count += 1;
    }
    for (final item in raw) {
      final provenance =
          (item['provenance'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final actionCode = (provenance['actionCode'] as String?)?.trim() ?? '';
      final reasonCode = (provenance['reasonCode'] as String?)?.trim() ?? '';
      if (actionCode == 'expand_search' ||
          reasonCode == 'need_more_search' ||
          reasonCode == 'need_more_evidence') {
        count += 1;
      }
    }
    return count;
  }

  int get evidenceLedgerCount {
    final ra = _runArtifacts;
    if (ra != null) {
      return ra.evidenceLedger.length;
    }
    final raw =
        (((message['runArtifacts'] as Map?)?['evidenceLedger'] as List?) ??
                const <Object?>[])
            .whereType<Map>()
            .length;
    return raw;
  }

  int get answerEvidenceBindingCount {
    final ra = _runArtifacts;
    if (ra != null) {
      return ra.answerEvidenceBindings.length;
    }
    final raw =
        (((message['runArtifacts'] as Map?)?['answerEvidenceBindings']
                    as List?) ??
                const <Object?>[])
            .whereType<Map>()
            .length;
    return raw;
  }

  List<String> get queryDesignLines {
    final normalized = normalizedMessage;
    final normalizedTimeline =
        (normalized[assistantProcessTimelineField] as List?) ??
        ((normalized['runArtifacts'] as Map?)?[assistantProcessTimelineField]
            as List?);
    if (normalizedTimeline != null) {
      final normalizedLines = _queryDesignLineStringsFromRawTimeline(
        normalizedTimeline,
      );
      if (normalizedLines.isNotEmpty) {
        return normalizedLines;
      }
    }

    final ra = _runArtifacts;
    if (ra != null) {
      final fromTyped = _queryDesignLineStringsFromFrames(ra.processTimeline);
      if (fromTyped.isNotEmpty) {
        return fromTyped;
      }
    }

    for (final rawList in <List<dynamic>?>[
      message['processTimeline'] as List?,
      (message['runArtifacts'] as Map?)?['processTimeline'] as List?,
    ]) {
      if (rawList == null) continue;
      final parsed = _queryDesignLineStringsFromRawTimeline(rawList);
      if (parsed.isNotEmpty) {
        return parsed;
      }
    }

    for (final container in <Map<String, dynamic>?>[
      normalized,
      (normalized['runArtifacts'] as Map?)?.cast<String, dynamic>(),
      Map<String, dynamic>.from(message),
      (message['runArtifacts'] as Map?)?.cast<String, dynamic>(),
    ]) {
      if (container == null) continue;
      final fromSearchPlans = _queryDesignLineStringsFromSearchPlans(container);
      if (fromSearchPlans.isNotEmpty) {
        return fromSearchPlans;
      }
    }

    for (final container in <Map<String, dynamic>?>[
      normalized,
      (normalized['runArtifacts'] as Map?)?.cast<String, dynamic>(),
      Map<String, dynamic>.from(message),
      (message['runArtifacts'] as Map?)?.cast<String, dynamic>(),
    ]) {
      if (container == null) continue;
      final fromUnderstanding =
          _queryDesignLineStringsFromUnderstandingSnapshot(container);
      if (fromUnderstanding.isNotEmpty) {
        return fromUnderstanding;
      }
    }

    return const <String>[];
  }

  List<String> get canonicalProcessSteps {
    final normalized = normalizedMessage;
    final normalizedTimeline =
        (normalized[assistantProcessTimelineField] as List?) ??
        ((normalized['runArtifacts'] as Map?)?[assistantProcessTimelineField]
            as List?);
    if (normalizedTimeline != null) {
      final normalizedSteps = normalizedTimeline
          .whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .map((item) => (item['stepId'] as String?)?.trim() ?? '')
          .where((stepId) => stepId.isNotEmpty)
          .toList(growable: false);
      final uniqueNormalizedSteps = _uniqueNonEmpty(normalizedSteps);
      if (uniqueNormalizedSteps.isNotEmpty) {
        return uniqueNormalizedSteps;
      }
    }

    final ra = _runArtifacts;
    if (ra != null && ra.processTimeline.isNotEmpty) {
      final steps = ra.processTimeline
          .map((frame) => frame.stepId.wireName.trim())
          .where((stepId) => stepId.isNotEmpty)
          .toList(growable: false);
      final uniqueSteps = _uniqueNonEmpty(steps);
      if (uniqueSteps.isNotEmpty) return uniqueSteps;
    }
    final candidates = <List<dynamic>>[
      (message['processTimeline'] as List?) ?? const <Object?>[],
      ((message['runArtifacts'] as Map?)?['processTimeline'] as List?) ??
          const <Object?>[],
    ];
    for (final raw in candidates) {
      final steps = raw
          .whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .map((item) => (item['stepId'] as String?)?.trim() ?? '')
          .where((item) => item.isNotEmpty)
          .toList(growable: false);
      final uniqueSteps = _uniqueNonEmpty(steps);
      if (uniqueSteps.isNotEmpty) {
        return uniqueSteps;
      }
    }
    return const <String>[];
  }

  List<String> get visibleProcessSteps {
    final steps = canonicalProcessSteps;
    if (steps.isEmpty) {
      return const <String>[];
    }
    return steps
        .where(
          (stepId) =>
              stepId == ProcessStepId.understanding.wireName ||
              stepId == ProcessStepId.retrievalDesign.wireName ||
              stepId == ProcessStepId.retrievalProcessing.wireName,
        )
        .toList(growable: false);
  }

  String get messageId => (message['id'] as String?)?.trim() ?? '';

  String get runId => (message['runId'] as String?)?.trim() ?? '';

  String get traceId => (message['traceId'] as String?)?.trim() ?? '';

  bool get finalAnswerReady {
    final normalized = normalizedMessage;
    final ra = _runArtifacts;
    if (ra != null && ra.answerDecisionReadView.finalAnswerReady) {
      return true;
    }
    final journey =
        (normalized[assistantJourneyField] as Map?)?.cast<String, dynamic>() ??
        _journey;
    final readiness =
        (journey['readiness'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    if (readiness['finalAnswerReady'] == true) {
      return true;
    }
    final displayState = resolvePersistedAssistantDisplayState(
      normalized,
    ).toJson();
    final processState =
        (displayState['process'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    if (processState['finalAnswerReady'] == true) {
      return true;
    }
    final answerGate =
        (normalized[assistantAnswerGateDecisionField] as Map?)
            ?.cast<String, dynamic>() ??
        (((normalized['runArtifacts']
                    as Map?)?[assistantAnswerGateDecisionField]
                as Map?)
            ?.cast<String, dynamic>()) ??
        const <String, dynamic>{};
    if (answerGate['finalAnswerReady'] == true) {
      return true;
    }
    final answerDecision =
        (normalized['conversationStateDecision'] as Map?)
            ?.cast<String, dynamic>() ??
        (((normalized['runArtifacts'] as Map?)?['answerDecision'] as Map?)
            ?.cast<String, dynamic>()) ??
        const <String, dynamic>{};
    return answerDecision['finalAnswerReady'] == true;
  }

  Map<String, dynamic> get _understandingResult =>
      _structuredMapField(assistantUnderstandingResultField);

  Map<String, dynamic> get _taskGraph =>
      _structuredMapField(assistantTaskGraphField);

  Map<String, dynamic> get _systemContextEnvelope =>
      _structuredMapField(assistantSystemContextEnvelopeField);

  Map<String, dynamic> _structuredMapField(String fieldName) {
    final normalized = normalizedMessage;
    for (final container in <Map<String, dynamic>?>[
      normalized,
      (normalized['runArtifacts'] as Map?)?.cast<String, dynamic>(),
      Map<String, dynamic>.from(message),
      (message['runArtifacts'] as Map?)?.cast<String, dynamic>(),
    ]) {
      if (container == null) continue;
      final raw = container[fieldName];
      if (raw is Map && raw.isNotEmpty) {
        return raw.cast<String, dynamic>();
      }
    }
    return const <String, dynamic>{};
  }

  List<Map<String, dynamic>> get _structuredIntents {
    final raw = _understandingResult['intents'];
    return (raw as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
  }

  List<Map<String, dynamic>> get _structuredTasks {
    final raw = _taskGraph['tasks'];
    return (raw as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
  }

  List<String> get structuredIntentTypes {
    return _uniqueNonEmpty(
      _structuredIntents.map(
        (item) => (item['intentType'] as String?)?.trim() ?? '',
      ),
    );
  }

  List<String> get structuredEntityTypes {
    return _uniqueNonEmpty(
      _structuredIntents.expand((intent) {
        final refs =
            (intent['entityRefs'] as List?)
                ?.whereType<Map>()
                .map((item) => item.cast<String, dynamic>())
                .toList(growable: false) ??
            const <Map<String, dynamic>>[];
        return refs.map(
          (item) => (item['entityType'] as String?)?.trim() ?? '',
        );
      }),
    );
  }

  List<String> get structuredEntityKeys {
    return _uniqueNonEmpty(
      _structuredIntents.expand((intent) {
        final refs =
            (intent['entityRefs'] as List?)
                ?.whereType<Map>()
                .map((item) => item.cast<String, dynamic>())
                .toList(growable: false) ??
            const <Map<String, dynamic>>[];
        return refs.expand(
          (item) => <String>[
            (item['canonicalKey'] as String?)?.trim() ?? '',
            (item['displayText'] as String?)?.trim() ?? '',
          ],
        );
      }),
    );
  }

  List<String> get structuredTaskToolNames {
    return _uniqueNonEmpty(
      _structuredTasks.map(
        (item) => (item['toolName'] as String?)?.trim() ?? '',
      ),
    );
  }

  List<String> get structuredTaskIntentIds {
    return _uniqueNonEmpty(
      _structuredTasks.map(
        (item) => (item['intentId'] as String?)?.trim() ?? '',
      ),
    );
  }

  Map<String, dynamic> get _planView {
    final normalized = normalizedMessage;
    for (final container in <Map<String, dynamic>?>[
      normalized,
      (normalized['runArtifacts'] as Map?)?.cast<String, dynamic>(),
      Map<String, dynamic>.from(message),
      (message['runArtifacts'] as Map?)?.cast<String, dynamic>(),
    ]) {
      if (container == null) {
        continue;
      }
      final typedQueryPlan = _typedQueryPlanFromRoot(container);
      final typedPlanView =
          (typedQueryPlan['planView'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      if (typedPlanView.isNotEmpty) {
        return typedPlanView;
      }
      final planView =
          (container['planView'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      if (planView.isNotEmpty) {
        return planView;
      }
    }
    return const <String, dynamic>{};
  }

  List<String> get structuredTemporalAnchors {
    final taskAnchors = _uniqueNonEmpty(
      _structuredTasks.expand((task) {
        final toolArgs =
            (task['toolArgs'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{};
        final queries =
            (toolArgs['queries'] as List?)
                ?.map((item) => item.toString().trim())
                .where((item) => item.isNotEmpty)
                .toList(growable: false) ??
            const <String>[];
        return <String>[
          (toolArgs['timePoint'] as String?)?.trim() ?? '',
          (toolArgs['timeStart'] as String?)?.trim() ?? '',
          (toolArgs['timeEnd'] as String?)?.trim() ?? '',
          (toolArgs['timeRangeStart'] as String?)?.trim() ?? '',
          (toolArgs['timeRangeEnd'] as String?)?.trim() ?? '',
          ..._extractExplicitDateAnchorsFromText(
            (toolArgs['query'] as String?)?.trim() ?? '',
          ),
          for (final query in queries)
            ..._extractExplicitDateAnchorsFromText(query),
        ];
      }),
    );
    if (taskAnchors.isNotEmpty) {
      return taskAnchors;
    }

    final planView = _planView;
    final searchPlans =
        (planView['searchPlans'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    final values = <String>[
      for (final task in searchPlans) ...<String>[
        (task['timePoint'] as String?)?.trim() ?? '',
        (task['timeRangeStart'] as String?)?.trim() ?? '',
        (task['timeRangeEnd'] as String?)?.trim() ?? '',
        ..._extractExplicitDateAnchorsFromText(
          (task['query'] as String?)?.trim() ?? '',
        ),
        ..._extractExplicitDateAnchorsFromText(
          (task['label'] as String?)?.trim() ?? '',
        ),
      ],
    ];
    return _uniqueNonEmpty(values.where((item) => item.isNotEmpty));
  }

  Map<String, dynamic> get structuredResolvedGeoScope {
    final location =
        (_systemContextEnvelope['location'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final fromSystemContext = <String, dynamic>{
      if ((location['formattedAddress'] as String?)?.trim().isNotEmpty == true)
        'resolvedText': location['formattedAddress'],
      if ((location['adminAreaLevel2'] as String?)?.trim().isNotEmpty == true)
        'cityLabel': location['adminAreaLevel2'],
      if ((location['adminAreaLevel1'] as String?)?.trim().isNotEmpty == true)
        'regionLabel': location['adminAreaLevel1'],
      if ((location['countryName'] as String?)?.trim().isNotEmpty == true)
        'countryLabel': location['countryName'],
      if ((location['countryCode'] as String?)?.trim().isNotEmpty == true)
        'countryCode': location['countryCode'],
    };
    if (fromSystemContext.isNotEmpty) {
      return fromSystemContext;
    }

    final planView = _planView;
    return (planView['resolvedGeoScope'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
  }

  Map<String, dynamic> get normalizedMessage =>
      normalizeCanonicalPersistedAssistantTurnMessage(
        Map<String, dynamic>.from(message),
      ) ??
      Map<String, dynamic>.from(message);
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
