// ASSISTANT_WEAK_TYPE: LLM_RAW | VENDOR_JSON — OpenAI 兼容 `/chat/completions` 请求/响应 wire；非 metadata SSOT。

/// `jsonDecode` 后 OpenAI 兼容 chat/completions **根对象**（用于读取 `usage` 等）。
final class OpenAiChatCompletionResponseRoot {
  const OpenAiChatCompletionResponseRoot(this.root);

  final Map<String, dynamic> root;

  Map<String, dynamic>? get usage {
    final u = root['usage'];
    if (u is Map<String, dynamic>) return u;
    if (u is Map) return Map<String, dynamic>.from(u);
    return null;
  }
}

/// 非流式 `POST /chat/completions` 请求体（与现有 [AssistantLlmProvider._requestCompletion] 行为一致）。
Map<String, dynamic> buildOpenAiNonStreamingChatCompletionRequest({
  required String modelId,
  required List<Map<String, dynamic>> requestMessages,
  required List<Map<String, dynamic>> toolSchemas,
  required bool enableTools,
  required double temperature,
  int? maxTokens,
  required Map<String, dynamic> reasoningRequestEntries,
  required bool forceJsonObject,
  required bool supportsJsonMode,
}) {
  final request = <String, dynamic>{
    'model': modelId,
    'messages': requestMessages,
    if (enableTools && toolSchemas.isNotEmpty) 'tools': toolSchemas,
    if (enableTools && toolSchemas.isNotEmpty) 'tool_choice': 'auto',
    'temperature': temperature,
    ...reasoningRequestEntries,
    if (forceJsonObject && supportsJsonMode)
      'response_format': const <String, dynamic>{'type': 'json_object'},
  };
  if (maxTokens != null) {
    request['max_tokens'] = maxTokens;
  }
  return request;
}

/// 带 tools 的流式 `POST /chat/completions`（`stream: true`），与 [_requestCompletionStreaming] 一致。
Map<String, dynamic> buildOpenAiStreamingChatCompletionRequest({
  required String modelId,
  required List<Map<String, dynamic>> requestMessages,
  required List<Map<String, dynamic>> toolSchemas,
  required bool enableTools,
  required double temperature,
  int? maxTokens,
  required Map<String, dynamic> reasoningRequestEntries,
  required bool forceJsonObject,
  required bool supportsJsonMode,
}) {
  final base = buildOpenAiNonStreamingChatCompletionRequest(
    modelId: modelId,
    requestMessages: requestMessages,
    toolSchemas: toolSchemas,
    enableTools: enableTools,
    temperature: temperature,
    maxTokens: maxTokens,
    reasoningRequestEntries: reasoningRequestEntries,
    forceJsonObject: forceJsonObject,
    supportsJsonMode: supportsJsonMode,
  );
  return <String, dynamic>{...base, 'stream': true};
}

/// 流式规划器 `POST /chat/completions`（`stream: true`），与现有 [AssistantLlmProvider] 流式路径一致。
Map<String, dynamic> buildOpenAiStreamingPlannerChatRequest({
  required String modelId,
  required List<Map<String, dynamic>> requestMessages,
  required Map<String, dynamic> reasoningRequestEntries,
  required bool supportsJsonMode,
}) {
  return <String, dynamic>{
    'model': modelId,
    'messages': requestMessages,
    'temperature': 0.2,
    'max_tokens': 4096,
    'stream': true,
    ...reasoningRequestEntries,
    if (supportsJsonMode)
      'response_format': const <String, dynamic>{'type': 'json_object'},
  };
}
