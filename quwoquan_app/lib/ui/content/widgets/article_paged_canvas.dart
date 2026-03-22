import 'dart:ui';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
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
    this.contentPadding,
    this.showIndicator = true,
  });

  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final int pageIndex;
  final int totalPages;
  final Widget child;
  final double aspectRatio;
  final EdgeInsets? contentPadding;
  final bool showIndicator;

  @override
  Widget build(BuildContext context) {
    final palette = resolveArticleTemplatePalette(context, template);

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
      child: Padding(
        padding:
            contentPadding ??
            EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.containerLg,
              AppSpacing.containerMd,
              AppSpacing.containerMd,
            ),
        child: child,
      ),
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
          child: paper,
        ),
      );
    } else {
      paper = ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyEight),
        child: paper,
      );
    }

    return AspectRatio(
      aspectRatio: aspectRatio,
      child: Stack(
        children: <Widget>[
          Positioned.fill(child: _ArticleBackdrop(template: template, palette: palette)),
          Positioned.fill(
            child: Padding(
              padding: EdgeInsets.all(AppSpacing.containerSm),
              child: paper,
            ),
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
  });

  final ArticlePageData page;
  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;

  @override
  Widget build(BuildContext context) {
    final typography = resolveArticleTypography(context, template, fontPreset);

    return SingleChildScrollView(
      physics: const BouncingScrollPhysics(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          if (page.title.trim().isNotEmpty) ...<Widget>[
            Text(page.title.trim(), style: typography.titleStyle),
            SizedBox(height: AppSpacing.intraGroupSm),
          ],
          if (page.imageUrl.trim().isNotEmpty && !page.usesWrappedLayout) ...<Widget>[
            _ArticlePageImage(
              imageUrl: page.imageUrl.trim(),
              borderRadius: AppSpacing.radiusTwenty,
              aspectRatio: template == ArticleTemplatePreset.journal ? 1 : 4 / 3,
            ),
            if (page.caption.trim().isNotEmpty) ...<Widget>[
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(page.caption.trim(), style: typography.captionStyle),
            ],
            SizedBox(height: AppSpacing.intraGroupSm),
          ],
          if (page.imageUrl.trim().isNotEmpty && page.usesWrappedLayout)
            _ArticleWrappedTextImage(
              body: page.body.trim(),
              imageUrl: page.imageUrl.trim(),
              imageLayout: page.imageLayout,
              typography: typography,
            )
          else if (page.body.trim().isNotEmpty)
            Text(page.body.trim(), style: typography.bodyStyle),
        ],
      ),
    );
  }
}

class ArticleTemplateThumbnail extends StatelessWidget {
  const ArticleTemplateThumbnail({
    super.key,
    required this.template,
    required this.fontPreset,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final borderColor = selected
        ? AppColors.primaryColor
        : CupertinoColors.separator.resolveFrom(context);

    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          AnimatedContainer(
            duration: const Duration(milliseconds: 220),
            curve: Curves.easeOutCubic,
            width: AppSpacing.avatarUserXl,
            height: AppSpacing.oneHundred + AppSpacing.xs,
            padding: const EdgeInsets.all(AppSpacing.two),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
              border: Border.all(color: borderColor, width: selected ? 2 : 1),
            ),
            child: ArticlePageShell(
              template: template,
              fontPreset: fontPreset,
              pageIndex: 0,
              totalPages: 1,
              aspectRatio: 72 / 104,
              showIndicator: false,
              contentPadding: const EdgeInsets.fromLTRB(8, 10, 8, 8),
              child: _TemplatePreviewFiller(
                template: template,
                fontPreset: fontPreset,
                label: label,
              ),
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            label,
            style: TextStyle(
              color: CupertinoColors.label.resolveFrom(context),
              fontSize: AppTypography.sm,
              fontWeight: selected ? AppTypography.semiBold : AppTypography.medium,
            ),
          ),
        ],
      ),
    );
  }
}

@immutable
class ArticleTemplatePalette {
  const ArticleTemplatePalette({
    required this.stageBackground,
    required this.paperColor,
    required this.paperBorderColor,
    required this.textColor,
    required this.secondaryTextColor,
    required this.accentColor,
    required this.badgeBackground,
    required this.badgeTextColor,
    required this.shadowColor,
    required this.overlayColor,
  });

  final Color stageBackground;
  final Color paperColor;
  final Color paperBorderColor;
  final Color textColor;
  final Color secondaryTextColor;
  final Color accentColor;
  final Color badgeBackground;
  final Color badgeTextColor;
  final Color shadowColor;
  final Color overlayColor;
}

