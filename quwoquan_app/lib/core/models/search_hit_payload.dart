import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_search_views.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_search_item_view_dto.g.dart';

/// 全局搜索 [SearchHit] 的具名载荷（sealed），避免跨层持匿名 Map 作为业务状态。
///
/// 通用 wire 边界使用 [SearchHitPayloadWireMap]；与 wire 对齐的帖子/圈子命中优先用 codegen 视图类型。
/// 序列化见各分支 [toWireMap]（仅边界/观测/助手工具）。
sealed class SearchHitPayload {
  const SearchHitPayload();

  /// 与 `SearchHit.toMap()['payload']` 形状一致的可编码 Map（JSON 边界）。
  Map<String, dynamic> toWireMap();
}

/// 通用 wire Map 命中（聊天、主页、POI、网页引用等）。
final class SearchHitPayloadWireMap extends SearchHitPayload {
  const SearchHitPayloadWireMap([Map<String, dynamic>? map])
    : map = map ?? const <String, dynamic>{};

  final Map<String, dynamic> map;

  @override
  Map<String, dynamic> toWireMap() => map;
}

/// 内容帖子命中（与 [PostSearchItemView] 同源）。
final class SearchHitPayloadContentPost extends SearchHitPayload {
  const SearchHitPayloadContentPost(this.item);

  final PostSearchItemView item;

  @override
  Map<String, dynamic> toWireMap() => postSearchItemViewToSearchHitWire(item);
}

/// 圈子「圈子」命中（与 [CircleSearchItemView] 同源）。
final class SearchHitPayloadCircleCircle extends SearchHitPayload {
  const SearchHitPayloadCircleCircle(this.item);

  final CircleSearchItemView item;

  @override
  Map<String, dynamic> toWireMap() => item.toSearchHitPayload();
}

/// 与 [AppSearchRepository._postHit] 当前字段表一致，避免与视图字段漂移。
Map<String, dynamic> postSearchItemViewToSearchHitWire(
  PostSearchItemView item,
) {
  return <String, dynamic>{
    'postId': item.postId,
    'contentType': item.contentType,
    'contentIdentity': item.contentIdentity,
    'title': item.title,
    'summary': item.summary,
    'coverUrl': item.coverUrl,
    'authorProfileSubjectId': item.authorProfileSubjectId,
    'authorDisplayName': item.authorDisplayName,
    'authorAvatarUrl': item.authorAvatarUrl,
    'circleId': item.circleId,
    'circleName': item.circleName,
    'categoryId': item.categoryId,
    'subCategory': item.subCategory,
    'likeCount': item.likeCount,
    'highlightText': item.highlightText,
    'matchedField': item.matchedField,
    'publishedAt': item.publishedAt?.toIso8601String(),
  };
}
