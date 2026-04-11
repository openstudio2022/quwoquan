import 'package:quwoquan_app/assistant/generated/contracts/run_artifacts.g.dart';

// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — answerDecision/diagnostics 仍为 metadata `type: map`；
// 此处仅提供稳定键的只读投影，完整 Map 仍以 RunArtifacts 字段为真源。

/// 只读：`RunArtifacts.answerDecision` 中编排层常用键（与 `local_phase_execution_owner` spread 对齐，非穷尽）。
class RunArtifactsAnswerDecisionReadView {
  RunArtifactsAnswerDecisionReadView(Map<String, dynamic> map)
    : _m = Map<String, dynamic>.from(map);

  final Map<String, dynamic> _m;

  String get nextAction => (_m['nextAction'] as String?)?.trim() ?? '';

  bool get finalAnswerReady => _m['finalAnswerReady'] == true;

  String get answerEligibility =>
      (_m['answerEligibility'] as String?)?.trim() ?? '';

  String get evidenceSummary =>
      (_m['evidenceSummary'] as String?)?.trim() ?? '';

  bool get synthesisReady => _m['synthesisReady'] == true;

  String get synthesisReason =>
      (_m['synthesisReason'] as String?)?.trim() ?? '';

  Map<String, dynamic> get asMap => Map<String, dynamic>.from(_m);
}

/// 只读：`RunArtifacts.diagnostics` 中常用键（非穷尽）。
class RunArtifactsDiagnosticsReadView {
  RunArtifactsDiagnosticsReadView(Map<String, dynamic> map)
    : _m = Map<String, dynamic>.from(map);

  final Map<String, dynamic> _m;

  String get domainId => (_m['domainId'] as String?)?.trim() ?? '';

  String get renderMode => (_m['renderMode'] as String?)?.trim() ?? '';

  bool get evidencePassed => _m['evidencePassed'] == true;

  String get finalAnswerMode =>
      (_m['finalAnswerMode'] as String?)?.trim() ?? '';

  bool get synthesisReady => _m['synthesisReady'] == true;

  bool get heuristicFallbackUsed => _m['heuristicFallbackUsed'] == true;

  Map<String, dynamic> get qualityGates =>
      (_m['qualityGates'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  List<String> get emergedTags {
    final raw = _m['emergedTags'];
    if (raw is! List) return const <String>[];
    return raw
        .map((e) => e.toString().trim())
        .where((s) => s.isNotEmpty)
        .toList(growable: false);
  }

  Map<String, dynamic> get asMap => Map<String, dynamic>.from(_m);
}

extension RunArtifactsMapReadViews on RunArtifacts {
  RunArtifactsAnswerDecisionReadView get answerDecisionReadView =>
      RunArtifactsAnswerDecisionReadView(answerDecision);

  RunArtifactsDiagnosticsReadView get diagnosticsReadView =>
      RunArtifactsDiagnosticsReadView(diagnostics);
}
