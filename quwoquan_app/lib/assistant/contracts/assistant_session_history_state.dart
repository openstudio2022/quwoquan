import 'package:quwoquan_app/assistant/contracts/preference_fact.dart';
import 'package:quwoquan_app/assistant/contracts/skill_synthesis_contract.dart';

class AssistantSkillHistorySummary {
  const AssistantSkillHistorySummary({
    required this.skillId,
    this.role = 'supporting',
    this.summary = '',
    this.status = '',
    this.answerReady = false,
    this.acceptedEvidenceCount = 0,
  });

  final String skillId;
  final String role;
  final String summary;
  final String status;
  final bool answerReady;
  final int acceptedEvidenceCount;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'skillId': skillId,
        'role': role,
        'summary': summary,
        'status': status,
        'answerReady': answerReady,
        'acceptedEvidenceCount': acceptedEvidenceCount,
      };

  factory AssistantSkillHistorySummary.fromJson(Map<String, dynamic> json) {
    return AssistantSkillHistorySummary(
      skillId: (json['skillId'] as String?)?.trim() ?? '',
      role: (json['role'] as String?)?.trim() ?? 'supporting',
      summary: (json['summary'] as String?)?.trim() ?? '',
      status: (json['status'] as String?)?.trim() ?? '',
      answerReady: json['answerReady'] == true,
      acceptedEvidenceCount:
          (json['acceptedEvidenceCount'] as num?)?.toInt() ?? 0,
    );
  }
}

class AssistantSkillPendingState {
  const AssistantSkillPendingState({
    required this.skillId,
    this.role = 'supporting',
    this.summary = '',
    this.status = '',
    this.nextAction = '',
    this.missingSlots = const <String>[],
    this.failureReason = '',
  });

  final String skillId;
  final String role;
  final String summary;
  final String status;
  final String nextAction;
  final List<String> missingSlots;
  final String failureReason;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'skillId': skillId,
        'role': role,
        'summary': summary,
        'status': status,
        'nextAction': nextAction,
        'missingSlots': missingSlots,
        'failureReason': failureReason,
      };

  factory AssistantSkillPendingState.fromJson(Map<String, dynamic> json) {
    return AssistantSkillPendingState(
      skillId: (json['skillId'] as String?)?.trim() ?? '',
      role: (json['role'] as String?)?.trim() ?? 'supporting',
      summary: (json['summary'] as String?)?.trim() ?? '',
      status: (json['status'] as String?)?.trim() ?? '',
      nextAction: (json['nextAction'] as String?)?.trim() ?? '',
      missingSlots:
          (json['missingSlots'] as List?)
              ?.map((item) => item.toString().trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      failureReason: (json['failureReason'] as String?)?.trim() ?? '',
    );
  }
}

class AssistantSessionHistoryState {
  const AssistantSessionHistoryState({
    this.sessionSummary = '',
    this.completedSkillSummaries = const <AssistantSkillHistorySummary>[],
    this.pendingSkillStates = const <AssistantSkillPendingState>[],
    this.userPreferences = const <PreferenceFact>[],
    this.lastAcceptedEvidenceSummary = '',
  });

  final String sessionSummary;
  final List<AssistantSkillHistorySummary> completedSkillSummaries;
  final List<AssistantSkillPendingState> pendingSkillStates;
  final List<PreferenceFact> userPreferences;
  final String lastAcceptedEvidenceSummary;

  bool get isEmpty =>
      sessionSummary.trim().isEmpty &&
      completedSkillSummaries.isEmpty &&
      pendingSkillStates.isEmpty &&
      userPreferences.isEmpty &&
      lastAcceptedEvidenceSummary.trim().isEmpty;

  Map<String, dynamic> toJson() => <String, dynamic>{
        if (sessionSummary.trim().isNotEmpty) 'sessionSummary': sessionSummary,
        if (completedSkillSummaries.isNotEmpty)
          'completedSkillSummaries': completedSkillSummaries
              .map((item) => item.toJson())
              .toList(growable: false),
        if (pendingSkillStates.isNotEmpty)
          'pendingSkillStates': pendingSkillStates
              .map((item) => item.toJson())
              .toList(growable: false),
        if (userPreferences.isNotEmpty)
          'userPreferences': userPreferences
              .map((item) => item.toJson())
              .toList(growable: false),
        if (lastAcceptedEvidenceSummary.trim().isNotEmpty)
          'lastAcceptedEvidenceSummary': lastAcceptedEvidenceSummary,
      };

