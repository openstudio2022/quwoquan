import 'planner_contracts.dart';

// Runtime-only protocol boundary:
// - This wrapper is derived from planner runtime enums and is not a shared
//   metadata-owned contract.
// - It must stay as an internal protocol adapter until the same semantics are
//   explicitly modeled in assistant metadata/codegen.
class ProcessProtocolCode {
  const ProcessProtocolCode({
    required this.phaseId,
    required this.actionCode,
    required this.reasonCode,
    PlannerPhaseId? stage,
  }) : stage = stage ?? phaseId;

  final PlannerPhaseId stage;
  final PlannerPhaseId phaseId;
  final PlannerActionCode actionCode;
  final PlannerReasonCode reasonCode;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'stage': stage.wireName,
        'phaseId': phaseId.wireName,
        'actionCode': actionCode.wireName,
        'reasonCode': reasonCode.wireName,
      };

  factory ProcessProtocolCode.fromWire({
    required String stage,
    required String phaseId,
    required String actionCode,
    required String reasonCode,
  }) {
    final parsedPhase = parsePlannerPhaseId(phaseId);
    return ProcessProtocolCode(
      stage: parsePlannerPhaseId(stage),
      phaseId: parsedPhase == PlannerPhaseId.unknown
          ? parsePlannerPhaseId(stage)
          : parsedPhase,
      actionCode: parsePlannerActionCode(actionCode),
      reasonCode: parsePlannerReasonCode(reasonCode),
    );
  }
}
