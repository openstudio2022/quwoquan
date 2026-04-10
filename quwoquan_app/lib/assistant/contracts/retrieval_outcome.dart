import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';

const String assistantRetrievalOutcomeField = 'retrievalOutcome';
const String assistantAnswerGateDecisionField = 'answerGateDecision';

class RetrievalOutcome {
  const RetrievalOutcome({
    this.status = 'unknown',
    this.summary = '',
    this.evidenceRequired = false,
    this.authorityRequired = false,
    this.freshnessRequired = false,
    this.timeWindowRequired = false,
    this.hasToolResult = false,
    this.referenceCount = 0,
    this.processedDocumentCount = 0,
    this.acceptedDocumentCount = 0,
    this.coveredDimensions = const <String>[],
    this.missingDimensions = const <String>[],
    this.coveredQueryTaskIds = const <String>[],
    this.authorityDomains = const <String>[],
    this.authoritySatisfied = false,
    this.freshnessHoursMax = 72,
    this.freshnessHours = 0,
    this.freshnessKnown = false,
    this.freshnessSatisfied = false,
    this.timeWindowKnown = false,
    this.timeWindowSatisfied = true,
    this.evidencePassed = false,
    this.evidenceStatus = '',
    this.expansionReason = '',
    this.terminalPayloadComplete = true,
    this.degraded = false,
    this.retrievalProcessing = const RetrievalProcessingSnapshot(),
  });

  final String status;
  final String summary;
  final bool evidenceRequired;
  final bool authorityRequired;
  final bool freshnessRequired;
  final bool timeWindowRequired;
  final bool hasToolResult;
  final int referenceCount;
  final int processedDocumentCount;
  final int acceptedDocumentCount;
  final List<String> coveredDimensions;
  final List<String> missingDimensions;
  final List<String> coveredQueryTaskIds;
  final List<String> authorityDomains;
  final bool authoritySatisfied;
  final int freshnessHoursMax;
  final int freshnessHours;
  final bool freshnessKnown;
  final bool freshnessSatisfied;
  final bool timeWindowKnown;
  final bool timeWindowSatisfied;
  final bool evidencePassed;
  final String evidenceStatus;
  final String expansionReason;
  final bool terminalPayloadComplete;
  final bool degraded;
  final RetrievalProcessingSnapshot retrievalProcessing;

  bool get temporalRequirementSatisfied => timeWindowRequired
      ? (timeWindowKnown && timeWindowSatisfied)
      : (!freshnessRequired || freshnessSatisfied);

  bool get retrievalReady =>
      !degraded &&
      terminalPayloadComplete &&
      status == 'ready' &&
      (!evidenceRequired || evidencePassed) &&
      (!authorityRequired || authoritySatisfied) &&
      temporalRequirementSatisfied &&
      missingDimensions.isEmpty;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'status': status,
    'summary': summary,
    'evidenceRequired': evidenceRequired,
    'authorityRequired': authorityRequired,
    'freshnessRequired': freshnessRequired,
    'timeWindowRequired': timeWindowRequired,
    'hasToolResult': hasToolResult,
    'referenceCount': referenceCount,
    'processedDocumentCount': processedDocumentCount,
    'acceptedDocumentCount': acceptedDocumentCount,
    'coveredDimensions': coveredDimensions,
    'missingDimensions': missingDimensions,
    'coveredQueryTaskIds': coveredQueryTaskIds,
    'authorityDomains': authorityDomains,
    'authoritySatisfied': authoritySatisfied,
    'freshnessHoursMax': freshnessHoursMax,
    'freshnessHours': freshnessHours,
    'freshnessKnown': freshnessKnown,
    'freshnessSatisfied': freshnessSatisfied,
    'timeWindowKnown': timeWindowKnown,
    'timeWindowSatisfied': timeWindowSatisfied,
    'evidencePassed': evidencePassed,
    'evidenceStatus': evidenceStatus,
    'expansionReason': expansionReason,
    'terminalPayloadComplete': terminalPayloadComplete,
    'degraded': degraded,
    'retrievalProcessing': retrievalProcessing.toJson(),
  };

  factory RetrievalOutcome.fromJson(Map<String, dynamic> json) {
    return RetrievalOutcome(
      status: (json['status'] as String?)?.trim() ?? 'unknown',
      summary: (json['summary'] as String?)?.trim() ?? '',
      evidenceRequired: json['evidenceRequired'] == true,
      authorityRequired: json['authorityRequired'] == true,
      freshnessRequired: json['freshnessRequired'] == true,
      timeWindowRequired: json['timeWindowRequired'] == true,
      hasToolResult: json['hasToolResult'] == true,
      referenceCount: (json['referenceCount'] as num?)?.toInt() ?? 0,
      processedDocumentCount:
          (json['processedDocumentCount'] as num?)?.toInt() ?? 0,
      acceptedDocumentCount:
          (json['acceptedDocumentCount'] as num?)?.toInt() ?? 0,
      coveredDimensions: _stringList(json['coveredDimensions']),
      missingDimensions: _stringList(json['missingDimensions']),
      coveredQueryTaskIds: _stringList(json['coveredQueryTaskIds']),
      authorityDomains: _stringList(json['authorityDomains']),
      authoritySatisfied: json['authoritySatisfied'] == true,
      freshnessHoursMax: (json['freshnessHoursMax'] as num?)?.toInt() ?? 72,
      freshnessHours: (json['freshnessHours'] as num?)?.toInt() ?? 0,
      freshnessKnown: json['freshnessKnown'] == true,
      freshnessSatisfied: json['freshnessSatisfied'] == true,
      timeWindowKnown: json['timeWindowKnown'] == true,
      timeWindowSatisfied: json['timeWindowSatisfied'] != false,
      evidencePassed: json['evidencePassed'] == true,
      evidenceStatus: (json['evidenceStatus'] as String?)?.trim() ?? '',
      expansionReason: (json['expansionReason'] as String?)?.trim() ?? '',
      terminalPayloadComplete: json['terminalPayloadComplete'] != false,
      degraded: json['degraded'] == true,
      retrievalProcessing: json['retrievalProcessing'] is Map
          ? RetrievalProcessingSnapshot.fromJson(
              (json['retrievalProcessing'] as Map).cast<String, dynamic>(),
            )
          : const RetrievalProcessingSnapshot(),
    );
  }

  static List<String> _stringList(Object? value) {
    if (value is! List) return const <String>[];
    final seen = <String>{};
    final out = <String>[];
    for (final item in value) {
      final normalized = item?.toString().trim() ?? '';
      if (normalized.isEmpty || !seen.add(normalized)) {
        continue;
      }
      out.add(normalized);
    }
    return out;
  }
}

