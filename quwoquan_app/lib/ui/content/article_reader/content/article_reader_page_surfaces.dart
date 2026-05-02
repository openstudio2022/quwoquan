import 'dart:math' as math;
import 'dart:ui' show ImageFilter, lerpDouble;

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/article_reader/templates/article_reader_template_theme.dart';
import 'package:quwoquan_app/ui/content/widgets/article_content_block_renderer.dart';

class ArticlePageShell extends StatelessWidget {
  const ArticlePageShell({
    super.key,
    required this.template,
    required this.fontPreset,
    required this.pageIndex,
    required this.totalPages,
    required this.child,
    this.aspectRatio = 0.72,
    this.outerPadding,
    this.contentPadding,
    this.headerReservedHeight,
    this.footerReservedHeight,
    this.showIndicator = true,
    this.variant = ArticlePageShellVariant.book,
    this.headerLabel,
    this.footerLabel,
    this.paperTexture,
  });

  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final int pageIndex;
  final int totalPages;
  final Widget child;
  final double aspectRatio;
  final EdgeInsets? outerPadding;
  final EdgeInsets? contentPadding;
  final double? headerReservedHeight;
  final double? footerReservedHeight;
  final bool showIndicator;
  final ArticlePageShellVariant variant;
  final String? headerLabel;
  final String? footerLabel;

  /// 非 null 时纸张/正文色取自纸张质感，与模版几何（圆角、手帐裁剪等）仍由 [template] 决定。
  final ArticlePaperTexture? paperTexture;

  @override
  Widget build(BuildContext context) {
    final palette = paperTexture != null
        ? resolveArticlePaperPalette(context, paperTexture!)
        : resolveArticleTemplatePalette(context, template);
    final headerText = headerLabel?.trim() ?? '';
    final footerText = footerLabel?.trim() ?? '';
    final resolvedOuterPadding =
        outerPadding ?? EdgeInsets.all(AppSpacing.containerSm);
    final resolvedContentPadding =
        contentPadding ??
        EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.containerLg,
          AppSpacing.containerMd,
          AppSpacing.containerMd,
        );
    final resolvedHeaderHeight =
        headerReservedHeight ??
        AppSpacing.sm + AppSpacing.hairline + AppSpacing.intraGroupSm * 2;
    final resolvedFooterHeight =
        footerReservedHeight ??
        AppSpacing.sm + AppSpacing.hairline + AppSpacing.interGroupSm;

