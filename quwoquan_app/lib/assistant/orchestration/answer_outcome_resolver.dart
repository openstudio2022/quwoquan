import 'package:quwoquan_app/assistant/context/assembly/evidence_evaluator.dart';
import 'package:quwoquan_app/assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/conversation/contracts/conversation_state_decision.dart';

class AnswerOutcomeSnapshot {
  const AnswerOutcomeSnapshot({
    this.slotState = const SlotStateSnapshot(),
    this.evidenceLedger = const <EvidenceLedgerEntry>[],
    this.answerEvidenceBindings = const <AnswerEvidenceBinding>[],
    this.evidenceEvaluation = const EvidenceEvaluationResult(),
    this.aggregationState = const AggregationState(),
    this.synthesisReadiness = const SynthesisReadinessResult(),
    this.conversationStateDecision,
    this.domainPolicyBundle,
    this.processJournal = const <ProcessJournalEvent>[],
    this.liveCursor,
  });

  final SlotStateSnapshot slotState;
  final List<EvidenceLedgerEntry> evidenceLedger;
  final List<AnswerEvidenceBinding> answerEvidenceBindings;
  final EvidenceEvaluationResult evidenceEvaluation;
  final AggregationState aggregationState;
  final SynthesisReadinessResult synthesisReadiness;
  final ConversationStateDecision? conversationStateDecision;
  final DomainPolicyBundle? domainPolicyBundle;
  final List<ProcessJournalEvent> processJournal;
  final ProcessJournalEvent? liveCursor;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'slotState': slotState.toJson(),
    'evidenceLedger': evidenceLedger
        .map((item) => item.toJson())
        .toList(growable: false),
    'answerEvidenceBindings': answerEvidenceBindings
        .map((item) => item.toJson())
        .toList(growable: false),
    'evidenceEvaluation': evidenceEvaluation.toJson(),
    'aggregationState': aggregationState.toJson(),
    'synthesisReadiness': synthesisReadiness.toJson(),
    if (conversationStateDecision != null)
      'conversationStateDecision': conversationStateDecision!.toDecisionMap(),
    if (domainPolicyBundle != null)
      'domainPolicyBundle': domainPolicyBundle!.toJson(),
    'processJournal': processJournal
        .map((item) => item.toJson())
        .toList(growable: false),
    if (liveCursor != null) 'liveCursor': liveCursor!.toJson(),
  };
}

class AnswerOutcomeResolver {
  const AnswerOutcomeResolver();

