import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';

/// 统一内容展示种类（媒体形态）。
///
/// 通过 `PostBaseDto` 的契约派生 getter（`isVideoLike`/`isArticleLike`/`hasImages`）
/// 判别，禁止对 DTO 子类做 `is/as/whereType`（遵循 04-dart-polymorphism）。
enum ContentSurfaceKind { micro, image, video, article }

/// 作者引用（强类型，替代裸 Map 作者字段）。
class ContentAuthorRef {
  const ContentAuthorRef({
    required this.id,
    required this.displayName,
    required this.avatarUrl,
    this.backgroundUrl,
  });

  final String id;
  final String displayName;
  final String avatarUrl;
  final String? backgroundUrl;
}

/// 图片媒体引用。
class ContentImageRef {
  const ContentImageRef({required this.url, this.aspectRatio});

  final String url;
  final double? aspectRatio;
}

/// 封面媒体引用（article 封面 / video 首帧）。
class ContentCoverRef {
  const ContentCoverRef({required this.url, this.aspectRatio});

  final String url;
  final double? aspectRatio;
}

/// 视频媒体引用（单视频）。
class ContentVideoRef {
  const ContentVideoRef({
    required this.url,
    required this.thumbnailUrl,
    this.durationMs,
    this.aspectRatio,
  });

  final String url;
  final String thumbnailUrl;
  final int? durationMs;
  final double? aspectRatio;
}

/// 互动统计（强类型，替代散落的 count 字段）。
class ContentStats {
  const ContentStats({
    this.like = 0,
    this.comment = 0,
    this.favorite = 0,
    this.share = 0,
    this.view = 0,
  });

  final int like;
  final int comment;
  final int favorite;
  final int share;
  final int view;
}

/// surface 归因上下文（仅透传埋点，不参与展示）。
class ContentSurfaceReferral {
  const ContentSurfaceReferral({this.position, this.feedRequestId});

  final int? position;
  final String? feedRequestId;
}

/// 统一只读内容展示模型。
///
/// 作为 feed / immersive / detail / share 四个消费 surface 的唯一只读真相源，
/// 覆盖 micro/image/video/article 四媒体类型。媒体差异由 [kind] + 强类型可选字段
/// 表达，surface widget 只读结果，不再各自从 DTO/Map 抽字段。
///
/// 字段集与 fallback 口径对齐 `contracts/metadata/content/post` 投影
/// （`fields.yaml` / `discovery_feed.yaml` / `post_read_presentation.yaml`）。
class ContentSurfaceView {
  const ContentSurfaceView({
    required this.postId,
    required this.kind,
    required this.contentType,
    required this.contentIdentity,
    required this.author,
    required this.stats,
    required this.createdAt,
    this.title,
    this.body,
    this.cover,
    this.images = const <ContentImageRef>[],
    this.video,
    this.intersectionReasons = const <IntersectionReason>[],
    this.tags = const <String>[],
    this.articleTemplate = '',
    this.articleFontPreset = '',
    this.referral = const ContentSurfaceReferral(),
  });

  final String postId;
  final ContentSurfaceKind kind;

  /// 原始内容类型（photo/video/article/moment 等），保留以便分支与埋点。
  final String contentType;

  /// 内容身份（work/moment）。
  final String contentIdentity;

  final ContentAuthorRef author;
  final ContentStats stats;
  final DateTime createdAt;

  final String? title;
  final String? body;

  final ContentCoverRef? cover;
  final List<ContentImageRef> images;
  final ContentVideoRef? video;

  final List<IntersectionReason> intersectionReasons;
  final List<String> tags;

  /// 长文模板 / 字体预设（仅 article 有意义）。
  final String articleTemplate;
  final String articleFontPreset;

  final ContentSurfaceReferral referral;

  bool get hasImages => images.isNotEmpty;
  bool get hasVideo => video != null;
  bool get hasIntersectionReasons => intersectionReasons.isNotEmpty;

  ContentSurfaceView copyWith({
    ContentSurfaceReferral? referral,
    List<IntersectionReason>? intersectionReasons,
  }) {
    return ContentSurfaceView(
      postId: postId,
      kind: kind,
      contentType: contentType,
      contentIdentity: contentIdentity,
      author: author,
      stats: stats,
      createdAt: createdAt,
      title: title,
      body: body,
      cover: cover,
      images: images,
      video: video,
      intersectionReasons: intersectionReasons ?? this.intersectionReasons,
      tags: tags,
      articleTemplate: articleTemplate,
      articleFontPreset: articleFontPreset,
      referral: referral ?? this.referral,
    );
  }
}
