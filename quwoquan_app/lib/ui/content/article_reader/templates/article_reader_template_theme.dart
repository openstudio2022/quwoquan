import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';

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
        shadowColor: AppColors.black.withValues(alpha: isDark ? 0.36 : 0.12),
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
        shadowColor: AppColors.black.withValues(alpha: isDark ? 0.34 : 0.11),
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
        shadowColor: AppColors.black.withValues(alpha: isDark ? 0.28 : 0.14),
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
        shadowColor: AppColors.black.withValues(alpha: 0.42),
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
        shadowColor: AppColors.black.withValues(alpha: isDark ? 0.28 : 0.09),
        overlayColor: isDark
            ? ArticleTemplateColors.gentleOverlayDark
            : ArticleTemplateColors.gentleOverlayLight,
      );
  }
}

/// 纸张质感 → 色板映射（替代 resolveArticleTemplatePalette）。
ArticleTemplatePalette resolveArticlePaperPalette(
  BuildContext context,
  ArticlePaperTexture texture,
) {
  final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;

  Color paper(Color light, Color dark) => isDark ? dark : light;
  Color text(Color light, Color dark) => isDark ? dark : light;

  switch (texture) {
    case ArticlePaperTexture.white:
      return ArticleTemplatePalette(
        stageBackground: paper(
          ArticlePaperPaletteColors.whiteStageLight,
          ArticlePaperPaletteColors.whiteStageDark,
        ),
        paperColor: paper(
          ArticlePaperPaletteColors.whitePaperLight,
          ArticlePaperPaletteColors.whitePaperDark,
        ),
        paperBorderColor: paper(
          ArticlePaperPaletteColors.whitePaperBorderLight,
          ArticlePaperPaletteColors.whitePaperBorderDark,
        ),
        textColor: text(
          ArticlePaperPaletteColors.whiteTextLight,
          ArticlePaperPaletteColors.whiteTextDark,
        ),
        secondaryTextColor: text(
          ArticlePaperPaletteColors.whiteSecondaryTextLight,
          ArticlePaperPaletteColors.whiteSecondaryTextDark,
        ),
        accentColor: text(
          ArticlePaperPaletteColors.whiteAccentLight,
          ArticlePaperPaletteColors.whiteAccentDark,
        ),
        badgeBackground: paper(
          ArticlePaperPaletteColors.whiteBadgeBackgroundLight,
          ArticlePaperPaletteColors.whiteBadgeBackgroundDark,
        ),
        badgeTextColor: text(
          ArticlePaperPaletteColors.whiteBadgeTextLight,
          ArticlePaperPaletteColors.whiteBadgeTextDark,
        ),
        shadowColor: AppColors.black.withValues(alpha: isDark ? 0.28 : 0.08),
        overlayColor: paper(
          ArticlePaperPaletteColors.whiteOverlayLight,
          ArticlePaperPaletteColors.whiteOverlayDark,
        ),
      );
    case ArticlePaperTexture.cream:
      return ArticleTemplatePalette(
        stageBackground: paper(
          ArticlePaperPaletteColors.creamStageLight,
          ArticlePaperPaletteColors.creamStageDark,
        ),
        paperColor: paper(
          ArticlePaperPaletteColors.creamPaperLight,
          ArticlePaperPaletteColors.creamPaperDark,
        ),
        paperBorderColor: paper(
          ArticlePaperPaletteColors.creamPaperBorderLight,
          ArticlePaperPaletteColors.creamPaperBorderDark,
        ),
        textColor: text(
          ArticlePaperPaletteColors.creamTextLight,
          ArticlePaperPaletteColors.creamTextDark,
        ),
        secondaryTextColor: text(
          ArticlePaperPaletteColors.creamSecondaryTextLight,
          ArticlePaperPaletteColors.creamSecondaryTextDark,
        ),
        accentColor: text(
          ArticlePaperPaletteColors.creamAccentLight,
          ArticlePaperPaletteColors.creamAccentDark,
        ),
        badgeBackground: paper(
          ArticlePaperPaletteColors.creamBadgeBackgroundLight,
          ArticlePaperPaletteColors.creamBadgeBackgroundDark,
        ),
        badgeTextColor: text(
          ArticlePaperPaletteColors.creamBadgeTextLight,
          ArticlePaperPaletteColors.creamBadgeTextDark,
        ),
        shadowColor: AppColors.black.withValues(alpha: isDark ? 0.28 : 0.09),
        overlayColor: paper(
          ArticlePaperPaletteColors.creamOverlayLight,
          ArticlePaperPaletteColors.creamOverlayDark,
        ),
      );
    case ArticlePaperTexture.sepia:
      return ArticleTemplatePalette(
        stageBackground: paper(
          ArticlePaperPaletteColors.sepiaStageLight,
          ArticlePaperPaletteColors.sepiaStageDark,
        ),
        paperColor: paper(
          ArticlePaperPaletteColors.sepiaPaperLight,
          ArticlePaperPaletteColors.sepiaPaperDark,
        ),
        paperBorderColor: paper(
          ArticlePaperPaletteColors.sepiaPaperBorderLight,
          ArticlePaperPaletteColors.sepiaPaperBorderDark,
        ),
        textColor: text(
          ArticlePaperPaletteColors.sepiaTextLight,
          ArticlePaperPaletteColors.sepiaTextDark,
        ),
        secondaryTextColor: text(
          ArticlePaperPaletteColors.sepiaSecondaryTextLight,
          ArticlePaperPaletteColors.sepiaSecondaryTextDark,
        ),
        accentColor: text(
          ArticlePaperPaletteColors.sepiaAccentLight,
          ArticlePaperPaletteColors.sepiaAccentDark,
        ),
        badgeBackground: paper(
          ArticlePaperPaletteColors.sepiaBadgeBackgroundLight,
          ArticlePaperPaletteColors.sepiaBadgeBackgroundDark,
        ),
        badgeTextColor: text(
          ArticlePaperPaletteColors.sepiaBadgeTextLight,
          ArticlePaperPaletteColors.sepiaBadgeTextDark,
        ),
        shadowColor: AppColors.black.withValues(alpha: isDark ? 0.28 : 0.10),
        overlayColor: paper(
          ArticlePaperPaletteColors.sepiaOverlayLight,
          ArticlePaperPaletteColors.sepiaOverlayDark,
        ),
      );
    case ArticlePaperTexture.parchment:
      return ArticleTemplatePalette(
        stageBackground: paper(
          ArticlePaperPaletteColors.parchmentStageLight,
          ArticlePaperPaletteColors.parchmentStageDark,
        ),
        paperColor: paper(
          ArticlePaperPaletteColors.parchmentPaperLight,
          ArticlePaperPaletteColors.parchmentPaperDark,
        ),
        paperBorderColor: paper(
          ArticlePaperPaletteColors.parchmentPaperBorderLight,
          ArticlePaperPaletteColors.parchmentPaperBorderDark,
        ),
        textColor: text(
          ArticlePaperPaletteColors.parchmentTextLight,
          ArticlePaperPaletteColors.parchmentTextDark,
        ),
        secondaryTextColor: text(
          ArticlePaperPaletteColors.parchmentSecondaryTextLight,
          ArticlePaperPaletteColors.parchmentSecondaryTextDark,
        ),
        accentColor: text(
          ArticlePaperPaletteColors.parchmentAccentLight,
          ArticlePaperPaletteColors.parchmentAccentDark,
        ),
        badgeBackground: paper(
          ArticlePaperPaletteColors.parchmentBadgeBackgroundLight,
          ArticlePaperPaletteColors.parchmentBadgeBackgroundDark,
        ),
        badgeTextColor: text(
          ArticlePaperPaletteColors.parchmentBadgeTextLight,
          ArticlePaperPaletteColors.parchmentBadgeTextDark,
        ),
        shadowColor: AppColors.black.withValues(alpha: isDark ? 0.28 : 0.12),
        overlayColor: paper(
          ArticlePaperPaletteColors.parchmentOverlayLight,
          ArticlePaperPaletteColors.parchmentOverlayDark,
        ),
      );
    case ArticlePaperTexture.eyeCare:
      return ArticleTemplatePalette(
        stageBackground: paper(
          ArticlePaperPaletteColors.eyeCareStageLight,
          ArticlePaperPaletteColors.eyeCareStageDark,
        ),
        paperColor: paper(
          ArticlePaperPaletteColors.eyeCarePaperLight,
          ArticlePaperPaletteColors.eyeCarePaperDark,
        ),
        paperBorderColor: paper(
          ArticlePaperPaletteColors.eyeCarePaperBorderLight,
          ArticlePaperPaletteColors.eyeCarePaperBorderDark,
        ),
        textColor: text(
          ArticlePaperPaletteColors.eyeCareTextLight,
          ArticlePaperPaletteColors.eyeCareTextDark,
        ),
        secondaryTextColor: text(
          ArticlePaperPaletteColors.eyeCareSecondaryTextLight,
          ArticlePaperPaletteColors.eyeCareSecondaryTextDark,
        ),
        accentColor: text(
          ArticlePaperPaletteColors.eyeCareAccentLight,
          ArticlePaperPaletteColors.eyeCareAccentDark,
        ),
        badgeBackground: paper(
          ArticlePaperPaletteColors.eyeCareBadgeBackgroundLight,
          ArticlePaperPaletteColors.eyeCareBadgeBackgroundDark,
        ),
        badgeTextColor: text(
          ArticlePaperPaletteColors.eyeCareBadgeTextLight,
          ArticlePaperPaletteColors.eyeCareBadgeTextDark,
        ),
        shadowColor: AppColors.black.withValues(alpha: isDark ? 0.28 : 0.08),
        overlayColor: paper(
          ArticlePaperPaletteColors.eyeCareOverlayLight,
          ArticlePaperPaletteColors.eyeCareOverlayDark,
        ),
      );
    case ArticlePaperTexture.quiet:
      return ArticleTemplatePalette(
        stageBackground: paper(
          ArticlePaperPaletteColors.quietStageLight,
          ArticlePaperPaletteColors.quietStageDark,
        ),
        paperColor: paper(
          ArticlePaperPaletteColors.quietPaperLight,
          ArticlePaperPaletteColors.quietPaperDark,
        ),
        paperBorderColor: paper(
          ArticlePaperPaletteColors.quietPaperBorderLight,
          ArticlePaperPaletteColors.quietPaperBorderDark,
        ),
        textColor: text(
          ArticlePaperPaletteColors.quietTextLight,
          ArticlePaperPaletteColors.quietTextDark,
        ),
        secondaryTextColor: text(
          ArticlePaperPaletteColors.quietSecondaryTextLight,
          ArticlePaperPaletteColors.quietSecondaryTextDark,
        ),
        accentColor: text(
          ArticlePaperPaletteColors.quietAccentLight,
          ArticlePaperPaletteColors.quietAccentDark,
        ),
        badgeBackground: paper(
          ArticlePaperPaletteColors.quietBadgeBackgroundLight,
          ArticlePaperPaletteColors.quietBadgeBackgroundDark,
        ),
        badgeTextColor: text(
          ArticlePaperPaletteColors.quietBadgeTextLight,
          ArticlePaperPaletteColors.quietBadgeTextDark,
        ),
        shadowColor: AppColors.black.withValues(alpha: isDark ? 0.28 : 0.08),
        overlayColor: paper(
          ArticlePaperPaletteColors.quietOverlayLight,
          ArticlePaperPaletteColors.quietOverlayDark,
        ),
      );
    case ArticlePaperTexture.night:
      return ArticleTemplatePalette(
        stageBackground: ArticlePaperPaletteColors.nightStage,
        paperColor: ArticlePaperPaletteColors.nightPaper,
        paperBorderColor: ArticlePaperPaletteColors.nightPaperBorder,
        textColor: ArticlePaperPaletteColors.nightText,
        secondaryTextColor: ArticlePaperPaletteColors.nightSecondaryText,
        accentColor: ArticlePaperPaletteColors.nightAccent,
        badgeBackground: ArticlePaperPaletteColors.nightBadgeBackground,
        badgeTextColor: ArticlePaperPaletteColors.nightBadgeText,
        shadowColor: AppColors.black.withValues(alpha: 0.42),
        overlayColor: ArticlePaperPaletteColors.nightOverlay,
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
      ArticleFontPreset.rounded => const <String>[
        'PingFang SC',
        'SF Pro Rounded',
      ],
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
    bodyStyle: base(size: AppTypography.base, height: articleBodyLineHeight()),
    captionStyle: base(
      size: AppTypography.xs,
      weight: AppTypography.medium,
      height: AppSpacing.textLineHeightLabel,
      color: palette.secondaryTextColor,
    ),
    placeholderStyle: base(
      size: AppTypography.base,
      height: articleBodyLineHeight(),
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

/// 基于纸张质感的排版规格（替代 resolveArticleTypography）。
ArticleTypographySpec resolveArticleTypographyForPaper(
  BuildContext context,
  ArticlePaperTexture texture,
  ArticleFontPreset fontPreset,
) {
  final palette = resolveArticlePaperPalette(context, texture);

  TextStyle base({
    required double size,
    FontWeight weight = FontWeight.normal,
    double height = 1.7,
    Color? color,
  }) {
    final fallback = switch (fontPreset) {
      ArticleFontPreset.classic => const <String>[
        'STSong',
        'Songti SC',
        'Noto Serif CJK SC',
      ],
      ArticleFontPreset.handwritten => const <String>['STKaiti', 'Kaiti SC'],
      ArticleFontPreset.rounded => const <String>[
        'PingFang SC',
        'SF Pro Rounded',
      ],
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
        ArticleFontPreset.classic => 'Songti SC',
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
    bodyStyle: base(size: AppTypography.base, height: articleBodyLineHeight()),
    captionStyle: base(
      size: AppTypography.xs,
      weight: AppTypography.medium,
      height: AppSpacing.textLineHeightLabel,
      color: palette.secondaryTextColor,
    ),
    placeholderStyle: base(
      size: AppTypography.base,
      height: articleBodyLineHeight(),
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
