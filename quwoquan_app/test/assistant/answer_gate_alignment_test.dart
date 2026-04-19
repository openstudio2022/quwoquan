import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/context/assembly/evidence_evaluator.dart';
import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/conversation_state_decision.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_tool_result_row.dart';
import 'package:quwoquan_app/assistant/contracts/retrieval_outcome.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/orchestration/answer_outcome_resolver.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/answer_gate_resolver.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/retrieval_outcome_resolver.dart';

void main() {
  test('canAnswerWithCurrentEvidence 会尊重 retrieval outcome 状态而不是只看引用数', () {
    const resolver = AnswerGateResolver();
    final allowed = resolver.canAnswerWithCurrentEvidence(
      retrievalOutcome: const RetrievalOutcome(
        status: 'need_more_evidence',
        evidenceRequired: true,
        hasToolResult: true,
        referenceCount: 3,
        terminalPayloadComplete: true,
      ),
      policy: const AnswerBoundaryPolicy(evidenceRequired: true),
    );

    expect(allowed, isFalse);
  });

  test('历史定点 query 会走 timeWindow 命中而不是 now-based freshness', () {
    const outcomeResolver = RetrievalOutcomeResolver();
    const gateResolver = AnswerGateResolver();
    final outcome = outcomeResolver.resolve(
      policy: const AnswerBoundaryPolicy(
        evidenceRequired: true,
        allowBoundedAnswer: true,
        freshnessHoursMax: 24,
      ),
      retrievalProcessing: const RetrievalProcessingSnapshot(
        processedDocumentCount: 1,
        acceptedDocumentCount: 1,
      ),
      evidenceEvaluation: const EvidenceEvaluationResult(
        status: EvidenceStatus.bounded,
        passed: false,
        authoritySatisfied: true,
        freshnessSatisfied: false,
        evidenceRequired: true,
        coveredDimensions: <String>['latest_signal'],
        missingDimensions: <String>[],
        summary: '已命中目标时段资料。',
      ),
      synthesisReadiness: const SynthesisReadinessResult(ready: true),
      queryTasks: const <QueryTask>[
        QueryTask(
          id: 'stock_yesterday',
          query: '2026-04-07 A股 大涨 原因',
          dimension: QueryTaskDimension.latestSignal,
          timeScope: 'year_month_day',
          timePoint: '2026-04-07',
          timezone: 'Asia/Shanghai',
        ),
      ],
      toolResults: <AssistantToolResultRow>[
        AssistantToolResultRow(
          toolName: 'web_search',
          toolCallId: 'stock_yesterday',
          message: '查询完成',
          data: <String, dynamic>{
            'freshnessKnown': true,
            'freshnessSatisfied': true,
            'timeConstraint': <String, dynamic>{
              'scope': 'year_month_day',
              'timeRangeStart': '2026-04-07T00:00:00.000',
              'timeRangeEnd': '2026-04-07T23:59:59.999',
              'referenceNowIso': '2026-04-08T10:30:00.000',
              'temporalMode': 'historical',
            },
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': 'A股盘后解读',
                'url': 'https://news.example.com/analysis/market-recap',
                'snippet': '2026-04-07 A股大涨，主要由权重板块共振驱动。',
              },
            ],
          },
        ),
      ],
    );

    expect(outcome.timeWindowRequired, isTrue);
    expect(outcome.timeWindowKnown, isTrue);
    expect(outcome.timeWindowSatisfied, isTrue);
    expect(outcome.freshnessRequired, isFalse);
    expect(outcome.evidencePassed, isTrue);
    expect(outcome.status, equals('ready'));

    final gate = gateResolver.resolve(
      retrievalOutcome: outcome,
      conversationStateDecision: const ConversationStateDecision(
        nextAction: AssistantNextAction.answer,
        finalAnswerMode: FinalAnswerMode.boundedAnswer,
        answerEligibility: AnswerEligibility.eligible,
        finalAnswerReady: true,
      ),
      renderableAnswer: true,
    );

    expect(gate.finalAnswerReady, isTrue);
    expect(gate.reasonCode, equals('evidence_ready'));
  });

  test('bounded answer 一旦被状态机选中就不再被 gate 回退成未完成', () {
    const gateResolver = AnswerGateResolver();
    const outcome = RetrievalOutcome(
      status: 'need_more_evidence',
      summary: '已基于当前可确认信息整理答案；如果还要继续补齐更多依据，可以再补查。',
      evidenceRequired: true,
      authorityRequired: true,
      authoritySatisfied: false,
      freshnessSatisfied: true,
      hasToolResult: true,
      referenceCount: 2,
      processedDocumentCount: 2,
      acceptedDocumentCount: 2,
      terminalPayloadComplete: true,
    );

    final gate = gateResolver.resolve(
      retrievalOutcome: outcome,
      conversationStateDecision: const ConversationStateDecision(
        nextAction: AssistantNextAction.answer,
        finalAnswerMode: FinalAnswerMode.boundedAnswer,
        answerEligibility: AnswerEligibility.eligible,
        finalAnswerReady: true,
      ),
      renderableAnswer: true,
    );

    expect(gate.finalAnswerReady, isTrue);
    expect(gate.reasonCode, equals('bounded_delivery'));
    expect(gate.reason, equals(outcome.summary));
  });

  test('零结果工具调用也不能把 bounded answer 误判为 ready', () {
    const gateResolver = AnswerGateResolver();
    const outcome = RetrievalOutcome(
      status: 'need_more_evidence',
      summary: '当前还没有拿到可支撑结论的外部证据。',
      evidenceRequired: true,
      authorityRequired: true,
      authoritySatisfied: false,
      freshnessSatisfied: false,
      hasToolResult: true,
      referenceCount: 0,
      processedDocumentCount: 0,
      acceptedDocumentCount: 0,
      terminalPayloadComplete: true,
    );

    final gate = gateResolver.resolve(
      retrievalOutcome: outcome,
      conversationStateDecision: const ConversationStateDecision(
        nextAction: AssistantNextAction.answer,
        finalAnswerMode: FinalAnswerMode.boundedAnswer,
        answerEligibility: AnswerEligibility.eligible,
        finalAnswerReady: true,
      ),
      renderableAnswer: true,
    );

    expect(gate.finalAnswerReady, isFalse);
    expect(gate.eligible, isFalse);
    expect(gate.reasonCode, equals('missing_required_evidence'));
  });

  test('resolveFromStructured 不再信任放宽后的 answerGateDecision', () {
    const gateResolver = AnswerGateResolver();
    final decision = gateResolver.resolveFromStructured(
      structured: <String, dynamic>{
        assistantRetrievalOutcomeField: <String, dynamic>{
          'status': 'need_more_evidence',
          'summary': '当前还没有拿到可支撑结论的外部证据。',
          'evidenceRequired': true,
          'authorityRequired': true,
          'authoritySatisfied': false,
          'hasToolResult': false,
          'referenceCount': 0,
          'processedDocumentCount': 0,
          'acceptedDocumentCount': 0,
          'terminalPayloadComplete': true,
        },
        assistantAnswerGateDecisionField: <String, dynamic>{
          'eligible': true,
          'finalAnswerReady': true,
          'reasonCode': 'bounded_delivery',
          'reason': '旧 gate 误判可成答。',
          'nextAction': AssistantNextAction.answer.wireName,
          'answerEligibility': AnswerEligibility.eligible.wireName,
          'renderable': true,
          'retrievalReady': false,
          'terminalPayloadComplete': true,
          'degraded': false,
          'incomplete': false,
        },
        'conversationStateDecision': const ConversationStateDecision(
          nextAction: AssistantNextAction.answer,
          finalAnswerMode: FinalAnswerMode.boundedAnswer,
          answerEligibility: AnswerEligibility.eligible,
          finalAnswerReady: true,
        ).toDecisionMap(),
        'userMarkdown': '目前我还没查到昨天 A 股大涨的具体原因。',
      },
    );

    expect(decision.finalAnswerReady, isFalse);
    expect(decision.eligible, isFalse);
    expect(decision.reasonCode, equals('missing_required_evidence'));
  });

  test('AnswerOutcomeResolver 不再信任 rawOutcome 里的宽松 gate', () {
    const resolver = AnswerOutcomeResolver();
    final snapshot = resolver.resolve(
      structured: <String, dynamic>{
        'userMarkdown': '目前我还没查到昨天 A 股大涨的具体原因。',
        'answerOutcome': <String, dynamic>{
          'retrievalOutcome': <String, dynamic>{
            'status': 'need_more_evidence',
            'summary': '当前还没有拿到可支撑结论的外部证据。',
            'evidenceRequired': true,
            'authorityRequired': true,
            'authoritySatisfied': false,
            'hasToolResult': false,
            'referenceCount': 0,
            'processedDocumentCount': 0,
            'acceptedDocumentCount': 0,
            'terminalPayloadComplete': true,
          },
          'conversationStateDecision': const ConversationStateDecision(
            nextAction: AssistantNextAction.answer,
            finalAnswerMode: FinalAnswerMode.boundedAnswer,
            answerEligibility: AnswerEligibility.eligible,
            finalAnswerReady: true,
          ).toDecisionMap(),
          'answerGateDecision': <String, dynamic>{
            'eligible': true,
            'finalAnswerReady': true,
            'reasonCode': 'bounded_delivery',
            'reason': '旧 gate 误判可成答。',
            'nextAction': AssistantNextAction.answer.wireName,
            'answerEligibility': AnswerEligibility.eligible.wireName,
            'renderable': true,
            'retrievalReady': false,
            'terminalPayloadComplete': true,
            'degraded': false,
            'incomplete': false,
          },
        },
      },
    );

    expect(snapshot.answerGateDecision.finalAnswerReady, isFalse);
    expect(snapshot.answerGateDecision.eligible, isFalse);
    expect(
      snapshot.answerGateDecision.reasonCode,
      equals('missing_required_evidence'),
    );
  });

  test('AnswerOutcomeResolver 会把 journey readiness 视为最终成答材料化信号', () {
    const resolver = AnswerOutcomeResolver();
    final snapshot = resolver.resolve(
      structured: const <String, dynamic>{
        'answerOutcome': <String, dynamic>{},
      },
      runArtifacts: RunArtifacts.fromJson(
        const <String, dynamic>{
          'journey': <String, dynamic>{
            'readiness': <String, dynamic>{
              'finalAnswerReady': true,
            },
          },
        },
      ),
    );

    expect(snapshot.journey.readiness.finalAnswerReady, isTrue);
    expect(snapshot.synthesisReadiness.ready, isTrue);
  });

  test('实时 query 仍然保持严格 freshness gate', () {
    const outcomeResolver = RetrievalOutcomeResolver();
    const gateResolver = AnswerGateResolver();
    final outcome = outcomeResolver.resolve(
      policy: const AnswerBoundaryPolicy(
        evidenceRequired: true,
        allowBoundedAnswer: true,
        freshnessHoursMax: 24,
      ),
      retrievalProcessing: const RetrievalProcessingSnapshot(
        processedDocumentCount: 1,
        acceptedDocumentCount: 1,
      ),
      evidenceEvaluation: const EvidenceEvaluationResult(
        status: EvidenceStatus.bounded,
        passed: false,
        authoritySatisfied: true,
        freshnessSatisfied: false,
        evidenceRequired: true,
        coveredDimensions: <String>['current_state'],
        missingDimensions: <String>[],
        summary: '拿到了天气候选，但时效还不够稳。',
      ),
      synthesisReadiness: const SynthesisReadinessResult(ready: true),
      queryTasks: const <QueryTask>[
        QueryTask(
          id: 'weather_today',
          query: '深圳 2026-04-09 实时天气',
          dimension: QueryTaskDimension.currentState,
          timeScope: 'today',
          timePoint: '2026-04-09',
          timezone: 'Asia/Shanghai',
        ),
      ],
      toolResults: <AssistantToolResultRow>[
        AssistantToolResultRow(
          toolName: 'web_search',
          toolCallId: 'weather_today',
          message: '查询完成',
          data: <String, dynamic>{
            'freshnessKnown': true,
            'freshnessSatisfied': false,
            'timeConstraint': <String, dynamic>{
              'scope': 'today',
              'timeRangeStart': '2026-04-09T00:00:00.000',
              'timeRangeEnd': '2026-04-09T10:30:00.000',
              'referenceNowIso': '2026-04-09T10:30:00.000',
              'temporalMode': 'realtime',
            },
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '深圳天气旧快讯',
                'url': 'https://weather.example.com/archive',
                'publishedAt': '2026-04-07T07:00:00.000Z',
                'snippet': '页面时效偏旧。',
              },
            ],
          },
        ),
      ],
    );

    expect(outcome.freshnessRequired, isTrue);
    expect(outcome.timeWindowRequired, isFalse);
    expect(outcome.status, equals('need_more_evidence'));

    final gate = gateResolver.resolve(
      retrievalOutcome: outcome,
      conversationStateDecision: const ConversationStateDecision(
        nextAction: AssistantNextAction.answer,
        finalAnswerMode: FinalAnswerMode.boundedAnswer,
        answerEligibility: AnswerEligibility.blocked,
        finalAnswerReady: false,
      ),
      renderableAnswer: true,
    );

    expect(gate.finalAnswerReady, isFalse);
    expect(gate.reasonCode, equals('freshness_unsatisfied'));
  });

  test('未来定点天气 query 不会被默认 freshness policy 误判成实时阻塞', () {
    const outcomeResolver = RetrievalOutcomeResolver();
    const gateResolver = AnswerGateResolver();
    final outcome = outcomeResolver.resolve(
      policy: const AnswerBoundaryPolicy(
        evidenceRequired: true,
        authorityRequired: true,
        allowBoundedAnswer: true,
        freshnessHoursMax: 1,
      ),
      retrievalProcessing: const RetrievalProcessingSnapshot(
        processedDocumentCount: 1,
        acceptedDocumentCount: 1,
      ),
      evidenceEvaluation: const EvidenceEvaluationResult(
        status: EvidenceStatus.full,
        passed: true,
        authoritySatisfied: true,
        freshnessSatisfied: false,
        evidenceRequired: true,
        coveredDimensions: <String>['latest_signal'],
        missingDimensions: <String>[],
        summary: '已拿到明日天气预报。',
      ),
      synthesisReadiness: const SynthesisReadinessResult(ready: true),
      queryTasks: const <QueryTask>[
        QueryTask(
          id: 'weather_tomorrow',
          query: '2026-04-10 深圳 天气 预报',
          dimension: QueryTaskDimension.latestSignal,
          timeScope: 'year_month_day',
          timePoint: '2026-04-10',
          freshnessHoursMax: 1,
          timezone: 'Asia/Shanghai',
        ),
      ],
      toolResults: <AssistantToolResultRow>[
        AssistantToolResultRow(
          toolName: 'web_search',
          toolCallId: 'weather_tomorrow',
          message: '查询完成',
          data: <String, dynamic>{
            'authoritySatisfied': true,
            'timeConstraint': <String, dynamic>{
              'scope': 'year_month_day',
              'timeRangeStart': '2026-04-10T00:00:00.000',
              'timeRangeEnd': '2026-04-10T23:59:59.999',
              'referenceNowIso': '2026-04-09T10:30:00.000',
              'temporalMode': 'future',
            },
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '深圳天气预报',
                'url': 'https://weather.com.cn/weather1d/101280601.shtml',
                'snippet': '深圳 2026-04-10 多云转阵雨，建议带伞。',
              },
            ],
          },
        ),
      ],
    );

    expect(outcome.freshnessRequired, isFalse);
    expect(outcome.status, equals('ready'));

    final gate = gateResolver.resolve(
      retrievalOutcome: outcome,
      conversationStateDecision: const ConversationStateDecision(
        nextAction: AssistantNextAction.answer,
        finalAnswerMode: FinalAnswerMode.full,
        answerEligibility: AnswerEligibility.eligible,
        finalAnswerReady: true,
      ),
      renderableAnswer: true,
    );

    expect(gate.finalAnswerReady, isTrue);
    expect(gate.reasonCode, equals('evidence_ready'));
  });

  test('低相关证据不会再被放行为 ready/full answer', () {
    const outcomeResolver = RetrievalOutcomeResolver();
    final outcome = outcomeResolver.resolve(
      policy: const AnswerBoundaryPolicy(
        evidenceRequired: true,
        authorityRequired: true,
      ),
      retrievalProcessing: const RetrievalProcessingSnapshot(
        processedDocumentCount: 5,
        acceptedDocumentCount: 4,
      ),
      evidenceEvaluation: const EvidenceEvaluationResult(
        status: EvidenceStatus.full,
        passed: true,
        authoritySatisfied: true,
        freshnessSatisfied: true,
        evidenceRequired: true,
        relevanceScore: 0.33,
        coveredDimensions: <String>['latest_signal'],
        missingDimensions: <String>[],
        summary: '已拿到若干网页，但命中度一般。',
      ),
      synthesisReadiness: const SynthesisReadinessResult(ready: true),
      toolResults: <AssistantToolResultRow>[
        AssistantToolResultRow(
          toolName: 'web_search',
          toolCallId: 'market_analysis',
          message: '查询完成',
          data: <String, dynamic>{
            'authoritySatisfied': true,
            'freshnessSatisfied': true,
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '市场解读',
                'url': 'https://news.example.com/analysis',
                'relevanceScore': 0.33,
              },
            ],
          },
        ),
      ],
    );

    expect(outcome.evidencePassed, isFalse);
    expect(outcome.status, equals('need_more_evidence'));
    expect(outcome.summary, contains('关联度'));
  });

  test('historical 判定会优先使用 referenceNowIso 而不是当前墙钟时间', () {
    const outcomeResolver = RetrievalOutcomeResolver();
    final outcome = outcomeResolver.resolve(
      policy: const AnswerBoundaryPolicy(evidenceRequired: false),
      retrievalProcessing: const RetrievalProcessingSnapshot(),
      evidenceEvaluation: const EvidenceEvaluationResult(),
      synthesisReadiness: const SynthesisReadinessResult(ready: true),
      queryTasks: const <QueryTask>[
        QueryTask(
          id: 'future_anchor',
          query: '2099-01-01 市场回顾',
          dimension: QueryTaskDimension.latestSignal,
          timeScope: 'year_month_day',
          timePoint: '2099-01-01',
          timezone: 'Asia/Shanghai',
        ),
      ],
      referenceNowIso: '2099-01-02T10:30:00+08:00',
      timezone: 'Asia/Shanghai',
    );

    expect(
      outcome.timeWindowRequired,
      isTrue,
      reason: '应基于传入 referenceNowIso 把 2099-01-01 判定为历史定点查询',
    );
    expect(outcome.timeWindowKnown, isFalse);
    expect(outcome.status, equals('need_more_evidence'));
  });
}
