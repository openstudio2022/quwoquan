import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// App-owned presentation projection of the canonical Content Post wire.
///
/// The cloud decoder remains [ContentPostProjection.fromWire]. This type only
/// normalizes nullable server fields for rendering and never decodes transport
/// maps itself.
final class ContentPostViewData {
  const ContentPostViewData({
    required this.id,
    required this.type,
    required this.assistantUsePolicy,
    required this.authorId,
    required this.displayName,
    required this.avatarUrl,
    this.authorAvatarAssetId,
    this.authorAvatarAccessMode,
    this.authorBackgroundUrl,
    required this.authorRoleLabel,
    required this.authorIdentityTags,
    required this.authorVerified,
    this.title = '',
    this.body,
    this.summary = '',
    this.imageUrls = const <String>[],
    this.coverUrl,
    this.articleTemplate = '',
    this.articleFontPreset = '',
    this.videoUrl,
    this.thumbnailUrl,
    this.width,
    this.height,
    this.durationMs,
    this.mediaAssetId,
    this.mediaAssetVersion,
    this.mediaItems = const <PostMediaItem>[],
    this.hlsCmafMasterManifestUrl,
    this.hlsCmafDescriptorVersion,
    required this.likeCount,
    required this.commentCount,
    required this.shareCount,
    this.viewerLiked,
    required this.createdAt,
    this.updatedAt,
    this.publishedAt,
    this.recallPath,
    this.supplySource,
    this.intersectionReasons,
    this.sourceAttribution,
    this.primaryHomepageId,
    this.primaryHomepageType,
    this.gatheringRef,
    this.openSurface,
    this.presentationRecipe,
  });

  factory ContentPostViewData.fromWire(
    ContentPostProjection wire, {
    PublicSourceAttribution? sourceAttribution,
    ContentUiSurface? openSurface,
    FeedPresentationRecipe? presentationRecipe,
  }) {
    final type = wire.contentType;
    final rawMedia = wire.mediaUrls ?? const <String>[];
    final mediaUrls = rawMedia
        .where((value) => value.isNotEmpty)
        .toList(growable: false);
    final explicitVideoUrl = wire.videoUrl ?? '';
    final videoUrl = explicitVideoUrl.isNotEmpty
        ? explicitVideoUrl
        : type == ContentType.video && mediaUrls.isNotEmpty
        ? mediaUrls.first
        : null;
    return ContentPostViewData(
      id: wire.postId,
      type: type,
      // 契约层已经把 wire 字符串解成 typed enum，这里只补 `DEFAULT_INHERIT`。
      // 再走一次字符串 codec 会把枚举 toString 成 `AssistantUsePolicy.inherit`
      // 并被 fromWire 拒绝。
      assistantUsePolicy: wire.assistantUsePolicy ?? AssistantUsePolicy.inherit,
      authorId: wire.authorId?.trim() ?? '',
      displayName: wire.authorDisplayName?.trim() ?? '',
      avatarUrl: wire.authorAvatarUrl ?? '',
      authorAvatarAssetId: wire.authorAvatarAssetId,
      authorAvatarAccessMode: wire.authorAvatarAccessMode,
      authorBackgroundUrl: wire.authorBackgroundUrl,
      authorRoleLabel: wire.authorRoleLabel?.trim() ?? '',
      authorIdentityTags: List<String>.unmodifiable(
        wire.authorIdentityTags ?? const <String>[],
      ),
      authorVerified: wire.authorVerified ?? false,
      title: wire.title ?? '',
      body: wire.body,
      summary: wire.summary ?? '',
      imageUrls: type == ContentType.video ? const <String>[] : mediaUrls,
      coverUrl: wire.coverUrl,
      articleTemplate: wire.articleTemplate ?? '',
      articleFontPreset: wire.articleFontPreset ?? '',
      videoUrl: videoUrl,
      thumbnailUrl: wire.thumbnailUrl,
      width: wire.width,
      height: wire.height,
      durationMs: wire.durationMs,
      mediaAssetId: wire.mediaAssetId,
      mediaAssetVersion: wire.mediaAssetVersion,
      mediaItems: wire.mediaItems ?? const <PostMediaItem>[],
      hlsCmafMasterManifestUrl: wire.hlsCmafMasterManifestUrl,
      hlsCmafDescriptorVersion: wire.hlsCmafDescriptorVersion,
      likeCount: wire.likeCount,
      commentCount: wire.commentCount,
      shareCount: wire.shareCount,
      viewerLiked: wire.viewerLiked,
      createdAt:
          wire.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
      updatedAt: wire.updatedAt,
      publishedAt: wire.publishedAt,
      recallPath: wire.recallPath,
      supplySource: wire.supplySource,
      intersectionReasons: wire.intersectionReasons,
      sourceAttribution: sourceAttribution,
      primaryHomepageId: wire.primaryHomepageId,
      gatheringRef: wire.gatheringRef,
      primaryHomepageType: wire.primaryHomepageType,
      openSurface: openSurface,
      presentationRecipe: presentationRecipe,
    );
  }

