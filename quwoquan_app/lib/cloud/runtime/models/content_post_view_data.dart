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
    required this.identity,
    required this.displayFormat,
    required this.assistantUsePolicy,
    required this.authorId,
    required this.displayName,
    required this.avatarUrl,
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
    this.hlsCmafMasterManifestUrl,
    this.hlsCmafDescriptorVersion,
    required this.likeCount,
    required this.commentCount,
    required this.shareCount,
    required this.createdAt,
    this.updatedAt,
    this.publishedAt,
    this.contentVertical,
    this.recallPath,
    this.supplySource,
    this.intersectionReasons,
    this.sourceAttribution,
  });

  factory ContentPostViewData.fromWire(
    ContentPostProjection wire, {
    SourceAttribution? sourceAttribution,
  }) {
    final type = wire.contentType.trim();
    final rawMedia = wire.mediaUrls ?? const <String>[];
    final mediaUrls = rawMedia
        .map((value) => value.trim())
        .where((value) => value.isNotEmpty)
        .toList(growable: false);
    final explicitVideoUrl = wire.videoUrl?.trim() ?? '';
    final videoUrl = explicitVideoUrl.isNotEmpty
        ? explicitVideoUrl
        : type == 'video' && mediaUrls.isNotEmpty
        ? mediaUrls.first
        : null;
    final identity = wire.contentIdentity?.trim() ?? '';
    return ContentPostViewData(
      id: wire.postId,
      type: type,
      identity: identity.isNotEmpty
          ? identity
          : type == 'micro'
          ? 'moment'
          : 'work',
      displayFormat: switch (type) {
        'video' => 'video',
        'image' => 'image',
        'article' => 'note',
        'micro' when videoUrl != null => 'video',
        'micro' when mediaUrls.isNotEmpty => 'image',
        'micro' => 'note',
        _ => throw FormatException('Unsupported contentType: $type'),
      },
      assistantUsePolicy: wire.assistantUsePolicy?.trim() ?? 'inherit',
      authorId: wire.authorId?.trim() ?? '',
      displayName: wire.authorDisplayName?.trim() ?? '',
      avatarUrl: wire.authorAvatarUrl?.trim() ?? '',
      authorBackgroundUrl: wire.authorBackgroundUrl,
      authorRoleLabel: wire.authorRoleLabel?.trim() ?? '',
      authorIdentityTags: List<String>.unmodifiable(
        wire.authorIdentityTags ?? const <String>[],
      ),
      authorVerified: wire.authorVerified ?? false,
      title: wire.title ?? '',
      body: wire.body,
      summary: wire.summary ?? '',
      imageUrls: type == 'video' ? const <String>[] : mediaUrls,
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
      hlsCmafMasterManifestUrl: wire.hlsCmafMasterManifestUrl,
      hlsCmafDescriptorVersion: wire.hlsCmafDescriptorVersion,
      likeCount: wire.likeCount,
      commentCount: wire.commentCount,
      shareCount: wire.shareCount,
      createdAt:
          wire.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
      updatedAt: wire.updatedAt,
      publishedAt: wire.publishedAt,
      contentVertical: wire.contentVertical,
      recallPath: wire.recallPath,
      supplySource: wire.supplySource,
      intersectionReasons: wire.intersectionReasons,
      sourceAttribution: sourceAttribution,
    );
  }

  final String id;
  final String type;
  final String identity;
  final String displayFormat;
  final String assistantUsePolicy;
  final String authorId;
  String get personaId => authorId;
  final String displayName;
  final String avatarUrl;
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
  final String? hlsCmafMasterManifestUrl;
  final int? hlsCmafDescriptorVersion;
  final int likeCount;
  final int commentCount;
  final int shareCount;
  final DateTime createdAt;
  final DateTime? updatedAt;
  final DateTime? publishedAt;
  final String? contentVertical;
  final String? recallPath;
  final String? supplySource;
  final List<IntersectionReason>? intersectionReasons;
  final SourceAttribution? sourceAttribution;

  bool get hasMeaningfulUpdate {
    final value = updatedAt;
    return value != null && value.difference(createdAt).inSeconds > 1;
  }

  String get normalizedTitle => title.trim();
  String get normalizedBody => (body ?? '').trim();
  List<String> get mediaImageUrls => imageUrls
      .map((url) => url.trim())
      .where((url) => url.isNotEmpty)
      .toList(growable: false);
  String get mediaCoverUrl => coverUrl?.trim() ?? '';
  String get mediaVideoUrl => videoUrl?.trim() ?? '';
  String get mediaThumbnailUrl => thumbnailUrl?.trim() ?? '';
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

  bool get isArticleLike => identity == 'work' && displayFormat == 'note';
  bool get isVideoLike => hasVideo;
  bool get isTextOnly => displayFormat == 'note' && !hasAnyMedia;
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
    identity: identity,
    displayFormat: displayFormat,
    assistantUsePolicy: assistantUsePolicy,
    authorId: authorId,
    displayName: displayName,
    avatarUrl: avatarUrl,
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
    hlsCmafMasterManifestUrl: hlsCmafMasterManifestUrl,
    hlsCmafDescriptorVersion: hlsCmafDescriptorVersion,
    likeCount: likeCount,
    commentCount: commentCount,
    shareCount: shareCount,
    createdAt: createdAt ?? this.createdAt,
    updatedAt: updatedAt,
    publishedAt: publishedAt,
    contentVertical: contentVertical,
    recallPath: recallPath,
    supplySource: supplySource,
    intersectionReasons: intersectionReasons,
    sourceAttribution: sourceAttribution,
  );

  /// App-local presentation payload; never used as a cloud decoder.
  Map<String, dynamic> toPresentationMap() => <String, dynamic>{
    'id': id,
    'type': type,
    'identity': identity,
    'assistantUsePolicy': assistantUsePolicy,
    'authorId': authorId,
    'displayName': displayName,
    'avatarUrl': avatarUrl,
    if (authorBackgroundUrl != null) 'authorBackgroundUrl': authorBackgroundUrl,
    'authorRoleLabel': authorRoleLabel,
    'authorIdentityTags': authorIdentityTags,
    'authorVerified': authorVerified,
    if (title.isNotEmpty) 'title': title,
    if (body != null) 'body': body,
    if (summary.isNotEmpty) 'summary': summary,
    if (coverUrl != null) 'coverUrl': coverUrl,
    if (articleTemplate.isNotEmpty) 'articleTemplate': articleTemplate,
    if (articleFontPreset.isNotEmpty) 'articleFontPreset': articleFontPreset,
    'imageUrls': imageUrls,
    if (videoUrl != null) 'videoUrl': videoUrl,
    if (thumbnailUrl != null) 'thumbnailUrl': thumbnailUrl,
    if (width != null) 'width': width,
    if (height != null) 'height': height,
    if (durationMs != null) 'durationMs': durationMs,
    if (mediaAssetId != null) 'mediaAssetId': mediaAssetId,
    if (mediaAssetVersion != null) 'mediaAssetVersion': mediaAssetVersion,
    if (hlsCmafMasterManifestUrl != null)
      'hlsCmafMasterManifestUrl': hlsCmafMasterManifestUrl,
    if (hlsCmafDescriptorVersion != null)
      'hlsCmafDescriptorVersion': hlsCmafDescriptorVersion,
    'likeCount': likeCount,
    'commentCount': commentCount,
    'shareCount': shareCount,
    'createdAt': createdAt,
    if (updatedAt != null) 'updatedAt': updatedAt,
    if (publishedAt != null) 'publishedAt': publishedAt,
    if (contentVertical != null) 'contentVertical': contentVertical,
    if (recallPath != null) 'recallPath': recallPath,
    if (supplySource != null) 'supplySource': supplySource,
    if (intersectionReasons != null)
      'intersectionReasons': intersectionReasons!
          .map((value) => value.toWire())
          .toList(growable: false),
  };
}