    Widget buildPageContent({required bool expandBody}) {
      final content = <Widget>[
        if (headerText.isNotEmpty) ...<Widget>[
          Text(
            headerText,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: palette.secondaryTextColor.withValues(alpha: 0.86),
              fontSize: AppTypography.sm,
              fontWeight: AppTypography.medium,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          DecoratedBox(
            decoration: BoxDecoration(
              border: Border(
                bottom: BorderSide(
                  color: palette.paperBorderColor.withValues(alpha: 0.5),
                  width: AppSpacing.hairline,
                ),
              ),
            ),
            child: SizedBox(height: AppSpacing.hairline),
          ),
          SizedBox(height: math.max(0, resolvedHeaderHeight - AppSpacing.sm)),
        ],
        if (expandBody) Expanded(child: child) else child,
        if (footerText.isNotEmpty) ...<Widget>[
          SizedBox(height: math.max(0, resolvedFooterHeight - AppSpacing.sm)),
          DecoratedBox(
            decoration: BoxDecoration(
              border: Border(
                top: BorderSide(
                  color: palette.paperBorderColor.withValues(alpha: 0.5),
                  width: AppSpacing.hairline,
                ),
              ),
            ),
            child: SizedBox(height: AppSpacing.hairline),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Align(
            alignment: Alignment.center,
            child: Text(
              footerText,
              style: TextStyle(
                color: palette.secondaryTextColor.withValues(alpha: 0.86),
                fontSize: AppTypography.sm,
                fontWeight: AppTypography.medium,
              ),
            ),
          ),
        ],
      ];
      return Padding(
        padding: resolvedContentPadding,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: expandBody ? MainAxisSize.max : MainAxisSize.min,
          children: content,
        ),
      );
    }

    Widget buildFlatPaper({
      required bool showShadow,
      required double borderAlpha,
    }) {
      Widget paper = DecoratedBox(
        decoration: BoxDecoration(
          color: palette.paperColor,
          border: Border(
            top: BorderSide(
              color: palette.paperBorderColor.withValues(alpha: borderAlpha),
              width: AppSpacing.hairline,
            ),
            left: BorderSide(
              color: palette.paperBorderColor.withValues(
                alpha: borderAlpha * 0.72,
              ),
              width: AppSpacing.hairline,
            ),
            right: BorderSide(
              color: palette.paperBorderColor.withValues(
                alpha: borderAlpha * 0.72,
              ),
              width: AppSpacing.hairline,
            ),
            bottom: BorderSide(
              color: palette.paperBorderColor.withValues(
                alpha: borderAlpha + 0.08,
              ),
              width: AppSpacing.hairline,
            ),
          ),
          boxShadow: showShadow
              ? <BoxShadow>[
                  BoxShadow(
                    color: AppColors.black.withValues(alpha: 0.18),
                    blurRadius: 24,
                    offset: const Offset(0, 10),
                  ),
                ]
              : null,
        ),
        child: buildPageContent(expandBody: true),
      );
      if (template == ArticleTemplatePreset.journal) {
        paper = CustomPaint(
          foregroundPainter: _JournalPaperTexturePainter(palette),
          child: paper,
        );
      }
      return Padding(padding: resolvedOuterPadding, child: paper);
    }

    if (variant == ArticlePageShellVariant.plainEdit ||
        variant == ArticlePageShellVariant.readerSheet) {
      final paper = buildFlatPaper(
        showShadow: variant == ArticlePageShellVariant.readerSheet,
        borderAlpha: variant == ArticlePageShellVariant.readerSheet
            ? 0.16
            : 0.24,
      );
      final sheet = AspectRatio(aspectRatio: aspectRatio, child: paper);
      if (!showIndicator) {
        return sheet;
      }
      return Stack(
        clipBehavior: Clip.none,
        children: <Widget>[
          sheet,
          Positioned(
            top: resolvedOuterPadding.top + AppSpacing.intraGroupXs,
            right: resolvedOuterPadding.right + AppSpacing.intraGroupXs,
            child: _ArticlePageIndicator(
              label: '${pageIndex + 1}/$totalPages',
              palette: palette,
            ),
          ),
        ],
      );
    }

    Widget paper = DecoratedBox(
      decoration: BoxDecoration(
        color: palette.paperColor,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyEight),
        border: Border.all(
          color: palette.paperBorderColor,
          width: AppSpacing.hairline,
        ),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: palette.shadowColor,
            blurRadius: 24,
            offset: const Offset(0, 14),
          ),
        ],
      ),
      child: buildPageContent(expandBody: true),
    );

    if (template == ArticleTemplatePreset.journal) {
      paper = ClipPath(
        clipper: const _JournalPaperClipper(),
        child: DecoratedBox(
          decoration: BoxDecoration(
            boxShadow: <BoxShadow>[
              BoxShadow(
                color: palette.shadowColor,
                blurRadius: 26,
                offset: const Offset(0, 16),
              ),
            ],
          ),
          child: CustomPaint(
            foregroundPainter: _JournalPaperTexturePainter(palette),
            child: paper,
          ),
        ),
      );
    } else {
      paper = RepaintBoundary(child: paper);
    }

    return AspectRatio(
      aspectRatio: aspectRatio,
      child: Stack(
        children: <Widget>[
          Positioned.fill(
            child: _ArticleBackdrop(template: template, palette: palette),
          ),
          Positioned.fill(
            child: Padding(
              padding: resolvedOuterPadding,
              child: IgnorePointer(
                child: CustomPaint(
                  painter: _ArticleBookChromePainter(
                    template: template,
                    palette: palette,
                    pageIndex: pageIndex,
                    totalPages: totalPages,
                  ),
                ),
              ),
            ),
          ),
          Positioned.fill(
            child: Padding(padding: resolvedOuterPadding, child: paper),
          ),
          if (showIndicator)
            Positioned(
              top: AppSpacing.containerMd,
              right: AppSpacing.containerMd,
              child: _ArticlePageIndicator(
                label: '${pageIndex + 1}/$totalPages',
                palette: palette,
              ),
            ),
        ],
      ),
    );
  }
}

class ArticlePageReadOnlyView extends StatelessWidget {
  const ArticlePageReadOnlyView({
    super.key,
    required this.page,
    required this.template,
    required this.fontPreset,
    this.metrics,
    this.paperTexture,
  });

  final ArticlePageData page;
  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final ArticleCanvasMetrics? metrics;
  final ArticlePaperTexture? paperTexture;

  @override
  Widget build(BuildContext context) {
    final typography = paperTexture != null
        ? resolveArticleTypographyForPaper(context, paperTexture!, fontPreset)
        : resolveArticleTypography(context, template, fontPreset);
    return ClipRect(
      child: SingleChildScrollView(
        physics: const NeverScrollableScrollPhysics(),
        child: Align(
          alignment: Alignment.topLeft,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: _buildReadOnlyPageFragments(
              context,
              page,
              typography,
              template,
              metrics ?? ArticleCanvasMetrics.snapshot(),
            ),
          ),
        ),
      ),
    );
  }
}