ArticleTemplatePalette resolveArticleTemplatePalette(
  BuildContext context,
  ArticleTemplatePreset template,
) {
  final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;

  switch (template) {
    case ArticleTemplatePreset.ritual:
      return ArticleTemplatePalette(
        stageBackground: isDark
            ? ArticleTemplateColors.ritualStageDark
            : ArticleTemplateColors.ritualStageLight,
        paperColor: isDark
            ? ArticleTemplateColors.ritualPaperDark
            : ArticleTemplateColors.ritualPaperLight,
        paperBorderColor: isDark
            ? ArticleTemplateColors.ritualPaperBorderDark
            : ArticleTemplateColors.ritualPaperBorderLight,
        textColor: isDark
            ? ArticleTemplateColors.ritualTextDark
            : ArticleTemplateColors.ritualTextLight,
        secondaryTextColor: isDark
            ? ArticleTemplateColors.ritualSecondaryTextDark
            : ArticleTemplateColors.ritualSecondaryTextLight,
        accentColor: isDark
            ? ArticleTemplateColors.ritualAccentDark
            : ArticleTemplateColors.ritualAccentLight,
        badgeBackground: isDark
            ? ArticleTemplateColors.ritualBadgeBackgroundDark
            : ArticleTemplateColors.ritualBadgeBackgroundLight,
        badgeTextColor: isDark
            ? ArticleTemplateColors.ritualBadgeTextDark
            : ArticleTemplateColors.ritualBadgeTextLight,
        shadowColor: Colors.black.withValues(alpha: isDark ? 0.36 : 0.12),
        overlayColor: isDark
            ? ArticleTemplateColors.ritualOverlayDark
            : ArticleTemplateColors.ritualOverlayLight,
      );
    case ArticleTemplatePreset.diffuse:
      return ArticleTemplatePalette(
        stageBackground: isDark
            ? ArticleTemplateColors.diffuseStageDark
            : ArticleTemplateColors.diffuseStageLight,
        paperColor: isDark
            ? ArticleTemplateColors.diffusePaperDark
            : ArticleTemplateColors.diffusePaperLight,
        paperBorderColor: isDark
            ? ArticleTemplateColors.diffusePaperBorderDark
            : ArticleTemplateColors.diffusePaperBorderLight,
        textColor: isDark
            ? ArticleTemplateColors.diffuseTextDark
            : ArticleTemplateColors.diffuseTextLight,
        secondaryTextColor: isDark
            ? ArticleTemplateColors.diffuseSecondaryTextDark
            : ArticleTemplateColors.diffuseSecondaryTextLight,
        accentColor: isDark
            ? ArticleTemplateColors.diffuseAccentDark
            : ArticleTemplateColors.diffuseAccentLight,
        badgeBackground: isDark
            ? ArticleTemplateColors.diffuseBadgeBackgroundDark
            : ArticleTemplateColors.diffuseBadgeBackgroundLight,
        badgeTextColor: isDark
            ? ArticleTemplateColors.diffuseBadgeTextDark
            : ArticleTemplateColors.diffuseBadgeTextLight,
        shadowColor: Colors.black.withValues(alpha: isDark ? 0.34 : 0.11),
        overlayColor: isDark
            ? ArticleTemplateColors.diffuseOverlayDark
            : ArticleTemplateColors.diffuseOverlayLight,
      );
    case ArticleTemplatePreset.journal:
      return ArticleTemplatePalette(
        stageBackground: isDark
            ? ArticleTemplateColors.journalStageDark
            : ArticleTemplateColors.journalStageLight,
        paperColor: isDark
            ? ArticleTemplateColors.journalPaperDark
            : ArticleTemplateColors.journalPaperLight,
        paperBorderColor: isDark
            ? ArticleTemplateColors.journalPaperBorderDark
            : ArticleTemplateColors.journalPaperBorderLight,
        textColor: isDark
            ? ArticleTemplateColors.journalTextDark
            : ArticleTemplateColors.journalTextLight,
        secondaryTextColor: isDark
            ? ArticleTemplateColors.journalSecondaryTextDark
            : ArticleTemplateColors.journalSecondaryTextLight,
        accentColor: isDark
            ? ArticleTemplateColors.journalAccentDark
            : ArticleTemplateColors.journalAccentLight,
        badgeBackground: isDark
            ? ArticleTemplateColors.journalBadgeBackgroundDark
            : ArticleTemplateColors.journalBadgeBackgroundLight,
        badgeTextColor: isDark
            ? ArticleTemplateColors.journalBadgeTextDark
            : ArticleTemplateColors.journalBadgeTextLight,
        shadowColor: Colors.black.withValues(alpha: isDark ? 0.28 : 0.14),
        overlayColor: isDark
            ? ArticleTemplateColors.journalOverlayDark
            : ArticleTemplateColors.journalOverlayLight,
      );
    case ArticleTemplatePreset.tech:
      return ArticleTemplatePalette(
        stageBackground: ArticleTemplateColors.techStage,
        paperColor: ArticleTemplateColors.techPaper,
        paperBorderColor: ArticleTemplateColors.techPaperBorder,
        textColor: ArticleTemplateColors.techText,
        secondaryTextColor: ArticleTemplateColors.techSecondaryText,
        accentColor: ArticleTemplateColors.techAccent,
        badgeBackground: ArticleTemplateColors.techBadgeBackground,
        badgeTextColor: ArticleTemplateColors.techBadgeText,
        shadowColor: Colors.black.withValues(alpha: 0.42),
        overlayColor: ArticleTemplateColors.techOverlay,
      );
    case ArticleTemplatePreset.gentle:
      return ArticleTemplatePalette(
        stageBackground: isDark
            ? ArticleTemplateColors.gentleStageDark
            : ArticleTemplateColors.gentleStageLight,
        paperColor: isDark
            ? ArticleTemplateColors.gentlePaperDark
            : ArticleTemplateColors.gentlePaperLight,
        paperBorderColor: isDark
            ? ArticleTemplateColors.gentlePaperBorderDark
            : ArticleTemplateColors.gentlePaperBorderLight,
        textColor: isDark
            ? ArticleTemplateColors.gentleTextDark
            : ArticleTemplateColors.gentleTextLight,
        secondaryTextColor: isDark
            ? ArticleTemplateColors.gentleSecondaryTextDark
            : ArticleTemplateColors.gentleSecondaryTextLight,
        accentColor: isDark
            ? ArticleTemplateColors.gentleAccentDark
            : ArticleTemplateColors.gentleAccentLight,
        badgeBackground: isDark
            ? ArticleTemplateColors.gentleBadgeBackgroundDark
            : ArticleTemplateColors.gentleBadgeBackgroundLight,
        badgeTextColor: isDark
            ? ArticleTemplateColors.gentleBadgeTextDark
            : ArticleTemplateColors.gentleBadgeTextLight,
        shadowColor: Colors.black.withValues(alpha: isDark ? 0.28 : 0.09),
        overlayColor: isDark
            ? ArticleTemplateColors.gentleOverlayDark
            : ArticleTemplateColors.gentleOverlayLight,
      );
  }
}

