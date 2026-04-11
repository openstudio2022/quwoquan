import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';

/// [ContentRepository.getPost] 的强类型封装：已解析的 [PostBaseDto] + 扩展 wire 的
/// [ContentPostDetailWireDto]；完整 JSON 回声用于与历史 `Map` API 兼容。
///
/// UI 应优先使用 [post]、[detailWire] 与 [readPresentation]（metadata 投影）；仅在文章详情 /
/// 沉浸器等仍依赖完整 Map 的路径使用 [wireForArticleProjection]。
class ContentPostDetailPayload {
  ContentPostDetailPayload._(this.post, this.detailWire, this._canonicalWire);

  /// 自网关 JSON 对象构造；[post]、[detailWire] 与 [_canonicalWire] 同源。
  factory ContentPostDetailPayload.fromWire(Map<String, dynamic> wire) {
    final copy = Map<String, dynamic>.from(wire);
    return ContentPostDetailPayload._(
      postBaseDtoFromMap(copy),
      ContentPostDetailWireDto.fromMap(copy),
      Map<String, dynamic>.from(wire),
    );
  }

  final PostBaseDto post;

  /// GET post 响应中基类之外的扩展字段（metadata: content_post_detail_wire.yaml）。
  final ContentPostDetailWireDto detailWire;

  final Map<String, dynamic> _canonicalWire;

  /// 只读投影（字段来自 metadata [PostReadPresentation] + 文章扩展 wire 键）。
  PostReadPresentation get readPresentation =>
      PostReadPresentation.fromPostBase(post, wire: wireForArticleProjection);

  /// 与详情页/沉浸式水合逻辑兼容的完整 wire（含 `cards`、`articleDocument` 等）。
  Map<String, dynamic> get wireForArticleProjection =>
      Map<String, dynamic>.from(_canonicalWire);
}
