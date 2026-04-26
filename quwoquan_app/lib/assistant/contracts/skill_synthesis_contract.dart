import 'package:quwoquan_app/assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_subagent_run_record.dart';
import 'package:quwoquan_app/assistant/contracts/skill_route_contract.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';

class SkillSynthesisTarget {
  const SkillSynthesisTarget({
    required this.skillId,
    this.role = 'supporting',
    this.priority = 0,
    this.reason = '',
  });

  final String skillId;
  final String role;
  final int priority;
  final String reason;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'skillId': skillId,
        'role': role,
        'priority': priority,
        'reason': reason,
      };

  factory SkillSynthesisTarget.fromJson(Map<String, dynamic> json) {
    return SkillSynthesisTarget(
      skillId: (json['skillId'] as String?)?.trim() ?? '',
      role: (json['role'] as String?)?.trim() ?? 'supporting',
      priority: (json['priority'] as num?)?.toInt() ?? 0,
      reason: (json['reason'] as String?)?.trim() ?? '',
    );
  }

  factory SkillSynthesisTarget.fromRouteTarget(SkillRouteTarget target) {
    return SkillSynthesisTarget(
      skillId: target.skillId.trim(),
      role: target.role.trim().isNotEmpty ? target.role.trim() : 'supporting',
      priority: target.priority,
      reason: target.routeNarrative.trim(),
    );
  }
}

class SkillSynthesisSkillResult {
  const SkillSynthesisSkillResult({
    required this.skillId,
    required this.status,
    required this.summary,
    this.role = 'supporting',
    this.acceptedEvidence = const <Map<String, dynamic>>[],
    this.rejectedEvidence = const <Map<String, dynamic>>[],
    this.missingSlots = const <String>[],
    this.failureReason = '',
    this.answerReady = false,
  });

  final String skillId;
  final String role;
  final String status;
  final String summary;
  final List<Map<String, dynamic>> acceptedEvidence;
  final List<Map<String, dynamic>> rejectedEvidence;
  final List<String> missingSlots;
  final String failureReason;
  final bool answerReady;

  bool get hasPendingWork =>
      missingSlots.isNotEmpty || failureReason.trim().isNotEmpty || !answerReady;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'skillId': skillId,
        'role': role,
        'status': status,
        'summary': summary,
        'acceptedEvidence': acceptedEvidence,
        'rejectedEvidence': rejectedEvidence,
        'missingSlots': missingSlots,
        'failureReason': failureReason,
        'answerReady': answerReady,
      };

  factory SkillSynthesisSkillResult.fromJson(Map<String, dynamic> json) {
    return SkillSynthesisSkillResult(
      skillId: (json['skillId'] as String?)?.trim() ?? '',
      role: (json['role'] as String?)?.trim() ?? 'supporting',
      status: (json['status'] as String?)?.trim() ?? '',
      summary: (json['summary'] as String?)?.trim() ?? '',
      acceptedEvidence: _mapList(json['acceptedEvidence']),
      rejectedEvidence: _mapList(json['rejectedEvidence']),
      missingSlots: _stringList(json['missingSlots']),
      failureReason: (json['failureReason'] as String?)?.trim() ?? '',
      answerReady: json['answerReady'] == true,
    );
  }
}

class SkillSynthesisInput {
  const SkillSynthesisInput({
    required this.userQuery,
    required this.routeNarrative,
    required this.selectedTargets,
    required this.skillResults,
    this.pendingClarifications = const <String>[],
    this.sessionSummary = '',
  });

  final String userQuery;
  final String routeNarrative;
  final List<SkillSynthesisTarget> selectedTargets;
  final List<SkillSynthesisSkillResult> skillResults;
  final List<String> pendingClarifications;
  final String sessionSummary;

  bool get hasPendingWork =>
      pendingClarifications.isNotEmpty ||
      skillResults.any((item) => item.hasPendingWork);

  Map<String, dynamic> toJson() => <String, dynamic>{
        'userQuery': userQuery,
        'routeNarrative': routeNarrative,
        'selectedTargets':
            selectedTargets.map((item) => item.toJson()).toList(growable: false),
        'skillResults':
            skillResults.map((item) => item.toJson()).toList(growable: false),
        'pendingClarifications': pendingClarifications,
        if (sessionSummary.trim().isNotEmpty) 'sessionSummary': sessionSummary,
        'hasPendingWork': hasPendingWork,
      };

  factory SkillSynthesisInput.fromJson(Map<String, dynamic> json) {
    return SkillSynthesisInput(
      userQuery: (json['userQuery'] as String?)?.trim() ?? '',
      routeNarrative: (json['routeNarrative'] as String?)?.trim() ?? '',
      selectedTargets: _targetList(json['selectedTargets']),
      skillResults: _skillResultList(json['skillResults']),
      pendingClarifications: _stringList(json['pendingClarifications']),
      sessionSummary: (json['sessionSummary'] as String?)?.trim() ?? '',
    );
  }