@immutable
class ArticleTypographySpec {
  const ArticleTypographySpec({
    required this.titleStyle,
    required this.bodyStyle,
    required this.captionStyle,
    required this.placeholderStyle,
    required this.badgeStyle,
  });

  final TextStyle titleStyle;
  final TextStyle bodyStyle;
  final TextStyle captionStyle;
  final TextStyle placeholderStyle;
  final TextStyle badgeStyle;
}

ArticleTypographySpec resolveArticleTypography(
  BuildContext context,
  ArticleTemplatePreset template,
  ArticleFontPreset fontPreset,
) {
  final palette = resolveArticleTemplatePalette(context, template);

  TextStyle base({
    required double size,
    FontWeight weight = FontWeight.normal,
    double height = 1.7,
    Color? color,
  }) {
    final fallback = switch (fontPreset) {
      ArticleFontPreset.classic => const <String>[
        'Times New Roman',
        'STSong',
        'Songti SC',
      ],
      ArticleFontPreset.handwritten => const <String>['Kaiti SC', 'STKaiti'],
      ArticleFontPreset.rounded => const <String>['PingFang SC', 'SF Pro Rounded'],
      ArticleFontPreset.mono => const <String>['Menlo', 'Monaco'],
      ArticleFontPreset.clean => const <String>['PingFang SC'],
    };

    return TextStyle(
      color: color ?? palette.textColor,
      fontSize: size,
      fontWeight: weight,
      height: height,
      letterSpacing: fontPreset == ArticleFontPreset.mono ? 0.15 : 0.05,
      fontFamily: switch (fontPreset) {
        ArticleFontPreset.classic => 'Times New Roman',
        ArticleFontPreset.handwritten => 'Kaiti SC',
        ArticleFontPreset.rounded => 'SF Pro Rounded',
        ArticleFontPreset.mono => 'Menlo',
        ArticleFontPreset.clean => null,
      },
      fontFamilyFallback: fallback,
    );
  }

  return ArticleTypographySpec(
    titleStyle: base(
      size: AppTypography.xl,
      weight: AppTypography.semiBold,
      height: AppSpacing.textLineHeightHeadline,
    ),
    bodyStyle: base(
      size: AppTypography.base,
      height: AppSpacing.textLineHeightArticleBody,
    ),
    captionStyle: base(
      size: AppTypography.xs,
      weight: AppTypography.medium,
      height: AppSpacing.textLineHeightLabel,
      color: palette.secondaryTextColor,
    ),
    placeholderStyle: base(
      size: AppTypography.base,
      height: AppSpacing.textLineHeightArticleBody,
      color: palette.secondaryTextColor.withValues(alpha: 0.72),
    ),
    badgeStyle: base(
      size: AppTypography.xs,
      weight: AppTypography.semiBold,
      height: AppSpacing.textLineHeightCompact,
      color: palette.badgeTextColor,
    ),
  );
}

