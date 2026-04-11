import 'package:quwoquan_app/assistant/generated/contracts/run_artifacts_map_stable_keys.g.dart';

// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — 不改变 JSON；仅按 metadata `map_stable_keys` 划分稳定键与扩展键。

/// 将 `RunArtifacts` 中 `type: map` 字段拆成「稳定键 / 扩展键」并无损合并。
abstract final class RunArtifactsMapPartition {
  RunArtifactsMapPartition._();

  static Map<String, dynamic> stableSlice(
    Map<String, dynamic> full,
    Set<String> stableKeys,
  ) {
    final out = <String, dynamic>{};
    for (final k in stableKeys) {
      if (full.containsKey(k)) {
        out[k] = full[k];
      }
    }
    return out;
  }

  static Map<String, dynamic> extensionSlice(
    Map<String, dynamic> full,
    Set<String> stableKeys,
  ) {
    final out = <String, dynamic>{};
    for (final e in full.entries) {
      if (!stableKeys.contains(e.key)) {
        out[e.key] = e.value;
      }
    }
    return out;
  }

  static Map<String, dynamic> mergeSlices(
    Map<String, dynamic> stablePart,
    Map<String, dynamic> extensionPart,
  ) =>
      <String, dynamic>{...stablePart, ...extensionPart};

  static Map<String, dynamic> answerDecisionStable(Map<String, dynamic> full) =>
      stableSlice(full, RunArtifactsMapStableKeys.answerDecision);

  static Map<String, dynamic> answerDecisionExtension(
    Map<String, dynamic> full,
  ) =>
      extensionSlice(full, RunArtifactsMapStableKeys.answerDecision);

  static Map<String, dynamic> diagnosticsStable(Map<String, dynamic> full) =>
      stableSlice(full, RunArtifactsMapStableKeys.diagnostics);

  static Map<String, dynamic> diagnosticsExtension(
    Map<String, dynamic> full,
  ) =>
      extensionSlice(full, RunArtifactsMapStableKeys.diagnostics);
}