List<ArticleLayoutFragment> _resolveReadOnlyFragments(ArticlePageData page) {
  if (page.fragments.isNotEmpty) {
    return page.fragments;
  }
  final fragments = <ArticleLayoutFragment>[];
  if (page.title.trim().isNotEmpty) {
    fragments.add(
      ArticleLayoutFragment(
        kind: ArticleLayoutFragmentKind.title,
        text: page.title.trim(),
        textStyleKey: 'title',
      ),
    );
  }
  for (final block in page.contentBlocks) {
    if (block.type == ArticleDocumentBlockType.image &&
        block.imageUrl.trim().isNotEmpty) {
      fragments.add(
        ArticleLayoutFragment(
          kind:
              block.imageLayout == 'wrapLeft' ||
                  block.imageLayout == 'wrapRight'
              ? ArticleLayoutFragmentKind.wrapContent
              : ArticleLayoutFragmentKind.fullWidthImage,
          text: page.body.trim(),
          asset: ArticleDocumentAsset(
            id: block.id,
            offset: block.offset,
            imageUrl: block.imageUrl,
            imageLayout: block.imageLayout,
            caption: block.caption,
          ),
        ),
      );
      continue;
    }
    fragments.add(
      ArticleLayoutFragment(
        kind: ArticleLayoutFragmentKind.semanticBlock,
        block: block,
        text: block.text.trim(),
        textStyleKey: switch (block.type) {
          ArticleDocumentBlockType.heading2 => 'heading2',
          ArticleDocumentBlockType.heading3 => 'heading3',
          ArticleDocumentBlockType.sectionTitle => 'sectionTitle',
          ArticleDocumentBlockType.orderedItem => 'orderedItem',
          ArticleDocumentBlockType.bulletItem => 'bulletItem',
          _ => 'body',
        },
        textAlign: block.textAlign,
      ),
    );
  }
  if (page.imageUrl.trim().isNotEmpty &&
      !fragments.any((fragment) => fragment.hasAsset)) {
    fragments.add(
      ArticleLayoutFragment(
        kind: page.usesWrappedLayout
            ? ArticleLayoutFragmentKind.wrapContent
            : ArticleLayoutFragmentKind.fullWidthImage,
        text: page.body.trim(),
        asset: ArticleDocumentAsset(
          id: '${page.id}_asset',
          offset: 0,
          imageUrl: page.imageUrl,
          imageLayout: page.imageLayout,
          caption: page.caption,
        ),
      ),
    );
    if (!page.usesWrappedLayout && page.body.trim().isNotEmpty) {
      fragments.add(
        ArticleLayoutFragment(
          kind: ArticleLayoutFragmentKind.body,
          text: page.body.trim(),
          textStyleKey: 'body',
        ),
      );
    }
  } else if (page.body.trim().isNotEmpty &&
      !fragments.any(
        (fragment) =>
            fragment.kind == ArticleLayoutFragmentKind.body ||
            fragment.kind == ArticleLayoutFragmentKind.wrapContent,
      )) {
    fragments.add(
      ArticleLayoutFragment(
        kind: ArticleLayoutFragmentKind.body,
        text: page.body.trim(),
        textStyleKey: 'body',
      ),
    );
  }
  return fragments;
}