  final String id;

  /// 对象身份的唯一权威轴：写入时确定，读侧只翻译，不从媒体附件反推。
  final ContentType type;
  final AssistantUsePolicy assistantUsePolicy;
  final String authorId;
  String get personaId => authorId;
  final String displayName;
  final String avatarUrl;

  /// 作者头像的媒体交付绑定（DEC-033）：release authority 的资产标识与交付形态。
  /// 契约缺席即为 null，禁止以 personaId/postId 冒充资产标识。
  final String? authorAvatarAssetId;
  final MediaDeliveryAccessMode? authorAvatarAccessMode;
  final String? authorBackgroundUrl;
  final String authorRoleLabel;
  final List<String> authorIdentityTags;
  final bool authorVerified;
  final String title;
  final String? body;
  final String summary;
  final List<String> imageUrls;
  final String? coverUrl;
  final String articleTemplate;
  final String articleFontPreset;
  final String? videoUrl;
  final String? thumbnailUrl;
  final int? width;
  final int? height;
  final int? durationMs;
  final String? mediaAssetId;
  final int? mediaAssetVersion;

  /// 逐条媒体的交付绑定投影（DEC-033）：保留契约 `mediaItems` 的每条
  /// `mediaAssetId`/`accessMode`/`coverAssetId`，映射不得丢弃。
  /// wire 缺席时为空列表。
  final List<PostMediaItem> mediaItems;
  final String? hlsCmafMasterManifestUrl;
  final int? hlsCmafDescriptorVersion;
  final int likeCount;
  final int commentCount;
  final int shareCount;

  /// viewer 维度点赞态：true/false 为服务端权威值；null 表示本次响应未附着
  /// viewer 态（匿名请求或读路径降级），hydrate 时不得据 null 回滚本地状态。
  final bool? viewerLiked;
  final DateTime createdAt;
  final DateTime? updatedAt;
  final DateTime? publishedAt;
  final String? recallPath;
  final String? supplySource;
  final List<IntersectionReason>? intersectionReasons;
  final PublicSourceAttribution? sourceAttribution;

  /// 主实体锚点（canonical homepage 引用）：想去 CTA 与实体跳转的意图信号源；
  /// 无实体锚点的内容两字段均为 null，想去入口不渲染、不做本地推断。
  final String? primaryHomepageId;

  /// 共同经历回流引用：feed/沉浸卡溯源标「他们从这条内容出发」的锚点；
  /// 作者删除或取消关联为 null。
  final String? gatheringRef;
  final String? primaryHomepageType;

  /// 云物化的目的面：列表项点击只按这一个字段导航。
  ///
  /// 只有下发列表信封的操作才有值；详情与离线快照当前不下发信封，缺席时导航
  /// 进入需升级的 typed 终态，不按 [type] 反推目的面。
  final ContentUiSurface? openSurface;

  /// 首页卡片家族；只有 `homeFeed` 会下发，其它面缺席。
  final FeedPresentationRecipe? presentationRecipe;

