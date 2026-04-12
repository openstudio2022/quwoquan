// ASSISTANT_WEAK_TYPE: VENDOR_JSON — OpenAI 兼容用量台账一行；非 metadata SSOT。

/// 单次 LLM 调用的用量台账条目（与 [AssistantLlmProvider] `_buildUsageEntry` 字段一致）。
final class LlmUsageLedgerEntry {
  const LlmUsageLedgerEntry({
    required this.provider,
    required this.modelId,
    required this.modelRef,
    required this.streaming,
    required this.source,
    required this.inputTokens,
    required this.outputTokens,
    required this.totalTokens,
    required this.latencyMs,
  });

  final String provider;
  final String modelId;
  final String modelRef;
  final bool streaming;
  final String source;
  final int inputTokens;
  final int outputTokens;
  final int totalTokens;
  final int latencyMs;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'provider': provider,
    'modelId': modelId,
    'modelRef': modelRef,
    'streaming': streaming,
    'source': source,
    'inputTokens': inputTokens,
    'outputTokens': outputTokens,
    'totalTokens': totalTokens,
    'latencyMs': latencyMs,
  };

  factory LlmUsageLedgerEntry.fromJson(Map<String, dynamic> json) {
    return LlmUsageLedgerEntry(
      provider: (json['provider'] as String?)?.trim() ?? '',
      modelId: (json['modelId'] as String?)?.trim() ?? '',
      modelRef: (json['modelRef'] as String?)?.trim() ?? '',
      streaming: json['streaming'] == true,
      source: (json['source'] as String?)?.trim() ?? '',
      inputTokens: _nonNegInt(json['inputTokens']),
      outputTokens: _nonNegInt(json['outputTokens']),
      totalTokens: _nonNegInt(json['totalTokens']),
      latencyMs: _nonNegInt(json['latencyMs']),
    );
  }

  static int _nonNegInt(Object? v) {
    if (v is int) return v < 0 ? 0 : v;
    if (v is num) {
      final n = v.toInt();
      return n < 0 ? 0 : n;
    }
    return int.tryParse(v?.toString().trim() ?? '') ?? 0;
  }
}