List<Widget> _buildReadOnlyPageFragments(
  BuildContext context,
  ArticlePageData page,
  ArticleTypographySpec typography,
  ArticleTemplatePreset template,
  ArticleCanvasMetrics metrics,
) {
  final fragments = _resolveReadOnlyFragments(page);
  final widgets = <Widget>[];
  final spacing = articleSpacingResolver();
  for (var index = 0; index < fragments.length; index += 1) {
    final fragment = fragments[index];
    final nextFragment = index + 1 < fragments.length
        ? fragments[index + 1]
        : null;
    var appended = false;
    switch (fragment.kind) {
      case ArticleLayoutFragmentKind.title:
        widgets.add(Text(fragment.text.trim(), style: typography.titleStyle));
        appended = true;
        break;
      case ArticleLayoutFragmentKind.semanticBlock:
        if (fragment.block == null) {
          break;
        }
        widgets.add(
          _ArticleSemanticBlock(block: fragment.block!, typography: typography),
        );
        appended = true;
        break;
      case ArticleLayoutFragmentKind.fullWidthImage:
        if (!fragment.hasAsset) {
          break;
        }
        widgets.add(
          _ArticlePageImage(
            imageUrl: fragment.asset!.imageUrl.trim(),
            borderRadius: 0,
            aspectRatio: fragment.asset!.imageLayout == 'journalCard'
                ? metrics.journalImageAspectRatio
                : metrics.fullWidthImageAspectRatio,
          ),
        );
        if (fragment.asset!.caption.trim().isNotEmpty) {
          widgets.add(
            SizedBox(
              height: spacing.between(
                ArticleSpacingSemantic.figure,
                ArticleSpacingSemantic.caption,
              ),
            ),
          );
          widgets.add(
            Center(
              child: Text(
                fragment.asset!.caption.trim(),
                textAlign: TextAlign.center,
                style: typography.captionStyle,
              ),
            ),
          );
        }
        appended = true;
        break;
      case ArticleLayoutFragmentKind.wrapContent:
        if (!fragment.hasAsset) {
          break;
        }
        widgets.add(
          ArticleWrappedParagraph(
            imageUrl: fragment.asset!.imageUrl.trim(),
            body: fragment.text.trim(),
            leadingText: fragment.leadingText,
            trailingText: fragment.trailingText,
            imageLayout: fragment.asset!.imageLayout,
            caption: fragment.asset!.caption,
            metrics: metrics,
          ),
        );
        appended = true;
        break;
      case ArticleLayoutFragmentKind.body:
        if (fragment.text.trim().isNotEmpty) {
          widgets.add(Text(fragment.text.trim(), style: typography.bodyStyle));
          appended = true;
        }
        break;
    }
    if (!appended || nextFragment == null) {
      continue;
    }
    final prevSemantic = articleSpacingSemanticForFragment(fragment);
    final nextSemantic = articleSpacingSemanticForFragment(nextFragment);
    final double gap;
    if (prevSemantic == ArticleSpacingSemantic.figure &&
        nextSemantic == ArticleSpacingSemantic.figure) {
      gap = spacing.betweenConsecutiveFigures();
    } else {
      gap = spacing.between(prevSemantic, nextSemantic);
    }
    if (gap > 0) {
      widgets.add(SizedBox(height: gap));
    }
  }
  return widgets;
}

class ArticleFrontispieceView extends StatelessWidget {
  const ArticleFrontispieceView({
    super.key,
    required this.page,
    required this.template,
    required this.fontPreset,
    required this.coverUrl,
    this.imageKey = const ValueKey<String>('article-frontispiece-image'),
    this.paperTexture,
  });

  final ArticlePageData page;
  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final String coverUrl;
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
                    ArticleAdaptiveImage(key: imageKey, imageUrl: coverUrl),
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

class _ArticleBackdrop extends StatelessWidget {
  const _ArticleBackdrop({required this.template, required this.palette});

  final ArticleTemplatePreset template;
  final ArticleTemplatePalette palette;