  factory AssistantSessionHistoryState.fromJson(Map<String, dynamic> json) {
    return AssistantSessionHistoryState(
      sessionSummary: (json['sessionSummary'] as String?)?.trim() ?? '',
      completedSkillSummaries:
          _completedSkillSummaries(json['completedSkillSummaries']),
      pendingSkillStates: _pendingSkillStates(json['pendingSkillStates']),
      userPreferences: _preferenceFacts(json['userPreferences']),
      lastAcceptedEvidenceSummary:
          (json['lastAcceptedEvidenceSummary'] as String?)?.trim() ?? '',
    );
  }

  factory AssistantSessionHistoryState.fromSkillSynthesis({
    required SkillSynthesisInput input,
    required SkillSynthesisOutput output,
    required List<PreferenceFact> userPreferences,
  }) {
    final completed = <AssistantSkillHistorySummary>[];
    final pending = <AssistantSkillPendingState>[];
    for (final result in input.skillResults) {
      final skillId = result.skillId.trim();
      if (skillId.isEmpty) {
        continue;
      }
      final acceptedEvidenceCount = result.acceptedEvidence.length;
      final isCompleted =
          result.answerReady &&
          result.failureReason.trim().isEmpty &&
          result.missingSlots.isEmpty &&
          !result.hasPendingWork;
      if (isCompleted) {
        completed.add(
          AssistantSkillHistorySummary(
            skillId: skillId,
            role: result.role.trim().isNotEmpty ? result.role.trim() : 'supporting',
            summary: result.summary.trim(),
            status: result.status.trim(),
            answerReady: true,
            acceptedEvidenceCount: acceptedEvidenceCount,
          ),
        );
      } else {
        pending.add(
          AssistantSkillPendingState(
            skillId: skillId,
            role: result.role.trim().isNotEmpty ? result.role.trim() : 'supporting',
            summary: result.summary.trim(),
            status: result.status.trim(),
            nextAction: output.nextAction.trim(),
            missingSlots: result.missingSlots,
            failureReason: result.failureReason.trim(),
          ),
        );
      }
    }
    final pendingSkillIds = pending.map((item) => item.skillId).toSet();
    for (final unresolvedSkill in output.unresolvedSkills) {
      final skillId = unresolvedSkill.trim();
      if (skillId.isEmpty || pendingSkillIds.contains(skillId)) {
        continue;
      }
      pending.add(
        AssistantSkillPendingState(
          skillId: skillId,
          status: output.partialCompletionState.trim(),
          nextAction: output.nextAction.trim(),
          summary: output.summary.trim(),
        ),
      );
    }
    return AssistantSessionHistoryState(
      sessionSummary: output.summary.trim().isNotEmpty
          ? output.summary.trim()
          : input.sessionSummary.trim(),
      completedSkillSummaries: completed,
      pendingSkillStates: pending,
      userPreferences: _dedupePreferenceFacts(userPreferences),
      lastAcceptedEvidenceSummary:
          _buildAcceptedEvidenceSummary(input.skillResults),
    );
  }

  AssistantSessionHistoryState mergeWith(
    AssistantSessionHistoryState other, {
    int maxSkillEntries = 8,
    int maxPreferenceFacts = 12,
  }) {
    if (other.isEmpty) {
      return this;
    }
    final completedBySkillId = <String, AssistantSkillHistorySummary>{};
    for (final item in other.completedSkillSummaries) {
      final skillId = item.skillId.trim();
      if (skillId.isEmpty) continue;
      completedBySkillId[skillId] = item;
    }
    for (final item in completedSkillSummaries) {
      final skillId = item.skillId.trim();
      if (skillId.isEmpty || completedBySkillId.containsKey(skillId)) {
        continue;
      }
      completedBySkillId[skillId] = item;
    }

    final pendingBySkillId = <String, AssistantSkillPendingState>{};
    for (final item in other.pendingSkillStates) {
      final skillId = item.skillId.trim();
      if (skillId.isEmpty) continue;
      pendingBySkillId[skillId] = item;
    }
    for (final item in pendingSkillStates) {
      final skillId = item.skillId.trim();
      if (skillId.isEmpty || pendingBySkillId.containsKey(skillId)) {
        continue;
      }
      pendingBySkillId[skillId] = item;
    }

    return AssistantSessionHistoryState(
      sessionSummary: other.sessionSummary.trim().isNotEmpty
          ? other.sessionSummary.trim()
          : sessionSummary.trim(),
      completedSkillSummaries:
          completedBySkillId.values.take(maxSkillEntries).toList(growable: false),
      pendingSkillStates:
          pendingBySkillId.values.take(maxSkillEntries).toList(growable: false),
      userPreferences: _mergePreferenceFacts(
        userPreferences,
        other.userPreferences,
        maxPreferenceFacts: maxPreferenceFacts,
      ),
      lastAcceptedEvidenceSummary:
          other.lastAcceptedEvidenceSummary.trim().isNotEmpty
          ? other.lastAcceptedEvidenceSummary.trim()
          : lastAcceptedEvidenceSummary.trim(),
    );
  }

