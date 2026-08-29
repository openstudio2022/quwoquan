part of 'article_reader_page_surfaces.dart';

class ArticleFrontispieceView extends StatelessWidget {
  const ArticleFrontispieceView({
    super.key,
    required this.page,
    required this.template,
    required this.fontPreset,
    required this.coverUrl,
    this.coverBinding = const MediaDeliveryBinding.absent(),
    this.imageKey = const ValueKey<String>('article-frontispiece-image'),
    this.paperTexture,
  });

  final ArticlePageData page;
  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final String coverUrl;

  /// 封面的 typed 交付绑定（DEC-033）。私有封面换签后仍由文章图组件渲染，
  /// 因此公开与私有两路共用同一套加载体验，不出现两种观感。
  final MediaDeliveryBinding coverBinding;

  final Key imageKey;
  final ArticlePaperTexture? paperTexture;

  @override
  Widget build(BuildContext context) {
    const coverTitleLineHeight = 1.15;
    final typography = paperTexture != null
        ? resolveArticleTypographyForPaper(context, paperTexture!, fontPreset)
        : resolveArticleTypography(context, template, fontPreset);
    final frontispieceBody = _resolvedBodyText();
    final coverTitle = page.title.trim();
    return LayoutBuilder(
      builder: (context, constraints) {
        final coverHeight = math.min(
          constraints.maxHeight * 0.3,
          constraints.maxWidth /
              (template == ArticleTemplatePreset.journal ? 0.8 : 1.1),
        );
        return Align(
          alignment: Alignment.topLeft,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              SizedBox(
                height: coverHeight,
                width: double.infinity,
                child: Stack(
                  fit: StackFit.expand,
                  children: <Widget>[
                    mediaDeliveryImage(
                      binding: coverBinding,
                      kind: MediaDeliveryKind.image,
                      publicBuilder: (context, publicUrl) =>
                          ArticleAdaptiveImage(
                            key: imageKey,
                            imageUrl: publicUrl,
                          ),
                      signedReadyBuilder:
                          (context, deliveryUrl, cacheIdentity) =>
                              ArticleAdaptiveImage(
                                key: imageKey,
                                imageUrl: coverUrl,
                                signedDeliveryUrl: deliveryUrl,
                                signedCacheIdentity: cacheIdentity,
                              ),
                    ),
                    Positioned.fill(
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: <Color>[
                              AppColors.black.withValues(alpha: 0.04),
                              AppColors.black.withValues(alpha: 0.18),
                              AppColors.black.withValues(alpha: 0.74),
                            ],
                            stops: const <double>[0.0, 0.48, 1.0],
                          ),
                        ),
                      ),
                    ),
                    if (coverTitle.isNotEmpty)
                      Positioned(
                        left: AppSpacing.containerMd,
                        right: AppSpacing.containerMd,
                        bottom: AppSpacing.containerMd,
                        child: Text(
                          coverTitle,
                          maxLines: 3,
                          overflow: TextOverflow.ellipsis,
                          style: typography.titleStyle.copyWith(
                            color: AppColors.white,
                            height: coverTitleLineHeight,
                            shadows: const <Shadow>[
                              Shadow(
                                color: AppColors.overlayLight,
                                blurRadius: 18,
                                offset: Offset(0, 4),
                              ),
                            ],
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              SizedBox(height: AppSpacing.containerMd),
              if (frontispieceBody.isNotEmpty)
                Text(frontispieceBody, style: typography.bodyStyle),
            ],
          ),
        );
      },
    );
  }

  String _resolvedBodyText() {
    final body = page.body.trim();
    if (body.isNotEmpty) {
      return body;
    }
    return page.contentBlocks
        .where((block) => block.isTextLike && block.hasText)
        .map((block) => block.text.trim())
        .where((value) => value.isNotEmpty)
        .join('\n');
  }
}