  @override
  Widget build(BuildContext context) {
    const journalTapePrimaryWidth = 74.0;
    const journalTapePrimaryHeight = 24.0;
    const journalTapeSecondaryWidth = 58.0;
    const journalTapeSecondaryHeight = 20.0;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: palette.stageBackground,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyEight + 6),
      ),
      child: Stack(
        children: <Widget>[
          if (template == ArticleTemplatePreset.gentle) ...<Widget>[
            Positioned(
              top: -20,
              left: -10,
              child: _BackdropBlob(
                width: AppSpacing.oneHundred + AppSpacing.twenty,
                height: AppSpacing.storyHeight,
                color: palette.accentColor.withValues(alpha: 0.16),
              ),
            ),
            Positioned(
              bottom: 10,
              right: -14,
              child: _BackdropBlob(
                width: AppSpacing.oneHundred + AppSpacing.buttonHeightSm,
                height: AppSpacing.storyHeight + AppSpacing.sm,
                color: ArticleTemplateColors.gentleBackdropMint.withValues(
                  alpha: 0.26,
                ),
              ),
            ),
          ],
          if (template == ArticleTemplatePreset.ritual)
            Positioned.fill(
              child: CustomPaint(painter: _RitualBackdropPainter(palette)),
            ),
          if (template == ArticleTemplatePreset.diffuse) ...<Widget>[
            Positioned(
              top: -18,
              right: -18,
              child: _BackdropBlob(
                width:
                    AppSpacing.oneHundred + AppSpacing.forty + AppSpacing.ten,
                height: AppSpacing.oneHundred + AppSpacing.twenty,
                color: ArticleTemplateColors.diffuseBackdropLavender.withValues(
                  alpha: 0.3,
                ),
              ),
            ),
            Positioned(
              bottom: -12,
              left: -10,
              child: _BackdropBlob(
                width: AppSpacing.oneHundred + AppSpacing.forty,
                height: AppSpacing.largeButtonSize * 2,
                color: ArticleTemplateColors.diffuseBackdropPink.withValues(
                  alpha: 0.26,
                ),
              ),
            ),
          ],
          if (template == ArticleTemplatePreset.journal) ...<Widget>[
            Positioned.fill(
              child: CustomPaint(painter: _JournalBackdropPainter(palette)),
            ),
            Positioned(
              top: 18,
              left: 18,
              child: _JournalTapeDecoration(
                width: journalTapePrimaryWidth,
                height: journalTapePrimaryHeight,
                angle: -0.16,
                color: ArticleTemplateColors.journalTape.withValues(
                  alpha: 0.92,
                ),
              ),
            ),
            Positioned(
              top: 34,
              right: 24,
              child: _JournalTapeDecoration(
                width: journalTapeSecondaryWidth,
                height: journalTapeSecondaryHeight,
                angle: 0.2,
                color: ArticleTemplateColors.journalTape.withValues(alpha: 0.7),
              ),
            ),
            Positioned(
              bottom: 36,
              right: 18,
              child: const _JournalStickerDecoration(
                label: 'MEMO',
                angle: 0.12,
              ),
            ),
            Positioned(
              bottom: 56,
              left: 24,
              child: const _JournalStickerDecoration(
                label: 'TODAY',
                angle: -0.08,
                compact: true,
              ),
            ),
          ],
          if (template == ArticleTemplatePreset.tech)
            Positioned.fill(
              child: CustomPaint(painter: _TechBackdropPainter(palette)),
            ),
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: palette.overlayColor,
                borderRadius: BorderRadius.circular(
                  AppSpacing.radiusTwentyEight + 6,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ArticlePageIndicator extends StatelessWidget {
  const _ArticlePageIndicator({required this.label, required this.palette});

  final String label;
  final ArticleTemplatePalette palette;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: palette.badgeBackground,
            borderRadius: BorderRadius.circular(
              AppSpacing.circularBorderRadius,
            ),
            border: Border.all(
              color: palette.paperBorderColor.withValues(alpha: 0.6),
              width: AppSpacing.hairline,
            ),
          ),
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.containerSm,
              vertical: AppSpacing.intraGroupXs,
            ),
            child: Text(
              label,
              style: TextStyle(
                color: palette.badgeTextColor,
                fontSize: AppTypography.xs,
                fontWeight: AppTypography.semiBold,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ArticleBookChromePainter extends CustomPainter {
  const _ArticleBookChromePainter({
    required this.template,
    required this.palette,
    required this.pageIndex,
    required this.totalPages,
  });

  final ArticleTemplatePreset template;
  final ArticleTemplatePalette palette;
  final int pageIndex;
  final int totalPages;

  @override
  void paint(Canvas canvas, Size size) {
    final spineWidth = lerpDouble(
      18,
      26,
      math.min(totalPages / 12, 1).toDouble(),
    )!;
    final spineRect = Rect.fromLTWH(0, 0, spineWidth, size.height);
    final spinePaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.centerLeft,
        end: Alignment.centerRight,
        colors: <Color>[
          AppColors.black.withValues(alpha: 0.18),
          palette.paperBorderColor.withValues(alpha: 0.16),
          AppColors.white.withValues(alpha: 0.08),
        ],
      ).createShader(spineRect);
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        spineRect,
        const Radius.circular(AppSpacing.radiusTwentyEight),
      ),
      spinePaint,
    );

    final foreEdgeRect = Rect.fromLTWH(size.width - 18, 0, 18, size.height);
    final foreEdgePaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.centerLeft,
        end: Alignment.centerRight,
        colors: <Color>[
          palette.paperBorderColor.withValues(alpha: 0.04),
          palette.paperBorderColor.withValues(alpha: 0.2),
          AppColors.white.withValues(alpha: 0.22),
        ],
      ).createShader(foreEdgeRect);
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        foreEdgeRect,
        const Radius.circular(AppSpacing.radiusTwentyEight),
      ),
      foreEdgePaint,
    );

