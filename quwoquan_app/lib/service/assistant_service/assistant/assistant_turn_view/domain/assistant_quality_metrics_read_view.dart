// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — `qualityMetrics` 仍为开放 JSON 子树。

/// `anchor.qualityMetrics` / `structuredResponse.qualityMetrics` 的稳定键只读投影。
class AssistantQualityMetricsReadView {
  AssistantQualityMetricsReadView(this._raw);

  final Map<String, dynamic> _raw;

  bool get heuristicFallbackUsed => _raw['heuristicFallbackUsed'] == true;
}
