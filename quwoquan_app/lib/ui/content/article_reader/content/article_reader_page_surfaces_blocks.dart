part of 'article_reader_page_surfaces.dart';

class _ArticleSemanticBlock extends StatelessWidget {
  const _ArticleSemanticBlock({
    required this.block,
    required this.typography,
    this.onEntityTap,
  });

  final ArticleDocumentBlock block;
  final ArticleTypographySpec typography;
  final ValueChanged<ArticleInlineSpan>? onEntityTap;

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
        fontSize: math.max(bodyFont * 1.14, AppTypography.xl),
        fontWeight: AppTypography.semiBold,
      ),
      ArticleDocumentBlockType.sectionTitle => typography.titleStyle.copyWith(
        fontSize: math.max(bodyFont * 1.28, AppTypography.xxl),
        fontWeight: AppTypography.bold,
        letterSpacing: 0.18,
      ),
      _ => typography.bodyStyle,
    };
    return _ArticleInlineText(
      text: block.text.trim(),
      spans: block.spans,
      style: style,
      onEntityTap: onEntityTap,
    );
  }
}

class _ArticleInlineText extends StatelessWidget {
  const _ArticleInlineText({
    required this.text,
    required this.spans,
    required this.style,
    this.onEntityTap,
  });

  final String text;
  final List<ArticleInlineSpan> spans;
  final TextStyle style;
  final ValueChanged<ArticleInlineSpan>? onEntityTap;

  @override
  Widget build(BuildContext context) {
    final mentionSpans = spans.where((span) => span.isInlineMention).toList()
      ..sort((a, b) => a.start.compareTo(b.start));
    if (mentionSpans.isEmpty) {
      return Text(text, style: style);
    }
    final children = <InlineSpan>[];
    var cursor = 0;
    for (final span in mentionSpans) {
      final start = span.start.clamp(0, text.length);
      final end = span.end.clamp(start, text.length);
      if (start < cursor) continue;
      if (start > cursor) {
        children.add(TextSpan(text: text.substring(cursor, start)));
      }
      final label = text.substring(start, end);
      children.add(
        TextSpan(
          text: label,
          style: style.copyWith(
            color: AppColors.worksAccent,
            fontWeight: AppTypography.semiBold,
            decoration: TextDecoration.underline,
            decorationColor: AppColors.worksAccent.withValues(alpha: 0.64),
          ),
          recognizer: TapGestureRecognizer()
            ..onTap = () => onEntityTap?.call(span),
        ),
      );
      cursor = end;
    }
    if (cursor < text.length) {
      children.add(TextSpan(text: text.substring(cursor)));
    }
    return RichText(
      key: const ValueKey<String>('article-entity-rich-text'),
      text: TextSpan(style: style, children: children),
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
              blurRadius: AppSpacing.ten,
              offset: const Offset(0, AppSpacing.intraGroupXs),
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

  static const double _compactVerticalPadding = 5;

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
          horizontal: compact ? AppSpacing.ten : AppSpacing.containerSm,
          vertical: compact ? _compactVerticalPadding : AppSpacing.intraGroupSm,
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
              blurRadius: AppSpacing.fourteen,
              offset: const Offset(0, AppSpacing.six),
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