    switch (template) {
      case ArticleTemplatePreset.ritual:
        final embossPaint = Paint()
          ..color = palette.accentColor.withValues(alpha: 0.18)
          ..strokeWidth = 1.4;
        canvas.drawLine(
          Offset(spineWidth + 6, 18),
          Offset(spineWidth + 6, size.height - 18),
          embossPaint,
        );
        canvas.drawLine(
          Offset(spineWidth + 11, 18),
          Offset(spineWidth + 11, size.height - 18),
          embossPaint,
        );
        break;
      case ArticleTemplatePreset.diffuse:
        final hazePaint = Paint()
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 18)
          ..color = palette.accentColor.withValues(alpha: 0.14);
        canvas.drawCircle(
          Offset(size.width * 0.86, size.height * 0.18),
          12,
          hazePaint,
        );
        canvas.drawCircle(
          Offset(size.width * 0.14, size.height * 0.82),
          14,
          hazePaint,
        );
        break;
      case ArticleTemplatePreset.journal:
        final holePaint = Paint()
          ..color = palette.paperBorderColor.withValues(alpha: 0.3);
        for (var index = 0; index < 6; index += 1) {
          final dy = 42.0 + (index * ((size.height - 84) / 5));
          canvas.drawCircle(Offset(spineWidth + 6, dy), 2.4, holePaint);
        }
        break;
      case ArticleTemplatePreset.tech:
        final techPaint = Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.2
          ..color = palette.accentColor.withValues(alpha: 0.42);
        final path = Path()
          ..moveTo(size.width - 28, 22)
          ..lineTo(size.width - 16, 22)
          ..lineTo(size.width - 16, 42)
          ..lineTo(size.width - 8, 42)
          ..moveTo(size.width - 30, size.height - 22)
          ..lineTo(size.width - 18, size.height - 22)
          ..lineTo(size.width - 18, size.height - 42)
          ..lineTo(size.width - 10, size.height - 42);
        canvas.drawPath(path, techPaint);
        break;
      case ArticleTemplatePreset.gentle:
        final ribbonPaint = Paint()
          ..color = palette.accentColor.withValues(alpha: 0.14)
          ..strokeWidth = 2.2
          ..strokeCap = StrokeCap.round;
        final ribbonInset = 16 + (pageIndex % 2) * 2;
        canvas.drawLine(
          Offset(spineWidth + ribbonInset, 24),
          Offset(spineWidth + ribbonInset, size.height - 24),
          ribbonPaint,
        );
        break;
    }
  }

  @override
  bool shouldRepaint(covariant _ArticleBookChromePainter oldDelegate) {
    return oldDelegate.template != template ||
        oldDelegate.palette != palette ||
        oldDelegate.pageIndex != pageIndex ||
        oldDelegate.totalPages != totalPages;
  }
}

class _ArticleSemanticBlock extends StatelessWidget {
  const _ArticleSemanticBlock({required this.block, required this.typography});

  final ArticleDocumentBlock block;
  final ArticleTypographySpec typography;

  @override
  Widget build(BuildContext context) {
    final titleFont = typography.titleStyle.fontSize ?? AppTypography.xl;
    final bodyFont = typography.bodyStyle.fontSize ?? AppTypography.base;
    final style = switch (block.type) {
      ArticleDocumentBlockType.heading2 => typography.titleStyle.copyWith(
        fontSize: titleFont * 0.82,
        fontWeight: AppTypography.semiBold,
      ),
      ArticleDocumentBlockType.heading3 => typography.bodyStyle.copyWith(
        fontSize: math.max(bodyFont * 1.14, 18),
        fontWeight: AppTypography.semiBold,
      ),
      ArticleDocumentBlockType.sectionTitle => typography.titleStyle.copyWith(
        fontSize: math.max(bodyFont * 1.28, 20),
        fontWeight: AppTypography.bold,
        letterSpacing: 0.18,
      ),
      _ => typography.bodyStyle,
    };
    return Text(block.text.trim(), style: style);
  }
}

class _ArticlePageImage extends StatelessWidget {
  const _ArticlePageImage({
    required this.imageUrl,
    required this.borderRadius,
    required this.aspectRatio,
  });

  final String imageUrl;
  final double borderRadius;
  final double aspectRatio;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(borderRadius),
      child: AspectRatio(
        aspectRatio: aspectRatio,
        child: ArticleAdaptiveImage(imageUrl: imageUrl),
      ),
    );
  }
}

class _BackdropBlob extends StatelessWidget {
  const _BackdropBlob({
    required this.width,
    required this.height,
    required this.color,
  });

  final double width;
  final double height;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Transform.rotate(
      angle: 0.18,
      child: Container(
        width: width,
        height: height,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(height / 2),
        ),
      ),
    );
  }
}

class _JournalTapeDecoration extends StatelessWidget {
  const _JournalTapeDecoration({
    required this.width,
    required this.height,
    required this.angle,
    required this.color,
  });