  factory SkillSynthesisInput.fromExecution({
    required String userQuery,
    required SkillRouteOutput skillRoute,
    required List<AssistantSubagentRunRecord> subagentRuns,
    SkillSynthesisSkillResult? primarySkillResult,
    String sessionSummary = '',
  }) {
    final selectedTargets = skillRoute.selectedTargets
        .map(SkillSynthesisTarget.fromRouteTarget)
        .where((item) => item.skillId.trim().isNotEmpty)
        .toList(growable: false);
    final targetBySkillId = <String, SkillSynthesisTarget>{
      for (final target in selectedTargets) target.skillId.trim(): target,
    };
    final resultsBySkillId = <String, SkillSynthesisSkillResult>{};
    if (primarySkillResult != null &&
        primarySkillResult.skillId.trim().isNotEmpty) {
      final skillId = primarySkillResult.skillId.trim();
      resultsBySkillId[skillId] = _resolveRoleForResult(
        result: primarySkillResult,
        role: targetBySkillId[skillId]?.role ?? primarySkillResult.role,
      );
    }
    for (final run in subagentRuns) {
      final skillId = run.domainId.trim();
      if (skillId.isEmpty) {
        continue;
      }
      resultsBySkillId[skillId] = _resolveRoleForResult(
        result: run.toSkillSynthesisSkillResult(
          role: targetBySkillId[skillId]?.role ?? 'supporting',
        ),
        role: targetBySkillId[skillId]?.role ?? 'supporting',
      );
    }
    return SkillSynthesisInput(
      userQuery: userQuery,
      routeNarrative: skillRoute.routeNarrative,
      selectedTargets: selectedTargets,
      skillResults: <SkillSynthesisSkillResult>[
        for (final target in selectedTargets)
          if (resultsBySkillId.containsKey(target.skillId.trim()))
            resultsBySkillId.remove(target.skillId.trim())!,
        ...resultsBySkillId.values,
      ],
      pendingClarifications: skillRoute.pendingClarifications
          .map((item) => item.trim())
          .where((item) => item.isNotEmpty)
          .toList(growable: false),
      sessionSummary: sessionSummary,
    );
  }
}

SkillSynthesisSkillResult _resolveRoleForResult({
  required SkillSynthesisSkillResult result,
  required String role,
}) {
  final resolvedRole = role.trim().isNotEmpty ? role.trim() : result.role.trim();
  return SkillSynthesisSkillResult(
    skillId: result.skillId,
    role: resolvedRole.isNotEmpty ? resolvedRole : 'supporting',
    status: result.status,
    summary: result.summary,
    acceptedEvidence: result.acceptedEvidence,
    rejectedEvidence: result.rejectedEvidence,
    missingSlots: result.missingSlots,
    failureReason: result.failureReason,
    answerReady: result.answerReady,
  );
}

class SkillSynthesisOutput {
  const SkillSynthesisOutput({
    required this.answerMarkdown,
    this.followUpSuggestions = const <String>[],
    this.partialCompletionState = 'complete',
    this.unresolvedSkills = const <String>[],
    this.nextAction = '',
    this.summary = '',
  });

  final String answerMarkdown;
  final List<String> followUpSuggestions;
  final String partialCompletionState;
  final List<String> unresolvedSkills;
  final String nextAction;
  final String summary;

  bool get isPartial =>
      partialCompletionState.trim() == 'partial' ||
      partialCompletionState.trim() == 'needs_clarification';

  Map<String, dynamic> toJson() => <String, dynamic>{
        'answerMarkdown': answerMarkdown,
        'followUpSuggestions': followUpSuggestions,
        'partialCompletionState': partialCompletionState,
        'unresolvedSkills': unresolvedSkills,
        'nextAction': nextAction,
        if (summary.trim().isNotEmpty) 'summary': summary,
      };

  factory SkillSynthesisOutput.fromJson(Map<String, dynamic> json) {
    return SkillSynthesisOutput(
      answerMarkdown: (json['answerMarkdown'] as String?)?.trim() ?? '',
      followUpSuggestions: _stringList(json['followUpSuggestions']),
      partialCompletionState:
          (json['partialCompletionState'] as String?)?.trim() ?? 'complete',
      unresolvedSkills: _stringList(json['unresolvedSkills']),
      nextAction: (json['nextAction'] as String?)?.trim() ?? '',
      summary: (json['summary'] as String?)?.trim() ?? '',
    );
  }

