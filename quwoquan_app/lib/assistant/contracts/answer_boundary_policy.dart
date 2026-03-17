export 'package:quwoquan_app/assistant/generated/contracts/answer_boundary_policy.g.dart';

import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/generated/contracts/answer_boundary_policy.g.dart';

class AnswerBoundaryPolicy extends AnswerBoundaryPolicyDto {
  const AnswerBoundaryPolicy({
    super.evidenceRequired = false,
    super.authorityRequired = false,
    super.requireToolResultBeforeSynthesis = false,
    super.allowBoundedAnswer = true,
    super.freshnessHoursMax = 72,
    super.authorityDomains = const <String>[],
    super.requiredDimensions = const <String>[],
    super.blockingDimensions = const <String>[],
    super.expansionPolicy = ContextScopeExpansionPolicy.expandScopeAndRequery,
    super.insufficiencyReason = PlannerReasonCode.needMoreEvidence,
    super.summary = '',
  });

  factory AnswerBoundaryPolicy.fromJson(Map<String, dynamic> json) {
    final dto = AnswerBoundaryPolicyDto.fromJson(json);
    return AnswerBoundaryPolicy(
      evidenceRequired: dto.evidenceRequired,
      authorityRequired: dto.authorityRequired,
      requireToolResultBeforeSynthesis: dto.requireToolResultBeforeSynthesis,
      allowBoundedAnswer: dto.allowBoundedAnswer,
      freshnessHoursMax: dto.freshnessHoursMax,
      authorityDomains: dto.authorityDomains,
      requiredDimensions: dto.requiredDimensions,
      blockingDimensions: dto.blockingDimensions,
      expansionPolicy: dto.expansionPolicy,
      insufficiencyReason: dto.insufficiencyReason,
      summary: dto.summary,
    );
  }
}