  final double width;
  final double height;
  final double angle;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Transform.rotate(
      angle: angle,
      child: Container(
        width: width,
        height: height,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(height / 2),
          border: Border.all(
            color: AppColors.white.withValues(alpha: 0.28),
            width: AppSpacing.hairline,
          ),
          boxShadow: <BoxShadow>[
            BoxShadow(
              color: AppColors.black.withValues(alpha: 0.06),
              blurRadius: 10,
              offset: const Offset(0, 4),
            ),
          ],
        ),
      ),
    );
  }
}

class _JournalStickerDecoration extends StatelessWidget {
  const _JournalStickerDecoration({
    required this.label,
    required this.angle,
    this.compact = false,
  });

  final String label;
  final double angle;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final background = compact
        ? ArticleTemplateColors.journalSticker.withValues(alpha: 0.9)
        : ArticleTemplateColors.journalSticker.withValues(alpha: 0.82);
    return Transform.rotate(
      angle: angle,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: compact ? 10 : 12,
          vertical: compact ? 5 : 6,
        ),
        decoration: BoxDecoration(
          color: background,
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          border: Border.all(
            color: AppColors.white.withValues(alpha: 0.44),
            width: AppSpacing.hairline,
          ),
          boxShadow: <BoxShadow>[
            BoxShadow(
              color: AppColors.black.withValues(alpha: 0.08),
              blurRadius: 14,
              offset: const Offset(0, 6),
            ),
          ],
        ),
        child: Text(
          label,
          style: TextStyle(
            color: ArticleTemplateColors.journalTextLight.withValues(
              alpha: 0.9,
            ),
            fontSize: compact ? AppTypography.xs : AppTypography.xsPlus,
            fontWeight: AppTypography.semiBold,
            letterSpacing: 0.8,
          ),
        ),
      ),
    );
  }
}

class _JournalPaperClipper extends CustomClipper<Path> {
  const _JournalPaperClipper();

  @override
  Path getClip(Size size) {
    return Path()
      ..moveTo(size.width * 0.02, size.height * 0.02)
      ..quadraticBezierTo(
        size.width * 0.16,
        -2,
        size.width * 0.3,
        size.height * 0.03,
      )
      ..quadraticBezierTo(
        size.width * 0.5,
        size.height * 0.01,
        size.width * 0.72,
        size.height * 0.04,
      )
      ..quadraticBezierTo(
        size.width * 0.9,
        size.height * 0.02,
        size.width * 0.98,
        size.height * 0.05,
      )
      ..lineTo(size.width * 0.97, size.height * 0.88)
      ..quadraticBezierTo(
        size.width * 0.85,
        size.height * 0.93,
        size.width * 0.76,
        size.height * 0.9,
      )
      ..quadraticBezierTo(
        size.width * 0.58,
        size.height * 0.95,
        size.width * 0.42,
        size.height * 0.91,
      )
      ..quadraticBezierTo(
        size.width * 0.25,
        size.height * 0.95,
        size.width * 0.08,
        size.height * 0.9,
      )
      ..quadraticBezierTo(
        -4,
        size.height * 0.78,
        size.width * 0.02,
        size.height * 0.62,
      )
      ..close();
  }

  @override
  bool shouldReclip(covariant CustomClipper<Path> oldClipper) => false;
}

class _JournalPaperTexturePainter extends CustomPainter {
  const _JournalPaperTexturePainter(this.palette);

  final ArticleTemplatePalette palette;

  @override
  void paint(Canvas canvas, Size size) {
    final fiberPaint = Paint()
      ..color = palette.paperBorderColor.withValues(alpha: 0.07)
      ..strokeWidth = 0.8
      ..strokeCap = StrokeCap.round;
    for (var index = 0; index < 36; index += 1) {
      final y = 14.0 + (index * (size.height / 36));
      final startX = 8.0 + ((index % 5) * 6);
      final endX = size.width - 12 - ((index % 4) * 4);
      canvas.drawLine(Offset(startX, y), Offset(endX, y + 1.6), fiberPaint);
    }

    final grainPaint = Paint()
      ..color = palette.paperBorderColor.withValues(alpha: 0.05)
      ..style = PaintingStyle.fill;
    for (var index = 0; index < 42; index += 1) {
      final dx = 10 + ((index * 23) % (size.width - 20).clamp(1, 99999));
      final dy = 18 + ((index * 31) % (size.height - 36).clamp(1, 99999));
      canvas.drawCircle(Offset(dx.toDouble(), dy.toDouble()), 0.9, grainPaint);
    }

    final marginPaint = Paint()
      ..color = ArticleTemplateColors.journalAccentLight.withValues(alpha: 0.2)
      ..strokeWidth = 1.2;
    canvas.drawLine(
      Offset(size.width * 0.16, 0),
      Offset(size.width * 0.16, size.height),
      marginPaint,
    );
  }

