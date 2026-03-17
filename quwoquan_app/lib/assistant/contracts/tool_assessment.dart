export 'package:quwoquan_app/assistant/generated/contracts/tool_assessment.g.dart';

import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/generated/contracts/tool_assessment.g.dart';

class ToolAssessment extends ToolAssessmentDto {
  const ToolAssessment({
    required super.assessmentType,
    super.userMessage = '',
    super.shouldContinueLoop = true,
    super.gapFill = false,
    super.rewriteQuery = false,
    super.allowAnswerWithCurrentEvidence = false,
    super.reasonCode = PlannerReasonCode.assessmentUpdate,
    super.referenceCount = 0,
    super.queryCount = 0,
    super.coveredDimensions = const <String>[],
    super.missingDimensions = const <String>[],
  });

  factory ToolAssessment.fromJson(Map<String, dynamic> json) {
    final normalized = <String, dynamic>{
      ...json,
      if (json['assessmentType'] == null && json['type'] != null)
        'assessmentType': json['type'],
      if (json['reasonCode'] == null && json['reason'] != null)
        'reasonCode': json['reason'],
    };
    final dto = ToolAssessmentDto.fromJson(normalized);
    return ToolAssessment(
      assessmentType: dto.assessmentType,
      userMessage: dto.userMessage,
      shouldContinueLoop: dto.shouldContinueLoop,
      gapFill: dto.gapFill,
      rewriteQuery: dto.rewriteQuery,
      allowAnswerWithCurrentEvidence: dto.allowAnswerWithCurrentEvidence,
      reasonCode: dto.reasonCode,
      referenceCount: dto.referenceCount,
      queryCount: dto.queryCount,
      coveredDimensions: dto.coveredDimensions,
      missingDimensions: dto.missingDimensions,
    );
  }

  AssessmentType get type => assessmentType;
}