  factory SkillSynthesisOutput.fromStructuredAnswer({
    required Map<String, dynamic> answerPayload,
    required SkillSynthesisInput input,
    AggregationState aggregationState = const AggregationState(),
    SynthesisReadinessResult synthesisReadiness =
        const SynthesisReadinessResult(),
  }) {
    final answerMarkdown = _firstNonEmptyText(<String?>[
      _stringFromMap(answerPayload['skillSynthesis'], 'answerMarkdown'),
      (answerPayload['userMarkdown'] as String?)?.trim(),
      _stringFromMap(answerPayload['result'], 'text'),
      _stringFromMap(answerPayload['result'], 'summary'),
      (answerPayload['finalText'] as String?)?.trim(),
    ]);
    final nextAction = _stringFromMap(answerPayload['decision'], 'nextAction');
    final followUpSuggestions = _stringList(answerPayload['actionHints']);
    final followUpPrompt = (answerPayload['followupPrompt'] as String?)?.trim() ?? '';
    final resolvedFollowUpSuggestions = followUpSuggestions.isNotEmpty
        ? followUpSuggestions
        : (followUpPrompt.isNotEmpty ? <String>[followUpPrompt] : const <String>[]);
    final unresolvedSkills = _stringList(
      _mapValue(answerPayload['skillSynthesis'])['unresolvedSkills'],
    );
    final combinedUnresolvedSkills = <String>{
      ...unresolvedSkills,
      ...input.skillResults
          .where((item) => item.hasPendingWork)
          .map((item) => item.skillId.trim())
          .where((item) => item.isNotEmpty),
    }.toList(growable: false);
    final partialCompletionState = _resolvePartialState(
      answerPayload: answerPayload,
      aggregationState: aggregationState,
      synthesisReadiness: synthesisReadiness,
      input: input,
      unresolvedSkills: combinedUnresolvedSkills,
    );
    return SkillSynthesisOutput(
      answerMarkdown: answerMarkdown,
      followUpSuggestions: resolvedFollowUpSuggestions,
      partialCompletionState: partialCompletionState,
      unresolvedSkills: combinedUnresolvedSkills,
      nextAction: nextAction,
      summary: _firstNonEmptyText(<String?>[
        _stringFromMap(answerPayload['skillSynthesis'], 'summary'),
        _stringFromMap(answerPayload['result'], 'summary'),
        (answerPayload['reasonShort'] as String?)?.trim(),
        answerMarkdown,
      ]),
    );
  }
}

extension AssistantSubagentRunRecordSkillSynthesis on AssistantSubagentRunRecord {
  SkillSynthesisSkillResult toSkillSynthesisSkillResult({
    String role = 'supporting',
  }) {
    return SkillSynthesisSkillResult(
      skillId: domainId.trim(),
      role: role.trim().isNotEmpty ? role.trim() : 'supporting',
      status: status.trim(),
      summary: summary.trim(),
      acceptedEvidence: acceptedEvidence,
      rejectedEvidence: rejectedEvidence,
      missingSlots: missingSlots,
      failureReason: failureReason.trim(),
      answerReady: answerReady,
    );
  }
}

List<String> _stringList(Object? value) {
  if (value is List) {
    return value
        .whereType<Object?>()
        .map((item) => item.toString().trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
  }
  if (value is String && value.trim().isNotEmpty) {
    return <String>[value.trim()];
  }
  return const <String>[];
}

List<Map<String, dynamic>> _mapList(Object? value) {
  if (value is List) {
    return value
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .toList(growable: false);
  }
  return const <Map<String, dynamic>>[];
}

List<SkillSynthesisTarget> _targetList(Object? value) {
  return _mapList(value)
      .map(SkillSynthesisTarget.fromJson)
      .toList(growable: false);
}

List<SkillSynthesisSkillResult> _skillResultList(Object? value) {
  return _mapList(value)
      .map(SkillSynthesisSkillResult.fromJson)
      .toList(growable: false);
}

Map<String, dynamic> _mapValue(Object? value) {
  if (value is Map) {
    return value.cast<String, dynamic>();
  }
  return const <String, dynamic>{};
}

String _stringFromMap(Object? value, String key) {
  if (value is Map) {
    final raw = value[key];
    if (raw is String) return raw.trim();
    return raw?.toString().trim() ?? '';
  }
  return '';
}

String _firstNonEmptyText(List<String?> values) {
  for (final value in values) {
    final text = value?.trim() ?? '';
    if (text.isNotEmpty) return text;
  }
  return '';
}

String _resolvePartialState({
  required Map<String, dynamic> answerPayload,
  required AggregationState aggregationState,
  required SynthesisReadinessResult synthesisReadiness,
  required SkillSynthesisInput input,
  required List<String> unresolvedSkills,
}) {
  final explicit = _stringFromMap(answerPayload['skillSynthesis'], 'partialCompletionState');
  if (explicit.isNotEmpty) return explicit;
  if (input.pendingClarifications.isNotEmpty) return 'needs_clarification';
  if (unresolvedSkills.isNotEmpty) return 'partial';
  if (aggregationState.finalAnswerReady) return 'complete';
  if (aggregationState.canGivePartialAnswer) return 'partial';
  if (synthesisReadiness.ready) return 'complete';
  return 'partial';
}
