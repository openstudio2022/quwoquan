// ASSISTANT_WEAK_TYPE: READ_VIEW — 编排层 answer 轨 JSON 子树仍为 `Map<String, dynamic>`；
// 集中 `Map?` cast，避免在 `local_phase_execution_owner` 等处重复 spread 样板。

/// LLM/编排 answer 载荷（`AssistantTurn` 子集）的只读投影。
class AssistantAnswerPayloadReadView {
  AssistantAnswerPayloadReadView(Map<String, dynamic> raw) : _raw = raw;

  final Map<String, dynamic> _raw;

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

  /// `diagnostics.emergedTags` 中条目的 Map 列表（与编排层 learning / facts 路径一致）。
  List<Map<String, dynamic>> get diagnosticsEmergedTagMaps {
    final raw = diagnosticsMap['emergedTags'];
    if (raw is! List) return const <Map<String, dynamic>>[];
    return raw
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .toList(growable: false);
  }

  /// `subagentPlan` 列表（每项为 JSON 对象 map）。
  List<Map<String, dynamic>> get subagentPlanMaps =>
      _mapListField(_raw['subagentPlan']);

  /// `evidence` 列表（每项为 JSON 对象 map）。
  List<Map<String, dynamic>> get evidenceMaps => _mapListField(_raw['evidence']);

  /// `reasoningBasis` 列表。
  List<Map<String, dynamic>> get reasoningBasisMaps =>
      _mapListField(_raw['reasoningBasis']);

  Map<String, dynamic> get modelSelfScoreMap =>
      (_raw['modelSelfScore'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  String parseStatusOrDefault(String def) => (_raw['parseStatus'] as String?) ?? def;

  Map<String, dynamic> get answerProcessingMap =>
      (_raw['answerProcessing'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  Map<String, dynamic> get displayStateMap =>
      (_raw['displayState'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  Map<String, dynamic> get retrievalProcessingMap =>
      (_raw['retrievalProcessing'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  Map<String, dynamic> get slotStateMap =>
      (_raw['slotState'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  Map<String, dynamic> get understandingSnapshotMap =>
      (_raw['understandingSnapshot'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  Map<String, dynamic> get historicalThinkingSnapshotMap =>
      (_raw['historicalThinkingSnapshot'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  Map<String, dynamic> get selfCheckMap =>
      (_raw['selfCheck'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  Map<String, dynamic>? get answerGateAssessmentMapOrNull {
    final v = _raw['answerGateAssessment'];
    if (v is! Map) return null;
    return v.cast<String, dynamic>();
  }

  String get followupPromptTrimmed =>
      (_raw['followupPrompt'] as String?)?.trim() ?? '';

  bool get hasNonEmptyContractId =>
      (_raw['contractId'] as String?)?.trim().isNotEmpty ?? false;

  String get contractIdTrimmed => (_raw['contractId'] as String?)?.trim() ?? '';

  bool get hasNonEmptyPhaseId =>
      (_raw['phaseId'] as String?)?.trim().isNotEmpty ?? false;

  String get phaseIdTrimmed => (_raw['phaseId'] as String?)?.trim() ?? '';

  bool get hasNonEmptyActionCode =>
      (_raw['actionCode'] as String?)?.trim().isNotEmpty ?? false;

  String get actionCodeTrimmed =>
      (_raw['actionCode'] as String?)?.trim() ?? '';

  bool get hasNonEmptyReasonCode =>
      (_raw['reasonCode'] as String?)?.trim().isNotEmpty ?? false;

  String get reasonCodeTrimmed =>
      (_raw['reasonCode'] as String?)?.trim() ?? '';

  String get messageKindTrimmed =>
      (_raw['messageKind'] as String?)?.trim() ?? '';

  String get userMarkdownTrimmed =>
      (_raw['userMarkdown'] as String?)?.trim() ?? '';

  String get resultInterpretationTrimmed =>
      (resultMap['interpretation'] as String?)?.trim() ?? '';

  String get resultTextTrimmed =>
      (resultMap['text'] as String?)?.trim() ?? '';

  bool get hasTopLevelResultMap => _raw['result'] is Map;

  /// 顶层 `problemClass`（小写），与 `decision.problemClass` 区分。
  String get problemClassRootTrimmedLower =>
      (_raw['problemClass'] as String?)?.trim().toLowerCase() ?? '';

  List<Map<String, dynamic>> _mapListField(Object? raw) {
    if (raw is! List) return const <Map<String, dynamic>>[];
    return raw
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .toList(growable: false);
  }
}
