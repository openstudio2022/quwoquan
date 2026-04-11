import 'dart:convert';

// ASSISTANT_WEAK_TYPE: VENDOR_JSON — HTTP 等入口 `jsonDecode` 后统一为 string-keyed map，避免 `dynamic` 根在网关与业务之间裸传。

/// 将请求体 JSON 解码为顶层对象 map；非对象或空体返回空 map。
Map<String, dynamic> assistantDecodeJsonObjectBody(String body) {
  final trimmed = body.trim();
  if (trimmed.isEmpty) return <String, dynamic>{};
  final decoded = jsonDecode(trimmed);
  if (decoded is Map<String, dynamic>) return decoded;
  if (decoded is Map) return decoded.cast<String, dynamic>();
  return <String, dynamic>{};
}
