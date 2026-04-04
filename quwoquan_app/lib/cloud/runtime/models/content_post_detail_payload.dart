import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';

/// [ContentRepository.getPost] 的强类型封装：已解析的 [PostBaseDto] + 原始 wire（文章卡片等扩展字段）。
///
/// UI 应优先使用 [post]；仅在 [projectArticleDetailView] 等尚未 metadata 化的投射链使用
/// [wireForArticleProjection]。
class ContentPostDetailPayload {
  ContentPostDetailPayload._(this.post, this._wire);

  /// 自网关 JSON 对象构造；[post] 与 [_wire] 同源。
  factory ContentPostDetailPayload.fromWire(Map<String, dynamic> wire) {
    final copy = Map<String, dynamic>.from(wire);
    return ContentPostDetailPayload._(postBaseDtoFromMap(copy), copy);
  }

  final PostBaseDto post;

  final Map<String, dynamic> _wire;

  /// 与详情页/沉浸式水合逻辑兼容的完整 wire（含 `cards`、`articleDocument` 等）。
  Map<String, dynamic> get wireForArticleProjection =>
      Map<String, dynamic>.from(_wire);
}