  @override
  bool shouldRepaint(covariant _JournalPaperTexturePainter oldDelegate) {
    return oldDelegate.palette != palette;
  }
}

class _JournalBackdropPainter extends CustomPainter {
  const _JournalBackdropPainter(this.palette);

  final ArticleTemplatePalette palette;

  @override
  void paint(Canvas canvas, Size size) {
    final linePaint = Paint()
      ..color = palette.paperBorderColor.withValues(alpha: 0.32)
      ..strokeWidth = 1;
    for (var y = 22.0; y < size.height; y += 20) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), linePaint);
    }

    final marginPaint = Paint()
      ..color = ArticleTemplateColors.journalAccentLight.withValues(alpha: 0.18)
      ..strokeWidth = 1.4;
    canvas.drawLine(
      Offset(size.width * 0.18, 0),
      Offset(size.width * 0.18, size.height),
      marginPaint,
    );

    final blotPaint = Paint()
      ..color = ArticleTemplateColors.journalAccentLight.withValues(alpha: 0.08)
      ..style = PaintingStyle.fill;
    canvas.drawOval(
      Rect.fromCenter(
        center: Offset(size.width * 0.72, size.height * 0.2),
        width: size.width * 0.26,
        height: size.height * 0.14,
      ),
      blotPaint,
    );
    canvas.drawOval(
      Rect.fromCenter(
        center: Offset(size.width * 0.32, size.height * 0.74),
        width: size.width * 0.22,
        height: size.height * 0.12,
      ),
      blotPaint,
    );

    final tapePaint = Paint()..color = ArticleTemplateColors.journalTape;
    canvas.save();
    canvas.translate(18, 18);
    canvas.rotate(-0.18);
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        const Rect.fromLTWH(0, 0, 68, 26),
        const Radius.circular(10),
      ),
      tapePaint,
    );
    canvas.restore();

    final stickerPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..color = ArticleTemplateColors.journalSticker;
    canvas.drawArc(
      Rect.fromCircle(
        center: Offset(size.width - 34, size.height - 32),
        radius: 18,
      ),
      -0.6,
      2.8,
      false,
      stickerPaint,
    );

    final doodlePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.8
      ..strokeCap = StrokeCap.round
      ..color = palette.textColor.withValues(alpha: 0.16);
    final path = Path()
      ..moveTo(size.width * 0.7, size.height * 0.8)
      ..quadraticBezierTo(
        size.width * 0.77,
        size.height * 0.76,
        size.width * 0.84,
        size.height * 0.82,
      )
      ..quadraticBezierTo(
        size.width * 0.9,
        size.height * 0.86,
        size.width * 0.93,
        size.height * 0.8,
      );
    canvas.drawPath(path, doodlePaint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _RitualBackdropPainter extends CustomPainter {
  const _RitualBackdropPainter(this.palette);

  final ArticleTemplatePalette palette;

  @override
  void paint(Canvas canvas, Size size) {
    final borderPaint = Paint()
      ..color = palette.paperBorderColor.withValues(alpha: 0.48)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2;
    final rect = RRect.fromRectAndRadius(
      Rect.fromLTWH(14, 14, size.width - 28, size.height - 28),
      const Radius.circular(24),
    );
    canvas.drawRRect(rect, borderPaint);

    final accentPaint = Paint()
      ..color = palette.accentColor.withValues(alpha: 0.22)
      ..strokeWidth = 2;
    canvas.drawLine(
      const Offset(28, 34),
      Offset(size.width - 28, 34),
      accentPaint,
    );
    canvas.drawLine(
      Offset(28, size.height - 34),
      Offset(size.width - 28, size.height - 34),
      accentPaint,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _TechBackdropPainter extends CustomPainter {
  const _TechBackdropPainter(this.palette);

  final ArticleTemplatePalette palette;

  @override
  void paint(Canvas canvas, Size size) {
    final gridPaint = Paint()
      ..color = palette.accentColor.withValues(alpha: 0.12)
      ..strokeWidth = 1;
    for (var x = 0.0; x < size.width; x += 20) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), gridPaint);
    }
    for (var y = 0.0; y < size.height; y += 20) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), gridPaint);
    }

    final glowPaint = Paint()
      ..color = palette.accentColor.withValues(alpha: 0.26)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 24);
    canvas.drawCircle(
      Offset(size.width * 0.82, size.height * 0.14),
      24,
      glowPaint,
    );
    canvas.drawCircle(
      Offset(size.width * 0.18, size.height * 0.86),
      28,
      glowPaint,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