class _ArticleBackdrop extends StatelessWidget {
  const _ArticleBackdrop({required this.template, required this.palette});

  final ArticleTemplatePreset template;
  final ArticleTemplatePalette palette;

  @override
  Widget build(BuildContext context) {
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
                width: AppSpacing.oneHundred + AppSpacing.forty + AppSpacing.ten,
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
          if (template == ArticleTemplatePreset.journal)
            Positioned.fill(
              child: CustomPaint(painter: _JournalBackdropPainter(palette)),
            ),
          if (template == ArticleTemplatePreset.tech)
            Positioned.fill(
              child: CustomPaint(painter: _TechBackdropPainter(palette)),
            ),
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: palette.overlayColor,
                borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyEight + 6),
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
            borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
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

class _ArticleWrappedTextImage extends StatelessWidget {
  const _ArticleWrappedTextImage({
    required this.body,
    required this.imageUrl,
    required this.imageLayout,
    required this.typography,
  });

  final String body;
  final String imageUrl;
  final String imageLayout;
  final ArticleTypographySpec typography;

  @override
  Widget build(BuildContext context) {
    final image = SizedBox(
      width: AppSpacing.oneHundred + AppSpacing.sm,
      child: _ArticlePageImage(
        imageUrl: imageUrl,
        borderRadius: AppSpacing.radiusTwenty,
        aspectRatio: 1,
      ),
    );
    final text = Expanded(
      child: Text(body, style: typography.bodyStyle),
    );

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: imageLayout == 'wrapRight'
          ? <Widget>[text, SizedBox(width: AppSpacing.containerSm), image]
          : <Widget>[image, SizedBox(width: AppSpacing.containerSm), text],
    );
  }
}

class _TemplatePreviewFiller extends StatelessWidget {
  const _TemplatePreviewFiller({
    required this.template,
    required this.fontPreset,
    required this.label,
  });

  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final String label;

  @override
  Widget build(BuildContext context) {
    final typography = resolveArticleTypography(context, template, fontPreset);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Container(
          width: AppSpacing.buttonHeightXs,
          height: AppSpacing.six,
          decoration: BoxDecoration(
            color: typography.captionStyle.color?.withValues(alpha: 0.35),
            borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupSm),
        Text(label, maxLines: 1, overflow: TextOverflow.ellipsis, style: typography.captionStyle),
        SizedBox(height: AppSpacing.intraGroupXs),
        Expanded(
          child: Text(
            '春风起，纸面轻轻落下',
            maxLines: 4,
            overflow: TextOverflow.ellipsis,
            style: typography.bodyStyle.copyWith(fontSize: AppTypography.xsPlus),
          ),
        ),
      ],
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

class _JournalPaperClipper extends CustomClipper<Path> {
  const _JournalPaperClipper();

  @override
  Path getClip(Size size) {
    return Path()
      ..moveTo(size.width * 0.02, size.height * 0.02)
      ..quadraticBezierTo(size.width * 0.16, -2, size.width * 0.3, size.height * 0.03)
      ..quadraticBezierTo(size.width * 0.5, size.height * 0.01, size.width * 0.72, size.height * 0.04)
      ..quadraticBezierTo(size.width * 0.9, size.height * 0.02, size.width * 0.98, size.height * 0.05)
      ..lineTo(size.width * 0.97, size.height * 0.88)
      ..quadraticBezierTo(size.width * 0.85, size.height * 0.93, size.width * 0.76, size.height * 0.9)
      ..quadraticBezierTo(size.width * 0.58, size.height * 0.95, size.width * 0.42, size.height * 0.91)
      ..quadraticBezierTo(size.width * 0.25, size.height * 0.95, size.width * 0.08, size.height * 0.9)
      ..quadraticBezierTo(-4, size.height * 0.78, size.width * 0.02, size.height * 0.62)
      ..close();
  }

  @override
  bool shouldReclip(covariant CustomClipper<Path> oldClipper) => false;
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
    canvas.drawLine(const Offset(28, 34), Offset(size.width - 28, 34), accentPaint);
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
    canvas.drawCircle(Offset(size.width * 0.82, size.height * 0.14), 24, glowPaint);
    canvas.drawCircle(Offset(size.width * 0.18, size.height * 0.86), 28, glowPaint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
