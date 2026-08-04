import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class WorkBrowserMediaViewData {
  const WorkBrowserMediaViewData({
    required this.kind,
    required this.url,
    this.coverUrl,
    this.durationMs,
    this.mediaAssetId,
    this.mediaAssetVersion,
    this.previewTrackManifestUrl,
    this.previewTrackVersion,
    this.hlsCmafMasterManifestUrl,
    this.hlsCmafDescriptorVersion,
    this.width,
    this.height,
    this.title,
  });

  factory WorkBrowserMediaViewData.fromWire(PostMediaItem wire) =>
      WorkBrowserMediaViewData(
        kind: wire.kind,
        url: wire.url,
        coverUrl: wire.coverUrl,
        durationMs: wire.durationMs,
        mediaAssetId: wire.mediaAssetId,
        mediaAssetVersion: wire.mediaAssetVersion,
        hlsCmafMasterManifestUrl: wire.hlsCmafMasterManifestUrl,
        hlsCmafDescriptorVersion: wire.hlsCmafDescriptorVersion,
        width: wire.width,
        height: wire.height,
        title: wire.title,
      );

  final String kind;
  final String url;
  final String? coverUrl;
  final int? durationMs;
  final String? mediaAssetId;
  final int? mediaAssetVersion;
  final String? previewTrackManifestUrl;
  final int? previewTrackVersion;
  final String? hlsCmafMasterManifestUrl;
  final int? hlsCmafDescriptorVersion;
  final int? width;
  final int? height;
  final String? title;
}

final class WorkBrowserEntityMentionViewData {
  const WorkBrowserEntityMentionViewData({
    required this.subjectType,
    required this.subjectId,
    required this.homepageId,
  });

  final String subjectType;
  final String subjectId;
  final String homepageId;
}

/// Immersive-view presentation state derived from canonical Post wire plus
/// optional typed detail wire. It is not a transport DTO.
final class WorkBrowserViewData {
  const WorkBrowserViewData({
    required this.authorBadge,
    required this.mediaAssetId,
    required this.mediaAssetVersion,
    required this.previewTrackManifestUrl,
    required this.previewTrackVersion,
    required this.mediaItems,
    required this.articleRenderProfile,
    required this.contentVertical,
    required this.paperTexture,
    required this.entityMentions,
    required this.imageUrls,
    required this.videoUrl,
    required this.coverUrl,
    required this.thumbnailUrl,
    required this.durationMs,
  });

  factory WorkBrowserViewData.fromPost(
    ContentPostViewData post, {
    ContentPostDetailSlice? detail,
    Map<String, Object?>? supplemental,
  }) {
    final supplementalItems = supplemental?['mediaItems'];
    final localMediaItems = supplementalItems is List
        ? supplementalItems
              .whereType<Map>()
              .map((item) {
                final map = Map<String, Object?>.from(item);
                return WorkBrowserMediaViewData(
                  kind: map['kind']?.toString() ?? '',
                  url: map['url']?.toString() ?? '',
                  coverUrl: map['coverUrl']?.toString(),
                  durationMs: (map['durationMs'] as num?)?.toInt(),
                  mediaAssetId: map['mediaAssetId']?.toString(),
                  mediaAssetVersion: (map['mediaAssetVersion'] as num?)
                      ?.toInt(),
                  previewTrackManifestUrl: map['previewTrackManifestUrl']
                      ?.toString(),
                  previewTrackVersion: (map['previewTrackVersion'] as num?)
                      ?.toInt(),
                  hlsCmafMasterManifestUrl: map['hlsCmafMasterManifestUrl']
                      ?.toString(),
                  hlsCmafDescriptorVersion:
                      (map['hlsCmafDescriptorVersion'] as num?)?.toInt(),
                  width: (map['width'] as num?)?.toInt(),
                  height: (map['height'] as num?)?.toInt(),
                  title: map['title']?.toString(),
                );
              })
              .toList(growable: false)
        : const <WorkBrowserMediaViewData>[];
    final supplementalMentions = supplemental?['entityMentions'];
    final localEntityMentions = supplementalMentions is List
        ? supplementalMentions
              .whereType<Map>()
              .map(
                (mention) => PostEntityMention.fromWire(
                  Map<String, Object?>.from(mention),
                ),
              )
              .toList(growable: false)
        : const <PostEntityMention>[];
    return WorkBrowserViewData(
      authorBadge: null,
      mediaAssetId: post.mediaAssetId,
      mediaAssetVersion: post.mediaAssetVersion,
      previewTrackManifestUrl: null,
      previewTrackVersion: null,
      mediaItems: localMediaItems.isNotEmpty
          ? List<WorkBrowserMediaViewData>.unmodifiable(localMediaItems)
          : List<WorkBrowserMediaViewData>.unmodifiable(
              (detail?.mediaItems ?? const <PostMediaItem>[]).map(
                WorkBrowserMediaViewData.fromWire,
              ),
            ),
      articleRenderProfile:
          detail?.articleRenderProfile?.toWire() ??
          (supplemental?['articleRenderProfile'] is Map
              ? Map<String, Object?>.from(
                  supplemental!['articleRenderProfile']! as Map,
                )
              : null),
      contentVertical:
          detail?.contentVertical ??
          supplemental?['contentVertical']?.toString() ??
          post.contentVertical,
      paperTexture: supplemental?['paperTexture']?.toString(),
      entityMentions: List<WorkBrowserEntityMentionViewData>.unmodifiable(
        (detail?.entityMentions ?? localEntityMentions).map(
          (mention) => WorkBrowserEntityMentionViewData(
            subjectType: mention.subjectType,
            subjectId: mention.subjectId,
            homepageId: mention.homepageId,
          ),
        ),
      ),
      imageUrls: post.mediaImageUrls,
      videoUrl: post.videoUrl,
      coverUrl: post.mediaCoverUrl,
      thumbnailUrl: post.mediaThumbnailUrl,
      durationMs: post.durationMs,
    );
  }

  final String? authorBadge;
  final String? mediaAssetId;
  final int? mediaAssetVersion;
  final String? previewTrackManifestUrl;
  final int? previewTrackVersion;
  final List<WorkBrowserMediaViewData> mediaItems;
  final Map<String, Object?>? articleRenderProfile;
  final String? contentVertical;
  final String? paperTexture;
  final List<WorkBrowserEntityMentionViewData> entityMentions;
  final List<String> imageUrls;
  final String? videoUrl;
  final String coverUrl;
  final String thumbnailUrl;
  final int? durationMs;

  List<WorkBrowserMediaViewData> get videoItems {
    final typed = mediaItems
        .where((item) => item.kind == 'video' && item.url.isNotEmpty)
        .toList(growable: false);
    if (typed.isNotEmpty) return typed;
    final fallback = videoUrl?.trim() ?? '';
    if (fallback.isEmpty) return const <WorkBrowserMediaViewData>[];
    return <WorkBrowserMediaViewData>[
      WorkBrowserMediaViewData(
        kind: 'video',
        url: fallback,
        coverUrl: thumbnailUrl.isNotEmpty
            ? thumbnailUrl
            : (coverUrl.isEmpty ? null : coverUrl),
        durationMs: durationMs,
        mediaAssetId: mediaAssetId,
        mediaAssetVersion: mediaAssetVersion,
      ),
    ];
  }

  List<String> get effectiveImageUrls {
    final typed = mediaItems
        .where((item) => item.kind == 'image' && item.url.isNotEmpty)
        .map((item) => item.url)
        .toList(growable: false);
    return typed.isEmpty ? imageUrls : typed;
  }
}
