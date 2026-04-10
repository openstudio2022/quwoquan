import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/conversation_state_decision.dart';
import 'package:quwoquan_app/assistant/contracts/retrieval_outcome.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/retrieval_outcome_resolver.dart';

class AnswerGateResolver {
  const AnswerGateResolver({
    RetrievalOutcomeResolver retrievalOutcomeResolver =
        const RetrievalOutcomeResolver(),
  }) : _retrievalOutcomeResolver = retrievalOutcomeResolver;

  final RetrievalOutcomeResolver _retrievalOutcomeResolver;

  bool canAnswerWithCurrentEvidence({
    required RetrievalOutcome retrievalOutcome,
    required AnswerBoundaryPolicy policy,
  }) {
    if (retrievalOutcome.degraded ||
        !retrievalOutcome.terminalPayloadComplete) {
      return false;
    }
    if (policy.evidenceRequired &&
        !retrievalOutcome.hasToolResult &&
        retrievalOutcome.referenceCount <= 0 &&
        retrievalOutcome.processedDocumentCount <= 0 &&
        retrievalOutcome.acceptedDocumentCount <= 0) {
      return false;
    }
    return retrievalOutcome.retrievalReady;
  }

  AnswerGateDecision resolve({
    required RetrievalOutcome retrievalOutcome,
    ConversationStateDecision? conversationStateDecision,
    bool renderableAnswer = false,
    bool degraded = false,
    bool terminalPayloadComplete = true,
  }) {
    final effectiveTerminalPayloadComplete =
        terminalPayloadComplete && retrievalOutcome.terminalPayloadComplete;
    final effectiveDegraded = degraded || retrievalOutcome.degraded;
    final nextAction =
        conversationStateDecision?.nextActionWireName ??
        (retrievalOutcome.retrievalReady
            ? AssistantNextAction.answer.wireName
            : AssistantNextAction.abort.wireName);
    final answerEligibility =
        conversationStateDecision?.answerEligibilityWireName ??
        (retrievalOutcome.retrievalReady &&
                nextAction == AssistantNextAction.answer.wireName
            ? AnswerEligibility.eligible.wireName
            : AnswerEligibility.blocked.wireName);
    final retrievalReady =
        !effectiveDegraded &&
        effectiveTerminalPayloadComplete &&
        retrievalOutcome.retrievalReady;
    final eligible =
        retrievalReady &&
        renderableAnswer &&
        effectiveTerminalPayloadComplete &&
        nextAction == AssistantNextAction.answer.wireName;
    final reasonCode = _reasonCode(
      retrievalOutcome: retrievalOutcome,
      retrievalReady: retrievalReady,
      renderableAnswer: renderableAnswer,
      degraded: effectiveDegraded,
      terminalPayloadComplete: effectiveTerminalPayloadComplete,
      nextAction: nextAction,
    );
    final reason = _reasonMessage(
      reasonCode: reasonCode,
      retrievalOutcome: retrievalOutcome,
      renderableAnswer: renderableAnswer,
      nextAction: nextAction,
    );
    return AnswerGateDecision(
      eligible: eligible,
      finalAnswerReady: eligible,
      reasonCode: reasonCode,
      reason: reason,
      nextAction: nextAction,
      answerEligibility: answerEligibility,
      renderable: renderableAnswer,
      retrievalReady: retrievalReady,
      terminalPayloadComplete: effectiveTerminalPayloadComplete,
      degraded: effectiveDegraded,
      incomplete: !effectiveTerminalPayloadComplete,
      coveredDimensions: retrievalOutcome.coveredDimensions,
      missingDimensions: retrievalOutcome.missingDimensions,
      authoritySatisfied: retrievalOutcome.authoritySatisfied,
      freshnessSatisfied: retrievalOutcome.freshnessSatisfied,
    );
  }

  AnswerGateDecision resolveFromStructured({
    required Map<String, dynamic> structured,
    RunArtifacts? runArtifacts,
    bool degraded = false,
  }) {
    final raw = (structured[assistantAnswerGateDecisionField] as Map?)
        ?.cast<String, dynamic>();
    if (raw != null && raw.isNotEmpty) {
      try {
        return AnswerGateDecision.fromJson(raw);
      } catch (_) {
        // Fall through to derived decision.
      }
    }
    final retrievalOutcome = _retrievalOutcomeResolver.resolveFromStructured(
      structured: structured,
      runArtifacts: runArtifacts,
      degraded: degraded,
    );
    final conversationStateDecision = _parseConversationStateDecision(
      structured['conversationStateDecision'] ??
          runArtifacts?.answerDecision ??
          structured['decision'],
    );
    final renderableAnswer = _hasRenderableAnswer(structured, runArtifacts);
    return resolve(
      retrievalOutcome: retrievalOutcome,
      conversationStateDecision: conversationStateDecision,
      renderableAnswer: renderableAnswer,
      degraded: degraded,
      terminalPayloadComplete: retrievalOutcome.terminalPayloadComplete,
    );
  }