class AnswerGateDecision {
  const AnswerGateDecision({
    this.eligible = false,
    this.finalAnswerReady = false,
    this.reasonCode = '',
    this.reason = '',
    this.nextAction = '',
    this.answerEligibility = '',
    this.renderable = false,
    this.retrievalReady = false,
    this.terminalPayloadComplete = true,
    this.degraded = false,
    this.incomplete = false,
    this.coveredDimensions = const <String>[],
    this.missingDimensions = const <String>[],
    this.authoritySatisfied = false,
    this.freshnessSatisfied = false,
  });

  final bool eligible;
  final bool finalAnswerReady;
  final String reasonCode;
  final String reason;
  final String nextAction;
  final String answerEligibility;
  final bool renderable;
  final bool retrievalReady;
  final bool terminalPayloadComplete;
  final bool degraded;
  final bool incomplete;
  final List<String> coveredDimensions;
  final List<String> missingDimensions;
  final bool authoritySatisfied;
  final bool freshnessSatisfied;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'eligible': eligible,
    'finalAnswerReady': finalAnswerReady,
    'reasonCode': reasonCode,
    'reason': reason,
    'nextAction': nextAction,
    'answerEligibility': answerEligibility,
    'renderable': renderable,
    'retrievalReady': retrievalReady,
    'terminalPayloadComplete': terminalPayloadComplete,
    'degraded': degraded,
    'incomplete': incomplete,
    'coveredDimensions': coveredDimensions,
    'missingDimensions': missingDimensions,
    'authoritySatisfied': authoritySatisfied,
    'freshnessSatisfied': freshnessSatisfied,
  };

  factory AnswerGateDecision.fromJson(Map<String, dynamic> json) {
    return AnswerGateDecision(
      eligible: json['eligible'] == true,
      finalAnswerReady: json['finalAnswerReady'] == true,
      reasonCode: (json['reasonCode'] as String?)?.trim() ?? '',
      reason: (json['reason'] as String?)?.trim() ?? '',
      nextAction: (json['nextAction'] as String?)?.trim() ?? '',
      answerEligibility: (json['answerEligibility'] as String?)?.trim() ?? '',
      renderable: json['renderable'] == true,
      retrievalReady: json['retrievalReady'] == true,
      terminalPayloadComplete: json['terminalPayloadComplete'] != false,
      degraded: json['degraded'] == true,
      incomplete: json['incomplete'] == true,
      coveredDimensions: RetrievalOutcome._stringList(
        json['coveredDimensions'],
      ),
      missingDimensions: RetrievalOutcome._stringList(
        json['missingDimensions'],
      ),
      authoritySatisfied: json['authoritySatisfied'] == true,
      freshnessSatisfied: json['freshnessSatisfied'] == true,
    );
  }
}
