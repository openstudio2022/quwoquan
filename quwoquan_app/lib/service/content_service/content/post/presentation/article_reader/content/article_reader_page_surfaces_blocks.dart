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
      ArticleDocumentBlockType.quote ||
      ArticleDocumentBlockType.callout ||
      ArticleDocumentBlockType.codeBlock =>
        ArticleRichBlockChrome.textStyleFor(block.type, typography.bodyStyle),
      _ => typography.bodyStyle,
    };
    final inlineText = _ArticleInlineText(
      text: block.text.trim(),
      spans: block.spans,
      style: style,
      onEntityTap: onEntityTap,
    );
    // 嵌套列表缩进（GWT-004）：listDepth 与 codec 缩进同一约定。
    if ((block.type == ArticleDocumentBlockType.orderedItem ||
            block.type == ArticleDocumentBlockType.bulletItem) &&
        block.listDepth > 0) {
      return Padding(
        key: ValueKey<String>('article-list-depth-${block.listDepth}'),
        padding: EdgeInsets.only(
          left: block.listDepth.clamp(0, 2) * AppSpacing.containerSm,
        ),
        child: inlineText,
      );
    }
    // 富块容器（GWT-003）：几何与分页测量共用 ArticleRichBlockChrome。
    final accent = typography.bodyStyle.color ?? AppColors.worksTitle;
    return switch (block.type) {
      ArticleDocumentBlockType.quote => Container(
        key: const ValueKey<String>('article-rich-quote'),
        padding: const EdgeInsets.only(left: ArticleRichBlockChrome.quoteGap),
        decoration: BoxDecoration(
          border: Border(
            left: BorderSide(
              color: accent.withValues(alpha: 0.32),
              width: ArticleRichBlockChrome.quoteBarWidth,
            ),
          ),
        ),
        child: inlineText,
      ),
      ArticleDocumentBlockType.callout => Container(
        key: const ValueKey<String>('article-rich-callout'),
        width: double.infinity,
        padding: ArticleRichBlockChrome.calloutPadding,
        decoration: BoxDecoration(
          color: accent.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
        ),
        child: inlineText,
      ),
      ArticleDocumentBlockType.codeBlock => Container(
        key: const ValueKey<String>('article-rich-code'),
        width: double.infinity,
        padding: ArticleRichBlockChrome.codePadding,
        decoration: BoxDecoration(
          color: accent.withValues(alpha: 0.06),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
          border: Border.all(
            color: accent.withValues(alpha: 0.12),
            width: AppSpacing.hairline,
          ),
        ),
        child: Text(block.text.trimRight(), style: style),
      ),
      _ => inlineText,
    };
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
    if (spans.isEmpty) {
      return Text(text, style: style);
    }
    // 行内分段唯一真相源（GWT-002）：与序列化共用同一字符级合成，
    // mention 原子段可点，样式段按 span 布尔渲染，无第二套切分。
    final segments = resolveArticleInlineSegments(text, spans);
    if (segments.isEmpty) {
      return Text(text, style: style);
    }
    final children = <InlineSpan>[];
    for (final segment in segments) {
      final raw = text.substring(segment.start, segment.end);
      final mention = segment.mention;
      if (mention != null) {
        // 链接段与 mention 段共用原子分段与 tap 通道；链接不加粗以示区分。
        final isLink = mention.isLink;
        children.add(
          TextSpan(
            text: raw,
            style: style.copyWith(
              color: AppColors.worksAccent,
              fontWeight: isLink ? null : AppTypography.semiBold,
              decoration: TextDecoration.underline,
              decorationColor: AppColors.worksAccent.withValues(alpha: 0.64),
            ),
            recognizer: TapGestureRecognizer()
              ..onTap = () => onEntityTap?.call(mention),
          ),
        );
        continue;
      }
      if (!segment.hasStyle) {
        children.add(TextSpan(text: raw));
        continue;
      }
      final decorations = <TextDecoration>[
        if (segment.underline) TextDecoration.underline,
        if (segment.strikethrough) TextDecoration.lineThrough,
      ];
      children.add(
        TextSpan(
          text: raw,
          style: style.copyWith(
            fontWeight: segment.bold ? AppTypography.bold : null,
            fontStyle: segment.italic ? FontStyle.italic : null,
            decoration: decorations.isEmpty
                ? null
                : TextDecoration.combine(decorations),
          ),
        ),
      );
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