  bool get hasMeaningfulUpdate {
    final value = updatedAt;
    return value != null && value.difference(createdAt).inSeconds > 1;
  }

  String get normalizedTitle => title.trim();
  String get normalizedBody => (body ?? '').trim();
  String get normalizedSummary => summary.trim();
  String get articlePreviewText => normalizedSummary;

  List<String> get mediaImageUrls =>
      imageUrls.where((url) => url.isNotEmpty).toList(growable: false);
  String get mediaCoverUrl => coverUrl ?? '';
  String get mediaVideoUrl => videoUrl ?? '';
  String get mediaThumbnailUrl => thumbnailUrl ?? '';
  String get mediaVideoCoverUrl =>
      mediaThumbnailUrl.isNotEmpty ? mediaThumbnailUrl : mediaCoverUrl;
  bool get hasImages => mediaImageUrls.isNotEmpty;
  bool get hasVideo => mediaVideoUrl.isNotEmpty;
  bool get hasVisualMedia =>
      hasImages || mediaCoverUrl.isNotEmpty || mediaThumbnailUrl.isNotEmpty;
  bool get hasAnyMedia => hasVisualMedia || hasVideo;
  int get mediaCount => hasVideo ? 1 : mediaImageUrls.length;
  double? get aspectRatio =>
      width != null && height != null && height! > 0 ? width! / height! : null;

  String get primaryImageUrl {
    if (mediaImageUrls.isNotEmpty) return mediaImageUrls.first;
    if (mediaCoverUrl.isNotEmpty) return mediaCoverUrl;
    return mediaThumbnailUrl;
  }

  String get primaryVisualUrl {
    if (hasVideo && mediaThumbnailUrl.isNotEmpty) return mediaThumbnailUrl;
    if (hasVideo && mediaCoverUrl.isNotEmpty) return mediaCoverUrl;
    return primaryImageUrl;
  }

  bool get supportsUnifiedViewer =>
      hasAnyMedia || normalizedTitle.isNotEmpty || normalizedBody.isNotEmpty;

  ContentPostViewData copyWith({
    String? id,
    String? title,
    String? summary,
    DateTime? createdAt,
  }) => ContentPostViewData(
    id: id ?? this.id,
    type: type,
    assistantUsePolicy: assistantUsePolicy,
    authorId: authorId,
    displayName: displayName,
    avatarUrl: avatarUrl,
    authorAvatarAssetId: authorAvatarAssetId,
    authorAvatarAccessMode: authorAvatarAccessMode,
    authorBackgroundUrl: authorBackgroundUrl,
    authorRoleLabel: authorRoleLabel,
    authorIdentityTags: authorIdentityTags,
    authorVerified: authorVerified,
    title: title ?? this.title,
    body: body,
    summary: summary ?? this.summary,
    imageUrls: imageUrls,
    coverUrl: coverUrl,
    articleTemplate: articleTemplate,
    articleFontPreset: articleFontPreset,
    videoUrl: videoUrl,
    thumbnailUrl: thumbnailUrl,
    width: width,
    height: height,
    durationMs: durationMs,
    mediaAssetId: mediaAssetId,
    mediaAssetVersion: mediaAssetVersion,
    mediaItems: mediaItems,
    hlsCmafMasterManifestUrl: hlsCmafMasterManifestUrl,
    hlsCmafDescriptorVersion: hlsCmafDescriptorVersion,
    likeCount: likeCount,
    commentCount: commentCount,
    shareCount: shareCount,
    viewerLiked: viewerLiked,
    createdAt: createdAt ?? this.createdAt,
    updatedAt: updatedAt,
    publishedAt: publishedAt,
    recallPath: recallPath,
    supplySource: supplySource,
    intersectionReasons: intersectionReasons,
    sourceAttribution: sourceAttribution,
    primaryHomepageId: primaryHomepageId,
    gatheringRef: gatheringRef,
    primaryHomepageType: primaryHomepageType,
    openSurface: openSurface,
    presentationRecipe: presentationRecipe,
  );
}