  AnswerOutcomeSnapshot resolve({
    required Map<String, dynamic> structured,
    RunArtifacts? runArtifacts,
    List<EvidenceLedgerEntry> fallbackEvidenceLedger =
        const <EvidenceLedgerEntry>[],
    List<AnswerEvidenceBinding> fallbackAnswerEvidenceBindings =
        const <AnswerEvidenceBinding>[],
    EvidenceEvaluationResult? fallbackEvidenceEvaluation,
    AggregationState? fallbackAggregationState,
    ConversationStateDecision? fallbackConversationStateDecision,
    SynthesisReadinessResult? fallbackSynthesisReadiness,
    SlotStateSnapshot? fallbackSlotState,
    DomainPolicyBundle? fallbackDomainPolicyBundle,
    List<ProcessJournalEvent> fallbackProcessJournal =
        const <ProcessJournalEvent>[],
    ProcessJournalEvent? fallbackLiveCursor,
  }) {
    final rawOutcome = (structured['answerOutcome'] as Map?)
        ?.cast<String, dynamic>();
    final slotState =
        (_hasOutcomeField(rawOutcome, 'slotState')
            ? _parseSlotState(rawOutcome!['slotState'])
            : null) ??
        runArtifacts?.slotState ??
        fallbackSlotState ??
        const SlotStateSnapshot();
    final evidenceLedger =
        (_hasOutcomeField(rawOutcome, 'evidenceLedger')
            ? _parseEvidenceLedger(rawOutcome!['evidenceLedger'])
            : null) ??
        ((runArtifacts != null && runArtifacts.evidenceLedger.isNotEmpty)
            ? runArtifacts.evidenceLedger
            : null) ??
        fallbackEvidenceLedger;
    final answerEvidenceBindings =
        (_hasOutcomeField(rawOutcome, 'answerEvidenceBindings')
            ? _parseAnswerEvidenceBindings(
                rawOutcome!['answerEvidenceBindings'],
              )
            : null) ??
        ((runArtifacts != null &&
                runArtifacts.answerEvidenceBindings.isNotEmpty)
            ? runArtifacts.answerEvidenceBindings
            : null) ??
        fallbackAnswerEvidenceBindings;
    final evidenceEvaluation =
        (_hasOutcomeField(rawOutcome, 'evidenceEvaluation')
            ? _parseEvidenceEvaluation(
                rawOutcome!['evidenceEvaluation'],
                evidenceLedger: evidenceLedger,
              )
            : null) ??
        _parseEvidenceEvaluation(
          structured['evidenceEvaluation'] ??
              runArtifacts?.diagnostics['evidenceEvaluation'] ??
              ((structured['webEvidenceGate'] as Map?)?['evaluation']),
          evidenceLedger: evidenceLedger,
        ) ??
        fallbackEvidenceEvaluation ??
        const EvidenceEvaluationResult();
    final aggregationState =
        (_hasOutcomeField(rawOutcome, 'aggregationState')
            ? _parseAggregationState(rawOutcome!['aggregationState'])
            : null) ??
        _parseAggregationState(structured['aggregationState']) ??
        fallbackAggregationState ??
        const AggregationState();
    final conversationStateDecision =
        (_hasOutcomeField(rawOutcome, 'conversationStateDecision')
            ? _parseConversationStateDecision(
                rawOutcome!['conversationStateDecision'],
                groundedSlotState: slotState,
              )
            : null) ??
        _parseConversationStateDecision(
          structured['conversationStateDecision'],
          groundedSlotState: slotState,
        ) ??
        fallbackConversationStateDecision;
    final synthesisReadiness =
        _reconcileSynthesisReadiness(
          parsed:
              (_hasOutcomeField(rawOutcome, 'synthesisReadiness')
                  ? _parseSynthesisReadiness(rawOutcome!['synthesisReadiness'])
                  : null) ??
              _parseSynthesisReadiness(structured['synthesisReadiness']),
          fallback: fallbackSynthesisReadiness,
          aggregationState: aggregationState,
          conversationStateDecision: conversationStateDecision,
          runArtifacts: runArtifacts,
        ) ??
        const SynthesisReadinessResult();
    final domainPolicyBundle =
        (_hasOutcomeField(rawOutcome, 'domainPolicyBundle')
            ? _parseDomainPolicyBundle(rawOutcome!['domainPolicyBundle'])
            : null) ??
        runArtifacts?.domainPolicyBundle ??
        fallbackDomainPolicyBundle;
    final processJournal =
        (_hasOutcomeField(rawOutcome, 'processJournal')
            ? _parseProcessJournal(rawOutcome!['processJournal'])
            : null) ??
        ((runArtifacts != null && runArtifacts.processJournal.isNotEmpty)
            ? runArtifacts.processJournal
            : null) ??
        fallbackProcessJournal;
    final liveCursor =
        (_hasOutcomeField(rawOutcome, 'liveCursor')
            ? _parseProcessJournalEvent(rawOutcome!['liveCursor'])
            : null) ??
        runArtifacts?.liveCursor ??
        fallbackLiveCursor;
    return AnswerOutcomeSnapshot(
      slotState: slotState,
      evidenceLedger: evidenceLedger,
      answerEvidenceBindings: answerEvidenceBindings,
      evidenceEvaluation: evidenceEvaluation,
      aggregationState: aggregationState,
      synthesisReadiness: synthesisReadiness,
      conversationStateDecision: conversationStateDecision,
      domainPolicyBundle: domainPolicyBundle,
      processJournal: processJournal,
      liveCursor: liveCursor,
    );
  }

  bool _hasOutcomeField(Map<String, dynamic>? rawOutcome, String key) =>
      rawOutcome != null && rawOutcome.containsKey(key);

  SlotStateSnapshot? _parseSlotState(Object? raw) {
    if (raw is! Map) return null;
    try {
      return SlotStateSnapshot.fromJson(raw.cast<String, dynamic>());
    } catch (_) {
      return null;
    }
  }

  List<EvidenceLedgerEntry>? _parseEvidenceLedger(Object? raw) {
    if (raw is! List) return null;
    try {
      return raw
          .whereType<Map>()
          .map(
            (item) =>
                EvidenceLedgerEntry.fromJson(item.cast<String, dynamic>()),
          )
          .toList(growable: false);
    } catch (_) {
      return null;
    }
  }

  List<AnswerEvidenceBinding>? _parseAnswerEvidenceBindings(Object? raw) {
    if (raw is! List) return null;
    try {
      return raw
          .whereType<Map>()
          .map(
            (item) =>
                AnswerEvidenceBinding.fromJson(item.cast<String, dynamic>()),
          )
          .toList(growable: false);
    } catch (_) {
      return null;
    }
  }

