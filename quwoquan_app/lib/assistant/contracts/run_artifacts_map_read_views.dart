import 'package:quwoquan_app/assistant/generated/contracts/run_artifacts.g.dart';

// ASSISTANT_WEAK_TYPE: READ_VIEW — `partitioned_map` 已提供 `core`/`extensions`；ReadView 仍基于合并后的 wire Map，供遗留路径使用。

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
      RunArtifactsAnswerDecisionReadView(answerDecision.toWireMap());

  RunArtifactsDiagnosticsReadView get diagnosticsReadView =>
      RunArtifactsDiagnosticsReadView(diagnostics.toWireMap());
}

/// 兼容 `??` 合并：`core` 对 map 字段的默认 `{}` 不视为「wire 曾携带该键」；extensions 优先。
extension RunArtifactsDiagnosticsPartitionedMergeLookup
    on RunArtifactsDiagnosticsPartitioned {
  Map<String, dynamic>? evidenceEvaluationForOutcomeMerge() {
    if (extensions.containsKey('evidenceEvaluation')) {
      final v = extensions['evidenceEvaluation'];
      return v is Map ? Map<String, dynamic>.from(v.cast<String, dynamic>()) : null;
    }
    final c = core.evidenceEvaluation;
    return c.isNotEmpty ? c : null;
  }

  Map<String, dynamic>? answerBoundaryPolicyForOutcomeMerge() {
    if (extensions.containsKey('answerBoundaryPolicy')) {
      final v = extensions['answerBoundaryPolicy'];
      return v is Map ? Map<String, dynamic>.from(v.cast<String, dynamic>()) : null;
    }
    final c = core.answerBoundaryPolicy;
    return c.isNotEmpty ? c : null;
  }
}
