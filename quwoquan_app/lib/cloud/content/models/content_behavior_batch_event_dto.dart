/// POST `/v1/content/behaviors` 请求体中 `events[]` 的单条载荷。
///
/// OpenAPI 规范见 `quwoquan_service/contracts/metadata/content/openapi.yaml`
/// → `BehaviorEvent`（`contentId` / `eventType` / `timestamp` 等）。
/// 端上另有历史字段（如 `action`、`postId`、`surface`）经 [fromMap] 原样保留。
class ContentBehaviorBatchEventDto {
  ContentBehaviorBatchEventDto._(this._payload);

  final Map<String, dynamic> _payload;

  /// 保留任意 wire 形状（测试、创作页 façade 等）。
  factory ContentBehaviorBatchEventDto.fromMap(Map<String, dynamic> map) {
    return ContentBehaviorBatchEventDto._(Map<String, dynamic>.from(map));
  }

  /// 与 OpenAPI `BehaviorEvent` 对齐的便捷构造。
  factory ContentBehaviorBatchEventDto.canonical({
    required String contentId,
    required String eventType,
    required String timestamp,
    int? durationMs,
    Map<String, dynamic>? metadata,
  }) {
    return ContentBehaviorBatchEventDto._(<String, dynamic>{
      'contentId': contentId,
      'eventType': eventType,
      'timestamp': timestamp,
      if (durationMs != null) 'durationMs': durationMs,
      if (metadata != null && metadata.isNotEmpty) 'metadata': metadata,
    });
  }

  Map<String, dynamic> toRequestMap() =>
      Map<String, dynamic>.from(_payload);
}