  static List<AssistantSkillHistorySummary> _completedSkillSummaries(
    Object? raw,
  ) {
    final items = raw is List ? raw : const <dynamic>[];
    return items
        .whereType<Map>()
        .map((item) => AssistantSkillHistorySummary.fromJson(item.cast<String, dynamic>()))
        .where((item) => item.skillId.trim().isNotEmpty)
        .toList(growable: false);
  }

  static List<AssistantSkillPendingState> _pendingSkillStates(
    Object? raw,
  ) {
    final items = raw is List ? raw : const <dynamic>[];
    return items
        .whereType<Map>()
        .map((item) => AssistantSkillPendingState.fromJson(item.cast<String, dynamic>()))
        .where((item) => item.skillId.trim().isNotEmpty)
        .toList(growable: false);
  }

  static List<PreferenceFact> _preferenceFacts(Object? raw) {
    final items = raw is List ? raw : const <dynamic>[];
    return items
        .whereType<Map>()
        .map((item) => PreferenceFact.fromJson(item.cast<String, dynamic>()))
        .where((item) => item.key.trim().isNotEmpty && item.value.trim().isNotEmpty)
        .toList(growable: false);
  }

  static List<PreferenceFact> _dedupePreferenceFacts(
    List<PreferenceFact> facts,
  ) {
    final deduped = <String, PreferenceFact>{};
    for (final fact in facts) {
      final key = fact.factId.trim().isNotEmpty
          ? fact.factId.trim()
          : '${fact.scope.trim()}:${fact.key.trim()}:${fact.value.trim()}';
      if (key.trim().isEmpty || deduped.containsKey(key)) {
        continue;
      }
      deduped[key] = fact;
    }
    return deduped.values.toList(growable: false);
  }

  static List<PreferenceFact> _mergePreferenceFacts(
    List<PreferenceFact> existing,
    List<PreferenceFact> incoming, {
    required int maxPreferenceFacts,
  }) {
    final merged = <String, PreferenceFact>{};
    for (final fact in incoming) {
      final key = fact.factId.trim().isNotEmpty
          ? fact.factId.trim()
          : '${fact.scope.trim()}:${fact.key.trim()}:${fact.value.trim()}';
      if (key.trim().isEmpty) continue;
      merged[key] = fact;
    }
    for (final fact in existing) {
      final key = fact.factId.trim().isNotEmpty
          ? fact.factId.trim()
          : '${fact.scope.trim()}:${fact.key.trim()}:${fact.value.trim()}';
      if (key.trim().isEmpty || merged.containsKey(key)) {
        continue;
      }
      merged[key] = fact;
    }
    return merged.values.take(maxPreferenceFacts).toList(growable: false);
  }

  static String _buildAcceptedEvidenceSummary(
    List<SkillSynthesisSkillResult> skillResults,
  ) {
    final parts = <String>[];
    for (final result in skillResults) {
      if (result.acceptedEvidence.isEmpty) continue;
      final evidenceSnippets = result.acceptedEvidence
          .take(2)
          .map((item) {
            final map = item.cast<String, dynamic>();
            final candidates = <String>[
              (map['title'] as String?)?.trim() ?? '',
              (map['snippet'] as String?)?.trim() ?? '',
              (map['summary'] as String?)?.trim() ?? '',
              (map['source'] as String?)?.trim() ?? '',
              (map['url'] as String?)?.trim() ?? '',
            ];
            for (final candidate in candidates) {
              if (candidate.isNotEmpty) return candidate;
            }
            return '';
          })
          .where((item) => item.isNotEmpty)
          .toList(growable: false);
      if (evidenceSnippets.isEmpty) continue;
      parts.add('${result.skillId.trim()}: ${evidenceSnippets.join('；')}');
      if (parts.length >= 3) break;
    }
    return parts.join(' | ').trim();
  }
}
