import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_detail_view.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/article_presentation_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_presentation_values.dart';

/// 统一内容展示种类（媒体形态）。
///
/// 通过 `ContentPostViewData` 的契约派生 getter（`isVideoLike`/`isArticleLike`/`hasImages`）
/// 判别，禁止对 DTO 子类做 `is/as/whereType`（遵循 04-dart-polymorphism）。
enum ContentSurfaceKind { micro, image, video, article }

/// Pure application projection of an already validated public media delivery.
///
/// Runtime endpoint validation remains owned by the media delivery adapter. The
/// content object only carries the resulting immutable value so its public seam
/// never depends on runtime transport.
class ContentDeliveryRef {
  const ContentDeliveryRef({
    required this.url,
    this.assetId = '',
    this.version = 0,
    this.sha256,
  });

  final String url;
  final String assetId;
  final int version;
  final String? sha256;
}

/// 作者引用（强类型，替代裸 Map 作者字段）。
class ContentAuthorRef {
  const ContentAuthorRef({
    required this.id,
    required this.displayName,
    required this.avatar,
    this.background,
  });

  final String id;
  final String displayName;
  final ContentDeliveryRef? avatar;
  final ContentDeliveryRef? background;

  String get avatarUrl => avatar?.url ?? '';

  String? get backgroundUrl => background?.url;
}

/// 图片媒体引用。
class ContentImageRef {
  const ContentImageRef({required this.delivery, this.aspectRatio});

  final ContentDeliveryRef delivery;
  final double? aspectRatio;

  String get url => delivery.url;
}

/// 封面媒体引用（article 封面 / video 首帧）。
class ContentCoverRef {
  const ContentCoverRef({required this.delivery, this.aspectRatio});

  final ContentDeliveryRef delivery;
  final double? aspectRatio;

  String get url => delivery.url;
}

/// 视频媒体引用（单视频）。
class ContentVideoRef {
  const ContentVideoRef({
    required this.delivery,
    this.thumbnail,
    this.durationMs,
    this.aspectRatio,
  });

  final ContentDeliveryRef delivery;
  final ContentDeliveryRef? thumbnail;
  final int? durationMs;
  final double? aspectRatio;

  String get url => delivery.url;

  String get thumbnailUrl => thumbnail?.url ?? '';
}

/// 互动统计（强类型，替代散落的 count 字段）。
class ContentStats {
  const ContentStats({
    this.like = 0,
    this.comment = 0,
    this.share = 0,
    this.view = 0,
  });

  final int like;
  final int comment;
  final int share;
  final int view;
}

/// surface 归因上下文（仅透传埋点，不参与展示）。
class ContentSurfaceReferral {
  const ContentSurfaceReferral({this.position, this.feedRequestId});

  final int? position;
  final String? feedRequestId;
}

/// 文章富渲染载荷（仅 article 类型有意义）。
///
/// 承载文章详情/沉浸阅读真正渲染所需的结构化内容：内容块、卡片、文档、分页、
/// 排版模板与字体预设。翻页层（pageflip）继续消费其中的 [pages] / [document] /
/// [contentBlocks] 子对象，几何/绘制真相源不变（rule 11/12）。
///
/// 作者/统计/标题/正文/封面等公共字段由外层 [ContentSurfaceView] 承载，本类不重复。
class ContentArticleRender {
  const ContentArticleRender({
    this.contentHtml = '',
    this.layoutMode = 'hero',
    this.images = const <String>[],
    this.contentBlocks = const <ArticleContentBlockView>[],
    required this.document,
    this.pages = const <ArticlePageData>[],
    this.template = ArticleTemplatePreset.gentle,
    this.fontPreset = ArticleFontPreset.clean,
    this.documentSource = ArticleDetailDocumentSource.empty,
    this.isOfficial = false,
    this.badge,
  });

  final String contentHtml;

  /// 'hero'（单图）或 'carousel'（多图）。
  final String layoutMode;
  final List<String> images;
  final List<ArticleContentBlockView> contentBlocks;
  final ArticleDocumentData document;
  final List<ArticlePageData> pages;
  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final ArticleDetailDocumentSource documentSource;
  final bool isOfficial;
  final String? badge;
}

/// 统一只读内容展示模型。
///
/// 作为 feed / immersive / detail / share 四个消费 surface 的唯一只读真相源，
/// 覆盖 micro/image/video/article 四媒体类型。媒体差异由 [kind] + 强类型可选字段
/// 表达，surface widget 只读结果，不再各自从 DTO/Map 抽字段。
///
/// 字段集与 fallback 口径对齐 `quwoquan_service/services/content-service/contracts/content/post` 投影
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
    this.updatedAt,
    this.publishedAt,
    this.title,
    this.body,
    this.cover,
    this.images = const <ContentImageRef>[],
    this.video,
    this.intersectionReasons = const <IntersectionReason>[],
    this.tags = const <String>[],
    this.articleTemplate = '',
    this.articleFontPreset = '',
    this.article,
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

  /// 创作时间（内容首次进入系统）。
  final DateTime createdAt;

  /// 最后实质更新时间；null 或不晚于 [createdAt] 表示未编辑过。
  final DateTime? updatedAt;

  /// 首次公开时间；null 表示未发布或未知。
  final DateTime? publishedAt;

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

  /// 文章富渲染载荷（仅 article 详情/沉浸阅读水合后非空）。
  final ContentArticleRender? article;

  final ContentSurfaceReferral referral;

  bool get hasImages => images.isNotEmpty;
  bool get hasVideo => video != null;
  bool get hasIntersectionReasons => intersectionReasons.isNotEmpty;
  bool get hasArticleRender => article != null;

  /// 是否在创作之后发生过实质更新（决定 UI 是否展示「更新于」）。
  /// 容忍秒级抖动：仅当更新时间比创作时间晚超过 1 秒才算更新。
  bool get hasMeaningfulUpdate {
    final updated = updatedAt;
    if (updated == null) {
      return false;
    }
    return updated.difference(createdAt).inSeconds > 1;
  }

  ContentSurfaceView copyWith({
    ContentSurfaceReferral? referral,
    List<IntersectionReason>? intersectionReasons,
    List<String>? tags,
    ContentArticleRender? article,
  }) {
    return ContentSurfaceView(
      postId: postId,
      kind: kind,
      contentType: contentType,
      contentIdentity: contentIdentity,
      author: author,
      stats: stats,
      createdAt: createdAt,
      updatedAt: updatedAt,
      publishedAt: publishedAt,
      title: title,
      body: body,
      cover: cover,
      images: images,
      video: video,
      intersectionReasons: intersectionReasons ?? this.intersectionReasons,
      tags: tags ?? this.tags,
      articleTemplate: articleTemplate,
      articleFontPreset: articleFontPreset,
      article: article ?? this.article,
      referral: referral ?? this.referral,
    );
  }
}
