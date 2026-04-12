import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';

/// [ContentRepository.getPost] 的强类型封装：已解析的 [PostBaseDto] + 扩展 wire 的
/// [ContentPostDetailWireDto]；服务端原始 JSON 保留于 [_canonicalWire] 仅用于合并诊断。
///
/// UI 应优先使用 [post]、[detailWire] 与 [readPresentation]；文章详情/沉浸器请使用
/// [mergedArticleWireMap]（由 DTO 序列化，而非裸 Map 业务状态）。
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

  /// 与详情页/沉浸式 [projectArticleDetailView] 兼容的 wire：由 [detailWire] + [post]
  /// 具名字段合并，嵌套 `cards` / `circleSummaries` / `articleDocument` 经 DTO `.toMap()`。
  Map<String, dynamic> get mergedArticleWireMap {
    final out = Map<String, dynamic>.from(_canonicalWire);
    final d = detailWire;
    out['cards'] = d.cards.map((c) => c.toMap()).toList(growable: false);
    out['circleSummaries'] =
        d.circleSummaries.map((c) => c.toMap()).toList(growable: false);
    final doc = d.articleDocument;
    if (doc != null) {
      out['articleDocument'] = doc.toMap();
    }
    final blocks = d.articleBlocks;
    if (blocks != null) {
      out['articleBlocks'] =
          blocks.map((b) => b.toMap()).toList(growable: false);
    }
    final pages = d.articlePages;
    if (pages != null) {
      out['articlePages'] = pages.map((p) => p.toMap()).toList(growable: false);
    }
    return out;
  }

  /// 只读投影（字段来自 metadata [PostReadPresentation] + 文章扩展 wire 键）。
  PostReadPresentation get readPresentation =>
      PostReadPresentation.fromPostBase(post, wire: mergedArticleWireMap);

}
