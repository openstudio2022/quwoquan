import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';

enum ArticleTemplatePreset { gentle, ritual, diffuse, journal, tech }

extension ArticleTemplatePresetX on ArticleTemplatePreset {
  String get label => switch (this) {
    ArticleTemplatePreset.gentle => '柔和',
    ArticleTemplatePreset.ritual => '礼记',
    ArticleTemplatePreset.diffuse => '弥散',
    ArticleTemplatePreset.journal => '手帐',
    ArticleTemplatePreset.tech => '科技',
  };
}

ArticleTemplatePreset articleTemplatePresetFromString(String? value) {
  return switch ((value ?? '').trim()) {
    'ritual' => ArticleTemplatePreset.ritual,
    'diffuse' => ArticleTemplatePreset.diffuse,
    'journal' => ArticleTemplatePreset.journal,
    'tech' => ArticleTemplatePreset.tech,
    _ => ArticleTemplatePreset.gentle,
  };
}

enum ArticleFontPreset { clean, classic, handwritten, rounded, mono }

extension ArticleFontPresetX on ArticleFontPreset {
  String get label => switch (this) {
    ArticleFontPreset.clean => '清雅',
    ArticleFontPreset.classic => '经典',
    ArticleFontPreset.handwritten => '手写',
    ArticleFontPreset.rounded => '圆体',
    ArticleFontPreset.mono => '等宽',
  };
}

ArticleFontPreset articleFontPresetFromString(String? value) {
  return switch ((value ?? '').trim()) {
    'classic' => ArticleFontPreset.classic,
    'handwritten' => ArticleFontPreset.handwritten,
    'rounded' => ArticleFontPreset.rounded,
    'mono' => ArticleFontPreset.mono,
    _ => ArticleFontPreset.clean,
  };
}

@immutable
class ArticlePageData {
  const ArticlePageData({
    required this.id,
    this.title = '',
    this.body = '',
    this.imageUrl = '',
    this.imageLayout = 'fullWidth',
    this.caption = '',
    this.contentBlocks = const <ArticleDocumentBlock>[],
    this.binding,
  });

  factory ArticlePageData.fromMap(Map<String, dynamic> map) {
    return ArticlePageData(
      id: (map['id'] ?? '').toString(),
      title: (map['title'] ?? '').toString(),
      body: (map['body'] ?? '').toString(),
      imageUrl: (map['imageUrl'] ?? map['imagePath'] ?? '').toString(),
      imageLayout: (map['imageLayout'] ?? 'fullWidth').toString(),
      caption: (map['caption'] ?? '').toString(),
    );
  }

  final String id;
  final String title;
  final String body;
  final String imageUrl;
  final String imageLayout;
  final String caption;
  final List<ArticleDocumentBlock> contentBlocks;
  final ArticlePageBinding? binding;

  bool get hasText =>
      title.trim().isNotEmpty ||
      body.trim().isNotEmpty ||
      contentBlocks.any((block) => block.isTextLike && block.hasText);
  bool get hasImage => imageUrl.trim().isNotEmpty;
  bool get isEmpty => !hasText && !hasImage;
  bool get usesWrappedLayout =>
      imageLayout == 'wrapLeft' || imageLayout == 'wrapRight';

  ArticlePageData copyWith({
    String? id,
    String? title,
    String? body,
    String? imageUrl,
    String? imageLayout,
    String? caption,
    List<ArticleDocumentBlock>? contentBlocks,
    ArticlePageBinding? binding,
  }) {
    return ArticlePageData(
      id: id ?? this.id,
      title: title ?? this.title,
      body: body ?? this.body,
      imageUrl: imageUrl ?? this.imageUrl,
      imageLayout: imageLayout ?? this.imageLayout,
      caption: caption ?? this.caption,
      contentBlocks: contentBlocks ?? this.contentBlocks,
      binding: binding ?? this.binding,
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'id': id,
      'title': title,
      'body': body,
      'imageUrl': imageUrl,
      'imageLayout': imageLayout,
      'caption': caption,
    };
  }
}

enum ArticleCanvasVariant { editor, preview, detail, immersive, thumbnail }

@immutable
class ArticleCanvasMetrics {
  const ArticleCanvasMetrics({
    required this.aspectRatio,
    required this.outerPadding,
    required this.contentPadding,
    required this.wrapImageGap,
    required this.wrapImageMaxWidth,
    required this.fullWidthImageAspectRatio,
    required this.journalImageAspectRatio,
    required this.inlineImageSpacing,
  });

