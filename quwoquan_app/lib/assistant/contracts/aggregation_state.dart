export 'package:quwoquan_app/assistant/generated/contracts/aggregation_state.g.dart';

import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/generated/contracts/aggregation_state.g.dart';

class AggregationState extends AggregationStateDto {
  const AggregationState({
    super.allSkillsReady = false,
    super.blockingSkills = const <String>[],
    super.blockedBy = const <String, AggregationBlockingSkillStateDto>{},
    super.canGivePartialAnswer = false,
    super.needExpansion = false,
    super.expansionPlan = const AggregationExpansionPlanDto(),
    super.finalAnswerReady = false,
    super.finalAnswerMode = FinalAnswerMode.blocked,
    super.clarificationNeeded = false,
    super.answerOwner = '',
    super.clarificationSource = '',
    super.dependencies = const <String, AggregationDependencyChainDto>{},
  });

  factory AggregationState.fromJson(Map<String, dynamic> json) {
    final normalized = <String, dynamic>{
      ...json,
      'blockedBy': _normalizeBlockedBy(json['blockedBy']),
      'expansionPlan': _normalizeExpansionPlan(json['expansionPlan']),
      'dependencies': _normalizeDependencies(json['dependencies']),
      'finalAnswerMode':
          (json['finalAnswerMode'] as String?)?.trim().isNotEmpty == true
          ? (json['finalAnswerMode'] as String).trim()
          : FinalAnswerMode.blocked.wireName,
    };
    final dto = AggregationStateDto.fromJson(normalized);
    return AggregationState(
      allSkillsReady: dto.allSkillsReady,
      blockingSkills: dto.blockingSkills,
      blockedBy: dto.blockedBy,
      canGivePartialAnswer: dto.canGivePartialAnswer,
      needExpansion: dto.needExpansion,
      expansionPlan: dto.expansionPlan,
      finalAnswerReady: dto.finalAnswerReady,
      finalAnswerMode: dto.finalAnswerMode,
      clarificationNeeded: dto.clarificationNeeded,
      answerOwner: dto.answerOwner,
      clarificationSource: dto.clarificationSource,
      dependencies: dto.dependencies,
    );
  }

  String get finalAnswerModeWireName => finalAnswerMode.wireName;

  Map<String, String> get blockedByReasons => blockedBy.map(
    (key, value) => MapEntry(key, value.stopReason.wireName),
  );

  Map<String, List<String>> get dependencyRunIds => dependencies.map(
    (key, value) => MapEntry(key, value.runIds),
  );

  static Map<String, dynamic> _normalizeBlockedBy(Object? raw) {
    if (raw is! Map) {
      return const <String, dynamic>{};
    }
    final normalized = <String, dynamic>{};
    for (final entry in raw.entries) {
      final key = entry.key.toString().trim();
      if (key.isEmpty) continue;
      final value = entry.value;
      if (value is Map) {
        normalized[key] = <String, dynamic>{
          'stopReason':
              (value['stopReason'] as String?)?.trim() ??
              (value['reason'] as String?)?.trim() ??
              FinalAnswerMode.blocked.wireName,
          'answerReady': value['answerReady'] == true,
        };
        continue;
      }
      normalized[key] = <String, dynamic>{
        'stopReason': value?.toString().trim().isNotEmpty == true
            ? value.toString().trim()
            : FinalAnswerMode.blocked.wireName,
        'answerReady': false,
      };
    }
    return normalized;
  }

  static Map<String, dynamic> _normalizeExpansionPlan(Object? raw) {
    if (raw is! Map) {
      return const <String, dynamic>{};
    }
    return <String, dynamic>{
      'targetSkills':
          (raw['targetSkills'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          ((raw['target'] as String?)?.trim().isNotEmpty == true
              ? <String>[(raw['target'] as String).trim()]
              : const <String>[]),
      'policy':
          (raw['policy'] as String?)?.trim().isNotEmpty == true
          ? (raw['policy'] as String).trim()
          : ((raw['strategy'] as String?)?.trim() == 'broaden_or_retry'
                ? ContextScopeExpansionPolicy.expandScopeAndRequery.wireName
                : ContextScopeExpansionPolicy.none.wireName),
      'reasonCode':
          (raw['reasonCode'] as String?)?.trim().isNotEmpty == true
          ? (raw['reasonCode'] as String).trim()
          : PlannerReasonCode.needMoreEvidence.wireName,
    };
  }

  static Map<String, dynamic> _normalizeDependencies(Object? raw) {
    if (raw is! Map) {
      return const <String, dynamic>{};
    }
    final normalized = <String, dynamic>{};
    for (final entry in raw.entries) {
      final key = entry.key.toString().trim();
      if (key.isEmpty) continue;
      final value = entry.value;
      if (value is Map) {
        normalized[key] = <String, dynamic>{
          'runIds':
              (value['runIds'] as List?)
                  ?.whereType<String>()
                  .map((item) => item.trim())
                  .where((item) => item.isNotEmpty)
                  .toList(growable: false) ??
              const <String>[],
        };
        continue;
      }
      normalized[key] = <String, dynamic>{
        'runIds':
            (value as List?)
                ?.whereType<String>()
                .map((item) => item.trim())
                .where((item) => item.isNotEmpty)
                .toList(growable: false) ??
            const <String>[],
      };
    }
    return normalized;
  }
}
