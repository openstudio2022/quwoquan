// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — `structuredResponse.dialogueRuntime` 开放 JSON 子树。

/// `dialogueRuntime` 在 UI/时间轴上仅需的只读投影（避免散列 `['domainId']`）。
class AssistantDialogueRuntimeReadView {
  AssistantDialogueRuntimeReadView(this._raw);

  final Map<String, dynamic> _raw;

  String get domainIdOrEmpty => (_raw['domainId'] ?? '').toString();

  String get suggestedNextStateIdOrEmpty =>
      (_raw['suggestedNextStateId'] as String?)?.trim() ?? '';
}