  String _reasonCode({
    required RetrievalOutcome retrievalOutcome,
    required bool retrievalReady,
    required bool renderableAnswer,
    required bool degraded,
    required bool terminalPayloadComplete,
    required String nextAction,
  }) {
    if (degraded) {
      return terminalPayloadComplete
          ? 'degraded_response'
          : 'incomplete_response';
    }
    if (!terminalPayloadComplete) return 'missing_terminal_payload';
    if (!retrievalReady) {
      if (retrievalOutcome.evidenceRequired &&
          !retrievalOutcome.hasToolResult &&
          retrievalOutcome.referenceCount <= 0 &&
          retrievalOutcome.processedDocumentCount <= 0 &&
          retrievalOutcome.acceptedDocumentCount <= 0) {
        return 'missing_required_evidence';
      }
      if (retrievalOutcome.authorityRequired &&
          !retrievalOutcome.authoritySatisfied) {
        return 'authority_unsatisfied';
      }
      if (retrievalOutcome.timeWindowRequired &&
          !retrievalOutcome.timeWindowKnown) {
        return 'historical_window_unknown';
      }
      if (retrievalOutcome.timeWindowRequired &&
          !retrievalOutcome.timeWindowSatisfied) {
        return 'historical_window_mismatch';
      }
      if (retrievalOutcome.freshnessRequired &&
          !retrievalOutcome.freshnessKnown) {
        return 'freshness_unknown';
      }
      if (retrievalOutcome.freshnessRequired &&
          !retrievalOutcome.freshnessSatisfied) {
        return 'freshness_unsatisfied';
      }
      if (retrievalOutcome.missingDimensions.isNotEmpty) {
        return 'missing_dimensions';
      }
      return 'missing_required_evidence';
    }
    if (nextAction != AssistantNextAction.answer.wireName) {
      return nextAction == AssistantNextAction.askUser.wireName
          ? 'ask_user'
          : 'blocked_by_state';
    }
    if (!renderableAnswer) return 'no_renderable_answer';
    return 'evidence_ready';
  }

  String _reasonMessage({
    required String reasonCode,
    required RetrievalOutcome retrievalOutcome,
    required bool renderableAnswer,
    required String nextAction,
  }) {
    final deliveringBoundedAnswer =
        nextAction == AssistantNextAction.answer.wireName && renderableAnswer;
    switch (reasonCode) {
      case 'evidence_ready':
        return retrievalOutcome.summary.trim().isNotEmpty
            ? retrievalOutcome.summary.trim()
            : '当前证据已满足成答条件。';
      case 'missing_terminal_payload':
        return '远端流式结果缺少终态 payload，当前只保留可见增量，不按成功完成处理。';
      case 'incomplete_response':
        return '当前响应未形成完整终态，先保留可见内容，不直接开闸成答。';
      case 'degraded_response':
        return retrievalOutcome.summary.trim().isNotEmpty
            ? retrievalOutcome.summary.trim()
            : '当前响应处于降级态，不直接开闸成答。';
      case 'authority_unsatisfied':
        if (deliveringBoundedAnswer) {
          return '已基于当前可确认信息整理答案，如需补齐更稳的权威依据可以继续补查。';
        }
        return '当前权威依据还不够稳，先不直接开闸成答。';
      case 'historical_window_unknown':
        if (deliveringBoundedAnswer) {
          return '已基于当前可确认信息整理答案，但资料缺少足够时间锚点；如果要继续核对目标时间窗，可以再补查。';
        }
        return '当前资料缺少足够时间锚点，还不能确认是否命中目标时间窗。';
      case 'historical_window_mismatch':
        if (deliveringBoundedAnswer) {
          return '已基于当前可确认信息整理答案，但现有资料还没充分落到目标时间窗；如果要继续补齐该时段依据，可以再补查。';
        }
        return '当前资料还没充分命中目标时间窗，先不直接开闸成答。';
      case 'freshness_unknown':
        if (deliveringBoundedAnswer) {
          return '已基于当前可确认信息整理答案，但资料缺少明确时间信号；如需补齐最新变化可继续补查。';
        }
        return '当前资料缺少明确时间信号，还不能按最新结论直接成答。';
      case 'freshness_unsatisfied':
        if (deliveringBoundedAnswer) {
          return '已基于当前可确认信息整理答案，如需补齐最新变化可继续补查。';
        }
        return '当前资料时效不足，还不能按最新结论直接成答。';
      case 'missing_dimensions':
        if (deliveringBoundedAnswer) {
          return '已基于当前可确认信息整理答案，但还有关键维度未补齐；如果你要，我可以继续补查。';
        }
        return '当前还缺关键维度，先不直接开闸成答。';
      case 'missing_required_evidence':
        if (deliveringBoundedAnswer) {
          return '已基于当前可确认信息整理答案；如果还要继续补齐更多依据，可以再补查。';
        }
        return '当前还缺继续成答所需的外部依据。';
      case 'ask_user':
        return '当前需要先补齐关键信息，再进入最终成答。';
      case 'no_renderable_answer':
        return '虽然证据已收敛，但还没有形成可展示的最终答案。';
      default:
        return retrievalOutcome.summary.trim().isNotEmpty
            ? retrievalOutcome.summary.trim()
            : '当前证据还不足以直接成答。';
    }
  }

  ConversationStateDecision? _parseConversationStateDecision(Object? raw) {
    if (raw is! Map) return null;
    try {
      final json = raw.cast<String, dynamic>();
      return ConversationStateDecision(
        nextAction: parseAssistantNextAction(
          (json['nextAction'] as String?)?.trim() ?? '',
        ),
        finalAnswerMode: parseFinalAnswerMode(
          (json['finalAnswerMode'] as String?)?.trim() ?? '',
        ),
        answerEligibility: parseAnswerEligibility(
          (json['answerEligibility'] as String?)?.trim() ?? '',
        ),
        finalAnswerReady: json['finalAnswerReady'] == true,
      );
    } catch (_) {
      return null;
    }
  }

  bool _hasRenderableAnswer(
    Map<String, dynamic> structured,
    RunArtifacts? runArtifacts,
  ) {
    final markdown =
        runArtifacts?.displayMarkdown.trim() ??
        ((structured['userMarkdown'] as String?)?.trim() ?? '');
    if (markdown.isNotEmpty) return true;
    final plain =
        runArtifacts?.displayPlainText.trim() ??
        (((structured['result'] as Map?)?['text'] as String?)?.trim() ?? '');
    return plain.isNotEmpty;
  }
}