  factory ArticleCanvasMetrics.snapshot() {
    return const ArticleCanvasMetrics(
      aspectRatio: 0.72,
      outerPadding: EdgeInsets.all(AppSpacing.containerSm),
      contentPadding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerLg,
        AppSpacing.containerMd,
        AppSpacing.containerMd,
      ),
      wrapImageGap: AppSpacing.containerSm,
      wrapImageMaxWidth: 132,
      fullWidthImageAspectRatio: 4 / 3,
      journalImageAspectRatio: 1,
      inlineImageSpacing: AppSpacing.intraGroupSm,
    );
  }

  final double aspectRatio;
  final EdgeInsets outerPadding;
  final EdgeInsets contentPadding;
  final double wrapImageGap;
  final double wrapImageMaxWidth;
  final double fullWidthImageAspectRatio;
  final double journalImageAspectRatio;
  final double inlineImageSpacing;

  Size contentSizeForStageWidth(double stageWidth) {
    final safeStageWidth = math.max(stageWidth, 1);
    final paperWidth = math.max(0, safeStageWidth - outerPadding.horizontal);
    final paperHeight = math.max(0, (paperWidth / aspectRatio) - outerPadding.vertical);
    return Size(
      math.max(0, paperWidth - contentPadding.horizontal),
      math.max(0, paperHeight - contentPadding.vertical),
    );
  }

  double wrapImageWidthForContent(double contentWidth) {
    return math.min(wrapImageMaxWidth, contentWidth * 0.42);
  }
}

ArticleCanvasMetrics resolveArticleCanvasMetrics(
  BuildContext context,
  BoxConstraints constraints, {
  ArticleCanvasVariant variant = ArticleCanvasVariant.preview,
}) {
  final width = constraints.maxWidth.isFinite
      ? constraints.maxWidth
      : MediaQuery.sizeOf(context).width;
  final aspectRatio = switch (variant) {
    ArticleCanvasVariant.thumbnail => 72 / 104,
    _ => AppSpacing.responsiveValue(
      context,
      compact: 0.74,
      regular: width >= 430 ? 0.72 : 0.74,
      expanded: 0.82,
    ),
  };
  final outerPadding = switch (variant) {
    ArticleCanvasVariant.thumbnail => const EdgeInsets.all(AppSpacing.two),
    _ => EdgeInsets.all(
      AppSpacing.responsiveValue(
        context,
        compact: AppSpacing.containerXs,
        regular: AppSpacing.containerSm,
        expanded: AppSpacing.containerMd,
      ),
    ),
  };
  final contentPadding = switch (variant) {
    ArticleCanvasVariant.thumbnail => const EdgeInsets.fromLTRB(8, 10, 8, 8),
    _ => EdgeInsets.fromLTRB(
      AppSpacing.responsiveValue(
        context,
        compact: AppSpacing.containerSm,
        regular: AppSpacing.containerMd,
        expanded: AppSpacing.containerLg,
      ),
      AppSpacing.responsiveValue(
        context,
        compact: AppSpacing.containerMd,
        regular: AppSpacing.containerLg,
        expanded: AppSpacing.containerXl,
      ),
      AppSpacing.responsiveValue(
        context,
        compact: AppSpacing.containerSm,
        regular: AppSpacing.containerMd,
        expanded: AppSpacing.containerLg,
      ),
      AppSpacing.responsiveValue(
        context,
        compact: AppSpacing.containerSm,
        regular: AppSpacing.containerMd,
        expanded: AppSpacing.containerLg,
      ),
    ),
  };
  return ArticleCanvasMetrics(
    aspectRatio: aspectRatio,
    outerPadding: outerPadding,
    contentPadding: contentPadding,
    wrapImageGap: AppSpacing.responsiveValue(
      context,
      compact: AppSpacing.intraGroupXs,
      regular: AppSpacing.containerSm,
      expanded: AppSpacing.containerMd,
    ),
    wrapImageMaxWidth: AppSpacing.responsiveValue(
      context,
      compact: 112,
      regular: 132,
      expanded: 168,
    ),
    fullWidthImageAspectRatio: 4 / 3,
    journalImageAspectRatio: 1,
    inlineImageSpacing: AppSpacing.intraGroupSm,
  );
}
