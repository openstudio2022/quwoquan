import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Canonical Search 的 content.post 强类型展示切片。
///
/// 该类型只从 [CanonicalSearchContentHit] 构造，不是 content 业务对象，也不提供
/// 动态 Map 解码入口。
final class PostSearchItemView {
  const PostSearchItemView({
    required this.postId,
    required this.contentType,
    this.contentIdentity,
    this.title,
    this.summary,
    this.coverUrl,
    this.coverAssetId,
    this.coverAccessMode,
    this.authorId,
    this.authorDisplayName,
    this.authorAvatarUrl,
    this.categoryId,
    this.subCategory,
    this.likeCount = 0,
    this.highlightText,
    this.matchedField,
    this.publishedAt,
    this.connectionState = 'unconnected',
    this.intersectionReason,
  });

  final String postId;
  final String contentType;
  final String? contentIdentity;
  final String? title;
  final String? summary;
  final String? coverUrl;

  /// 封面的配对媒体资产标识与交付访问模式（DEC-033）；research 相位的
  /// coverUrl 是相对私有 CAS 引用，消费面按 coverAssetId 换短签。
  final String? coverAssetId;
  final MediaDeliveryAccessMode? coverAccessMode;
  final String? authorId;
  final String? authorDisplayName;
  final String? authorAvatarUrl;
  final String? categoryId;
  final String? subCategory;
  final int likeCount;
  final String? highlightText;
  final String? matchedField;
  final DateTime? publishedAt;
  final String connectionState;
  final CanonicalSearchIntersectionReason? intersectionReason;

  factory PostSearchItemView.fromCanonical(
    CanonicalSearchContentHit hit, {
    String? highlightText,
    String? matchedField,
    String? connectionState,
    CanonicalSearchIntersectionReason? intersectionReason,
  }) {
    final reason = intersectionReason;
    return PostSearchItemView(
      postId: hit.postId,
      contentType: hit.contentType.wireName,
      contentIdentity: hit.contentIdentity?.wireName,
      title: hit.title,
      summary: hit.summary,
      coverUrl: hit.coverUrl,
      coverAssetId: hit.coverAssetId,
      coverAccessMode: hit.coverAccessMode,
      authorId: hit.authorId,
      authorDisplayName: hit.authorDisplayName,
      authorAvatarUrl: hit.authorAvatarUrl,
      categoryId: hit.categoryId,
      subCategory: hit.subCategory,
      likeCount: hit.likeCount,
      highlightText: highlightText,
      matchedField: matchedField,
      publishedAt: hit.publishedAt,
      connectionState: connectionState ?? 'unconnected',
      intersectionReason: reason,
    );
  }
}
