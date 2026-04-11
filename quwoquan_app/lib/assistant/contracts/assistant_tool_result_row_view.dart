// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — 工具/trace 行上的 `data` 仍为弱类型 JSON。

/// 单行工具结果 Map 中 `data` 载荷的只读视图（收窄 `item['data']` 散列）。
class AssistantToolResultRowView {
  AssistantToolResultRowView(this._row);

  final Map<String, dynamic> _row;

  Map<String, dynamic> get dataPayload =>
      (_row['data'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
}
