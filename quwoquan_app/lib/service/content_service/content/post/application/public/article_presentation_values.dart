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

enum ArticlePaperTexture { darkPaper, coolGray, warmBlack, inkGreen, deepBrown }

extension ArticlePaperTextureX on ArticlePaperTexture {
  String get label => switch (this) {
    ArticlePaperTexture.darkPaper => '深色纸',
    ArticlePaperTexture.coolGray => '冷灰纸',
    ArticlePaperTexture.warmBlack => '暖黑纸',
    ArticlePaperTexture.inkGreen => '墨绿纸',
    ArticlePaperTexture.deepBrown => '深棕纸',
  };
}

ArticlePaperTexture articlePaperTextureFromString(String? value) {
  return switch ((value ?? '').trim()) {
    'coolGray' || 'quiet' => ArticlePaperTexture.coolGray,
    'warmBlack' || 'cream' || 'sepia' => ArticlePaperTexture.warmBlack,
    'inkGreen' || 'eyeCare' => ArticlePaperTexture.inkGreen,
    'deepBrown' || 'parchment' => ArticlePaperTexture.deepBrown,
    'darkPaper' || 'night' || 'white' => ArticlePaperTexture.darkPaper,
    _ => ArticlePaperTexture.darkPaper,
  };
}

ArticlePaperTexture paperTextureFromTemplate(ArticleTemplatePreset template) {
  return switch (template) {
    ArticleTemplatePreset.gentle => ArticlePaperTexture.warmBlack,
    ArticleTemplatePreset.ritual => ArticlePaperTexture.deepBrown,
    ArticleTemplatePreset.diffuse => ArticlePaperTexture.darkPaper,
    ArticleTemplatePreset.journal => ArticlePaperTexture.inkGreen,
    ArticleTemplatePreset.tech => ArticlePaperTexture.coolGray,
  };
}

enum ArticleCanvasVariant { editor, preview, detail, immersive, thumbnail }

class ArticleEdgeInsetsView {
  const ArticleEdgeInsetsView({
    required this.left,
    required this.top,
    required this.right,
    required this.bottom,
  });

  static const zero = ArticleEdgeInsetsView(
    left: 0,
    top: 0,
    right: 0,
    bottom: 0,
  );

  final double left;
  final double top;
  final double right;
  final double bottom;
}

/// Pure cross-object view of the article canvas geometry.
///
/// Flutter layout types stay inside each object's presentation boundary. The
/// media viewer can author this value while the Post presentation maps it to
/// its private canvas implementation.
class ArticleCanvasMetricsView {
  const ArticleCanvasMetricsView({
    required this.aspectRatio,
    required this.outerPadding,
    required this.contentPadding,
    required this.headerReservedHeight,
    required this.footerReservedHeight,
    required this.wrapImageGap,
    required this.wrapImageMaxWidth,
    required this.fullWidthImageAspectRatio,
    required this.journalImageAspectRatio,
    required this.inlineImageSpacing,
  });

  final double aspectRatio;
  final ArticleEdgeInsetsView outerPadding;
  final ArticleEdgeInsetsView contentPadding;
  final double headerReservedHeight;
  final double footerReservedHeight;
  final double wrapImageGap;
  final double wrapImageMaxWidth;
  final double fullWidthImageAspectRatio;
  final double journalImageAspectRatio;
  final double inlineImageSpacing;
}
