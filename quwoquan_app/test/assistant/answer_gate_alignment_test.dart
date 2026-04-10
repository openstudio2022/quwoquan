import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/context/assembly/evidence_evaluator.dart';
import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/conversation_state_decision.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/assistant/contracts/retrieval_outcome.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
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
      toolResults: <Map<String, dynamic>>[
        <String, dynamic>{
          'data': <String, dynamic>{
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
        },
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
      toolResults: <Map<String, dynamic>>[
        <String, dynamic>{
          'data': <String, dynamic>{
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
        },
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
      toolResults: <Map<String, dynamic>>[
        <String, dynamic>{
          'data': <String, dynamic>{
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
        },
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
      toolResults: <Map<String, dynamic>>[
        <String, dynamic>{
          'data': <String, dynamic>{
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
        },
      ],
    );

    expect(outcome.evidencePassed, isFalse);
    expect(outcome.status, equals('need_more_evidence'));
    expect(outcome.summary, contains('命中度'));
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
