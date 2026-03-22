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
            width: 72,
            height: 104,
            padding: const EdgeInsets.all(2),
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
        stageBackground: isDark ? const Color(0xFF171411) : const Color(0xFFF6F0E7),
        paperColor: isDark ? const Color(0xFF2A241D) : const Color(0xFFFDF8EF),
        paperBorderColor: isDark ? const Color(0xFF564739) : const Color(0xFFE0D1BC),
        textColor: isDark ? const Color(0xFFF8ECDD) : const Color(0xFF3A2C22),
        secondaryTextColor: isDark ? const Color(0xFFD1BFA9) : const Color(0xFF8A6E56),
        accentColor: isDark ? const Color(0xFFD3A96D) : const Color(0xFFB6874C),
        badgeBackground: isDark ? const Color(0xE646382C) : const Color(0xCCFFFFFF),
        badgeTextColor: isDark ? const Color(0xFFF8ECDD) : const Color(0xFF6B4E34),
        shadowColor: Colors.black.withValues(alpha: isDark ? 0.36 : 0.12),
        overlayColor: isDark ? const Color(0x14000000) : const Color(0x10C79C6E),
      );
    case ArticleTemplatePreset.diffuse:
      return ArticleTemplatePalette(
        stageBackground: isDark ? const Color(0xFF16192A) : const Color(0xFFF6F4FF),
        paperColor: isDark ? const Color(0xFF252A43) : const Color(0xFFFDFBFF),
        paperBorderColor: isDark ? const Color(0xFF48507A) : const Color(0xFFE6DAFF),
        textColor: isDark ? const Color(0xFFF4F1FF) : const Color(0xFF31274D),
        secondaryTextColor: isDark ? const Color(0xFFC7BFEE) : const Color(0xFF7D6EA1),
        accentColor: isDark ? const Color(0xFFA9B5FF) : const Color(0xFF8B8AF5),
        badgeBackground: isDark ? const Color(0xE634395A) : const Color(0xCCFFFFFF),
        badgeTextColor: isDark ? const Color(0xFFF5F3FF) : const Color(0xFF6660A8),
        shadowColor: Colors.black.withValues(alpha: isDark ? 0.34 : 0.11),
        overlayColor: isDark ? const Color(0x145A66A3) : const Color(0x14C3C8FF),
      );
    case ArticleTemplatePreset.journal:
      return ArticleTemplatePalette(
        stageBackground: isDark ? const Color(0xFF202322) : const Color(0xFFF7F3EA),
        paperColor: isDark ? const Color(0xFFFAF2E2) : const Color(0xFFFFFBF5),
        paperBorderColor: isDark ? const Color(0xFFD9C6A8) : const Color(0xFFE8DCC8),
        textColor: isDark ? const Color(0xFF2B2016) : const Color(0xFF3A2C22),
        secondaryTextColor: isDark ? const Color(0xFF7D6753) : const Color(0xFF8E7865),
        accentColor: isDark ? const Color(0xFFFF5D7A) : const Color(0xFFFF4A6B),
        badgeBackground: isDark ? const Color(0xE6FBF0DE) : const Color(0xCCFFFFFF),
        badgeTextColor: isDark ? const Color(0xFF6B5644) : const Color(0xFF7D6A59),
        shadowColor: Colors.black.withValues(alpha: isDark ? 0.28 : 0.14),
        overlayColor: isDark ? const Color(0x1024C6A2) : const Color(0x1438DCC7),
      );
    case ArticleTemplatePreset.tech:
      return ArticleTemplatePalette(
        stageBackground: const Color(0xFF0B1019),
        paperColor: const Color(0xFF141C2B),
        paperBorderColor: const Color(0xFF314462),
        textColor: const Color(0xFFE8F2FF),
        secondaryTextColor: const Color(0xFF8FB0D9),
        accentColor: const Color(0xFF4EE0FF),
        badgeBackground: const Color(0xCC18273E),
        badgeTextColor: const Color(0xFFE8F2FF),
        shadowColor: Colors.black.withValues(alpha: 0.42),
        overlayColor: const Color(0x1237A4C8),
      );
    case ArticleTemplatePreset.gentle:
      return ArticleTemplatePalette(
        stageBackground: isDark ? const Color(0xFF1D1E26) : const Color(0xFFF7F8F5),
        paperColor: isDark ? const Color(0xFF2A2D36) : const Color(0xFFFFFEFB),
        paperBorderColor: isDark ? const Color(0xFF454956) : const Color(0xFFE8E7DF),
        textColor: isDark ? const Color(0xFFF4F4F0) : const Color(0xFF2F3136),
        secondaryTextColor: isDark ? const Color(0xFFC7C9CE) : const Color(0xFF7A7D86),
        accentColor: isDark ? const Color(0xFFFFB0BE) : const Color(0xFFFF7A95),
        badgeBackground: isDark ? const Color(0xCC343840) : const Color(0xCCFFFFFF),
        badgeTextColor: isDark ? const Color(0xFFF4F4F0) : const Color(0xFF6F7280),
        shadowColor: Colors.black.withValues(alpha: isDark ? 0.28 : 0.09),
        overlayColor: isDark ? const Color(0x10B7F0D7) : const Color(0x10BFE9D2),
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
      height: 1.4,
    ),
    bodyStyle: base(size: AppTypography.base, height: 1.82),
    captionStyle: base(
      size: AppTypography.xs,
      weight: AppTypography.medium,
      height: 1.5,
      color: palette.secondaryTextColor,
    ),
    placeholderStyle: base(
      size: AppTypography.base,
      height: 1.82,
      color: palette.secondaryTextColor.withValues(alpha: 0.72),
    ),
    badgeStyle: base(
      size: AppTypography.xs,
      weight: AppTypography.semiBold,
      height: 1.2,
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
                width: 120,
                height: 80,
                color: palette.accentColor.withValues(alpha: 0.16),
              ),
            ),
            Positioned(
              bottom: 10,
              right: -14,
              child: _BackdropBlob(
                width: 132,
                height: 88,
                color: const Color(0xFFB6E8D6).withValues(alpha: 0.26),
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
                width: 150,
                height: 120,
                color: const Color(0xFFBBC7FF).withValues(alpha: 0.3),
              ),
            ),
            Positioned(
              bottom: -12,
              left: -10,
              child: _BackdropBlob(
                width: 140,
                height: 96,
                color: const Color(0xFFFFC7EB).withValues(alpha: 0.26),
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
      width: 108,
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
          width: 28,
          height: 6,
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

    final tapePaint = Paint()..color = const Color(0x99A5B4FF);
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
      ..color = const Color(0x88A7B8FF);
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
