import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart'
    show SlotStateSnapshot;
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';

/// LLM/编排 answer 载荷：与 [assistant_turn/schema.yaml] 中 `AssistantTurnOutput` 同源。
///
/// - [asTypedOutput]：metadata 生成类型，优先用于只读结构化字段。
/// - `*Map` getter：保留 wire 上 **未收入 schema 的扩展键**（如 spread `...apv.decisionMap`）。
class AssistantAnswerPayloadReadView {
  AssistantAnswerPayloadReadView(Map<String, dynamic> raw) : _raw = raw;

  final Map<String, dynamic> _raw;

  /// 由 SSOT `AssistantTurnOutput.fromJson` 解析；调用方勿在持有本 view 期间再改 `_raw`。
  AssistantTurnOutput get asTypedOutput => AssistantTurnOutput.fromJson(_raw);

  Map<String, dynamic> get decisionMap =>
      (_raw['decision'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  Map<String, dynamic> get diagnosticsMap =>
      (_raw['diagnostics'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  Map<String, dynamic> get resultMap =>
      (_raw['result'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  Map<String, dynamic> get askUserMap =>
      (_raw['askUser'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  AssistantTurnResult get resultTyped => asTypedOutput.result;

  AssistantTurnDiagnostics get diagnosticsTyped => asTypedOutput.diagnostics;

  SlotStateSnapshot get slotStateTyped => asTypedOutput.slotState;

  String get nextActionWireName => asTypedOutput.decision.nextAction.wireName;

  String get slotStateFailureReason =>
      (_raw['slotState'] as Map?)?['failureReason']?.toString().trim() ?? '';

  String get diagnosticsFailureReason =>
      (_raw['diagnostics'] as Map?)?['failureReason']?.toString().trim() ?? '';

  List<String> get slotStateMissingSlots => asTypedOutput.slotState.missingSlots;

  List<String> get topLevelMissingSlots =>
      (_raw['missingSlots'] as List?)
          ?.map((item) => item.toString().trim())
          .where((item) => item.isNotEmpty)
          .toList(growable: false) ??
      const <String>[];

  /// `diagnostics.emergedTags`（与 metadata [AssistantTurnDiagnostics] 一致）。
  List<Map<String, dynamic>> get diagnosticsEmergedTagMaps =>
      asTypedOutput.diagnostics.emergedTags;

  /// `subagentPlan` 每项的 wire map（与 [SubagentPlan] 同源）。
  List<Map<String, dynamic>> get subagentPlanMaps =>
      asTypedOutput.subagentPlan
          .map((p) => p.toJson())
          .toList(growable: false);

  /// `evidence` wire maps。
  List<Map<String, dynamic>> get evidenceMaps =>
      asTypedOutput.evidence
          .map((e) => e.toJson())
          .toList(growable: false);

  /// `reasoningBasis` wire maps。
  List<Map<String, dynamic>> get reasoningBasisMaps =>
      asTypedOutput.reasoningBasis
          .map((e) => e.toJson())
          .toList(growable: false);

  Map<String, dynamic> get modelSelfScoreMap => asTypedOutput.modelSelfScore.toJson();

  String parseStatusOrDefault(String def) {
    final top = (_raw['parseStatus'] as String?)?.trim();
    if (top != null && top.isNotEmpty) return top;
    final d = asTypedOutput.diagnostics.parseStatus.trim();
    if (d.isNotEmpty) return d;
    return def;
  }

  Map<String, dynamic> get answerProcessingMap =>
      asTypedOutput.answerProcessing.toJson();

  Map<String, dynamic> get displayStateMap => asTypedOutput.displayState.toJson();

  Map<String, dynamic> get retrievalProcessingMap =>
      asTypedOutput.retrievalProcessing.toJson();

  Map<String, dynamic> get slotStateMap => asTypedOutput.slotState.toJson();

  Map<String, dynamic> get understandingSnapshotMap =>
      asTypedOutput.understandingSnapshot.toJson();

  Map<String, dynamic> get historicalThinkingSnapshotMap =>
      asTypedOutput.historicalThinkingSnapshot.toJson();

  Map<String, dynamic> get selfCheckMap => asTypedOutput.selfCheck.toJson();

  String get followupPromptTrimmed => asTypedOutput.followupPrompt.trim();

  bool get hasNonEmptyContractId => asTypedOutput.contractId.trim().isNotEmpty;

  String get contractIdTrimmed => asTypedOutput.contractId.trim();

  bool get hasNonEmptyPhaseId =>
      asTypedOutput.phaseId.wireName.trim().isNotEmpty;

  String get phaseIdTrimmed => asTypedOutput.phaseId.wireName.trim();

  bool get hasNonEmptyActionCode =>
      asTypedOutput.actionCode.wireName.trim().isNotEmpty;

  String get actionCodeTrimmed => asTypedOutput.actionCode.wireName.trim();

  bool get hasNonEmptyReasonCode =>
      asTypedOutput.reasonCode.wireName.trim().isNotEmpty;

  String get reasonCodeTrimmed => asTypedOutput.reasonCode.wireName.trim();

  String get messageKindTrimmed => asTypedOutput.messageKind.wireName.trim();

  String get userMarkdownTrimmed => asTypedOutput.userMarkdown.trim();

  String get resultInterpretationTrimmed =>
      asTypedOutput.result.interpretation.trim();

  String get resultTextTrimmed => asTypedOutput.result.text.trim();

  bool get hasTopLevelResultMap => _raw['result'] is Map;

  /// 顶层 `problemClass`（小写），与 `decision.problemClass` 区分。
  String get problemClassRootTrimmedLower =>
      (_raw['problemClass'] as String?)?.trim().toLowerCase() ?? '';

}