  AggregationState? _parseAggregationState(Object? raw) {
    if (raw is! Map) return null;
    try {
      return AggregationState.fromJson(raw.cast<String, dynamic>());
    } catch (_) {
      return null;
    }
  }

  EvidenceEvaluationResult? _parseEvidenceEvaluation(
    Object? raw, {
    required List<EvidenceLedgerEntry> evidenceLedger,
  }) {
    if (raw is! Map) return null;
    try {
      final json = raw.cast<String, dynamic>();
      return EvidenceEvaluationResult(
        entries: evidenceLedger,
        coverageScore: ((json['coverageScore'] as num?) ?? 0).toDouble(),
        authorityScore: ((json['authorityScore'] as num?) ?? 0).toDouble(),
        relevanceScore: ((json['relevanceScore'] as num?) ?? 0).toDouble(),
        freshnessHours: (json['freshnessHours'] as num?)?.toInt() ?? 0,
        status: parseEvidenceStatus((json['status'] as String?) ?? ''),
        passed: json['passed'] == true,
        authoritySatisfied: json['authoritySatisfied'] == true,
        freshnessSatisfied: json['freshnessSatisfied'] == true,
        evidenceRequired: json['evidenceRequired'] == true,
        coveredDimensions: _stringList(json['coveredDimensions']),
        coveredQueryTaskIds: _stringList(json['coveredQueryTaskIds']),
        blockingDimensions: _stringList(json['blockingDimensions']),
        missingDimensions: _stringList(json['missingDimensions']),
        summary: (json['summary'] as String?) ?? '',
      );
    } catch (_) {
      return null;
    }
  }

  ConversationStateDecision? _parseConversationStateDecision(
    Object? raw, {
    required SlotStateSnapshot groundedSlotState,
  }) {
    if (raw is! Map) return null;
    try {
      final dto = ConversationStateDecisionDto.fromJson(
        raw.cast<String, dynamic>(),
      );
      return ConversationStateDecision(
        nextAction: dto.nextAction,
        finalAnswerMode: dto.finalAnswerMode,
        answerEligibility: dto.answerEligibility,
        slotState: groundedSlotState,
        missingCriticalSlots: dto.missingCriticalSlots,
        askUser: dto.askUser,
        qualityGates: dto.qualityGates,
        finalAnswerReady: dto.finalAnswerReady,
      );
    } catch (_) {
      return null;
    }
  }

  SynthesisReadinessResult? _parseSynthesisReadiness(Object? raw) {
    if (raw is! Map) return null;
    try {
      return SynthesisReadinessResult.fromJson(raw.cast<String, dynamic>());
    } catch (_) {
      return null;
    }
  }

  SynthesisReadinessResult? _reconcileSynthesisReadiness({
    SynthesisReadinessResult? parsed,
    SynthesisReadinessResult? fallback,
    AggregationState? aggregationState,
    ConversationStateDecision? conversationStateDecision,
    RunArtifacts? runArtifacts,
  }) {
    final candidate = parsed ?? fallback;
    final finalAnswerReady =
        conversationStateDecision?.finalAnswerReady == true ||
        aggregationState?.finalAnswerReady == true ||
        (runArtifacts?.displayMarkdown.trim().isNotEmpty ?? false) ||
        (runArtifacts?.displayPlainText.trim().isNotEmpty ?? false);
    if (!finalAnswerReady) {
      return candidate;
    }
    return SynthesisReadinessResult(
      ready: true,
      reason: (candidate?.reason.trim().isNotEmpty ?? false)
          ? candidate!.reason.trim()
          : 'final_answer_materialized',
      gapFillTask: candidate?.gapFillTask,
    );
  }

  DomainPolicyBundle? _parseDomainPolicyBundle(Object? raw) {
    if (raw is! Map) return null;
    try {
      return DomainPolicyBundle.fromJson(raw.cast<String, dynamic>());
    } catch (_) {
      return null;
    }
  }

  List<ProcessJournalEvent>? _parseProcessJournal(Object? raw) {
    if (raw is! List) return null;
    try {
      return raw
          .whereType<Map>()
          .map(
            (item) =>
                ProcessJournalEvent.fromJson(item.cast<String, dynamic>()),
          )
          .toList(growable: false);
    } catch (_) {
      return null;
    }
  }

  ProcessJournalEvent? _parseProcessJournalEvent(Object? raw) {
    if (raw is! Map) return null;
    try {
      return ProcessJournalEvent.fromJson(raw.cast<String, dynamic>());
    } catch (_) {
      return null;
    }
  }

  List<String> _stringList(Object? value) {
    if (value is! List) return const <String>[];
    return value
        .map((item) => item.toString().trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
  }
}
