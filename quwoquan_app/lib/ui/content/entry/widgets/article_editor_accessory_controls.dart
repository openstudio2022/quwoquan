part of 'article_editor_accessory_panels.dart';

/// 附件工具栏按钮、图标绘制与纸张/字体横向选择器。
class _AccessoryIconButton extends StatelessWidget {
  const _AccessoryIconButton({
    required this.icon,
    required this.semanticLabel,
    required this.onPressed,
  });

  final IconData icon;
  final String semanticLabel;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null;
    final color = enabled
        ? CupertinoColors.label.resolveFrom(context)
        : CupertinoColors.tertiaryLabel.resolveFrom(context);
    return SizedBox(
      width: AppSpacing.minInteractiveSize,
      child: Semantics(
        button: true,
        label: semanticLabel,
        enabled: enabled,
        child: CupertinoButton(
          padding: EdgeInsets.zero,
          minimumSize: const Size.square(AppSpacing.iconButtonMinSizeSm),
          onPressed: onPressed,
          child: Icon(icon, size: AppSpacing.iconMedium, color: color),
        ),
      ),
    );
  }
}

enum ArticleEditorAccessoryGlyph {
  image,
  emoji,
  keyboard,
  at,
  structure,
  template,
  font,
  style,
  list,
  typography,
}

class ArticleEditorAccessoryButton extends StatelessWidget {
  const ArticleEditorAccessoryButton({
    super.key,
    required this.glyph,
    required this.semanticLabel,
    required this.onPressed,
    this.selected = false,
    this.buttonKey,
  });

  final ArticleEditorAccessoryGlyph glyph;
  final String semanticLabel;
  final VoidCallback onPressed;
  final bool selected;
  final Key? buttonKey;

  @override
  Widget build(BuildContext context) {
    final color = selected
        ? CupertinoColors.label.resolveFrom(context)
        : CupertinoColors.label.resolveFrom(context).withValues(alpha: 0.78);
    final iconSize = AppSpacing.responsiveValue(
      context,
      compact: 20,
      regular: 22,
      expanded: 23,
    );
    final strokeWidth = AppSpacing.responsiveValue(
      context,
      compact: 1.5,
      regular: 1.65,
      expanded: 1.8,
    );

    // emoji 使用 Material Icon（与聊天页底部工具栏一致）
    final Widget glyphWidget;
    if (glyph == ArticleEditorAccessoryGlyph.emoji) {
      glyphWidget = Icon(
        Icons.sentiment_satisfied_alt,
        size: iconSize + 2,
        color: color,
      );
    } else if (glyph == ArticleEditorAccessoryGlyph.at) {
      glyphWidget = Text(
        '@',
        style: TextStyle(
          color: color,
          fontSize: iconSize,
          fontWeight: AppTypography.semiBold,
          height: AppSpacing.textLineHeightSingle,
        ),
      );
    } else {
      glyphWidget = SizedBox(
        width: iconSize,
        height: iconSize,
        child: CustomPaint(
          painter: _AccessoryGlyphPainter(
            glyph: glyph,
            color: color,
            strokeWidth: strokeWidth,
          ),
        ),
      );
    }

    return SizedBox(
      width: AppSpacing.minInteractiveSize,
      child: Semantics(
        button: true,
        label: semanticLabel,
        child: CupertinoButton(
          key: buttonKey,
          padding: EdgeInsets.zero,
          minimumSize: const Size.square(AppSpacing.iconButtonMinSizeSm),
          onPressed: onPressed,
          child: Center(child: glyphWidget),
        ),
      ),
    );
  }
}

class _AccessoryGlyphPainter extends CustomPainter {
  const _AccessoryGlyphPainter({
    required this.glyph,
    required this.color,
    required this.strokeWidth,
  });

  final ArticleEditorAccessoryGlyph glyph;
  final Color color;
  final double strokeWidth;

  @override
  void paint(Canvas canvas, Size size) {
    final stroke = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    final fill = Paint()
      ..color = color
      ..style = PaintingStyle.fill;

    switch (glyph) {
      case ArticleEditorAccessoryGlyph.image:
        // 图片图标：圆角矩形框 + 右上角实心小圆点太阳 + 山峰折线（参考图一）
        final rect = RRect.fromRectAndRadius(
          Rect.fromLTWH(
            size.width * 0.06,
            size.height * 0.06,
            size.width * 0.88,
            size.height * 0.88,
          ),
          Radius.circular(size.width * 0.14),
        );
        canvas.drawRRect(rect, stroke);
        // 太阳：实心小圆点
        canvas.drawCircle(
          Offset(size.width * 0.72, size.height * 0.3),
          size.width * 0.06,
          fill,
        );
        // 山峰折线
        final mountainPath = Path()
          ..moveTo(size.width * 0.12, size.height * 0.78)
          ..lineTo(size.width * 0.36, size.height * 0.48)
          ..lineTo(size.width * 0.52, size.height * 0.6)
          ..lineTo(size.width * 0.72, size.height * 0.42)
          ..lineTo(size.width * 0.88, size.height * 0.64);
        canvas.drawPath(mountainPath, stroke);
      case ArticleEditorAccessoryGlyph.emoji:
        // emoji 由 ArticleEditorAccessoryButton 直接用 Icon 渲染
        break;
      case ArticleEditorAccessoryGlyph.at:
        // @ 由 ArticleEditorAccessoryButton 直接用 Text 渲染
        break;
      case ArticleEditorAccessoryGlyph.keyboard:
        final rect = RRect.fromRectAndRadius(
          Rect.fromLTWH(
            size.width * 0.08,
            size.height * 0.18,
            size.width * 0.84,
            size.height * 0.64,
          ),
          Radius.circular(size.width * 0.12),
        );
        canvas.drawRRect(rect, stroke);
        for (var row = 0; row < 2; row += 1) {
          final y = row == 0 ? size.height * 0.36 : size.height * 0.52;
          for (var column = 0; column < 4; column += 1) {
            final x = size.width * (0.24 + column * 0.16);
            canvas.drawCircle(Offset(x, y), size.width * 0.03, fill);
          }
        }
        canvas.drawLine(
          Offset(size.width * 0.28, size.height * 0.66),
          Offset(size.width * 0.72, size.height * 0.66),
          stroke,
        );
      case ArticleEditorAccessoryGlyph.style:
        // "Aa" 样式图标：在 iconSize×iconSize 画布内绘制，视觉居中
        final bigA = TextPainter(
          text: TextSpan(
            text: 'A',
            style: TextStyle(
              color: color,
              fontSize: size.height * 0.88,
              fontWeight: AppTypography.semiBold,
              height: AppSpacing.textLineHeightSingle,
            ),
          ),
          textDirection: TextDirection.ltr,
        )..layout();
        final smallA = TextPainter(
          text: TextSpan(
            text: 'a',
            style: TextStyle(
              color: color,
              fontSize: size.height * 0.62,
              fontWeight: AppTypography.regular,
              height: AppSpacing.textLineHeightSingle,
            ),
          ),
          textDirection: TextDirection.ltr,
        )..layout();
        // 整体水平居中
        final totalWidth = bigA.width + smallA.width - size.width * 0.06;
        final startX = (size.width - totalWidth) / 2;
        // 略低于几何中心，与描边类图标（山峰在下方）视觉重心对齐
        final baselineY = size.height * 0.88;
        // 大 A
        bigA.paint(canvas, Offset(startX, baselineY - bigA.height));
        // 小 a 底部对齐大 A
        smallA.paint(
          canvas,
          Offset(
            startX + bigA.width - size.width * 0.06,
            baselineY - smallA.height,
          ),
        );
      // 以下 glyph 不再在工具栏使用，保留以避免编译错误
      case ArticleEditorAccessoryGlyph.structure:
      case ArticleEditorAccessoryGlyph.template:
      case ArticleEditorAccessoryGlyph.font:
      case ArticleEditorAccessoryGlyph.list:
      case ArticleEditorAccessoryGlyph.typography:
        break;
    }
  }

  @override
  bool shouldRepaint(covariant _AccessoryGlyphPainter oldDelegate) {
    return oldDelegate.glyph != glyph ||
        oldDelegate.color != color ||
        oldDelegate.strokeWidth != strokeWidth;
  }
}

// ── 纸张质感滤镜式横滑选择器 ──

class _PaperTextureSelector extends StatelessWidget {
  const _PaperTextureSelector({
    required this.selected,
    required this.onSelected,
  });

  final ArticlePaperTexture selected;
  final ValueChanged<ArticlePaperTexture> onSelected;

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      scrollDirection: Axis.horizontal,
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
      itemCount: ArticlePaperTexture.values.length,
      separatorBuilder: (_, _) =>
          SizedBox(width: AppSpacing.filterTemplateItemGap),
      itemBuilder: (context, index) {
        final texture = ArticlePaperTexture.values[index];
        final isSelected = texture == selected;
        final palette = resolveArticlePaperPalette(context, texture);
        final labelColor = CupertinoColors.secondaryLabel.resolveFrom(context);
        return GestureDetector(
          onTap: () => onSelected(texture),
          child: SizedBox(
            width: AppSpacing.largeAvatarSize,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  curve: Curves.easeOutCubic,
                  width: AppSpacing.avatarCircleLg,
                  height: AppSpacing.avatarCircleLg,
                  decoration: BoxDecoration(
                    color: palette.paperColor,
                    borderRadius: BorderRadius.circular(
                      AppSpacing.borderRadius,
                    ),
                    border: Border.all(
                      color: isSelected
                          ? AppColors.iosAccent(context)
                          : palette.paperBorderColor,
                      width: isSelected ? 2.5 : 1,
                    ),
                  ),
                  child: Center(
                    child: Text(
                      CreatePageText.fontPreviewGlyph,
                      style: TextStyle(
                        fontSize: AppTypography.lg,
                        fontWeight: AppTypography.medium,
                        color: palette.textColor,
                      ),
                    ),
                  ),
                ),
                SizedBox(height: AppSpacing.xs),
                Text(
                  texture.label,
                  style: TextStyle(
                    fontSize: AppTypography.xxs,
                    fontWeight: isSelected
                        ? AppTypography.semiBold
                        : AppTypography.regular,
                    color: isSelected
                        ? CupertinoColors.label.resolveFrom(context)
                        : labelColor,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _FontPresetSelector extends StatelessWidget {
  const _FontPresetSelector({required this.selected, required this.onSelected});

  final ArticleFontPreset selected;
  final ValueChanged<ArticleFontPreset> onSelected;

  @override
  Widget build(BuildContext context) {
    final labelColor = CupertinoColors.secondaryLabel.resolveFrom(context);
    return ListView.separated(
      scrollDirection: Axis.horizontal,
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
      itemCount: ArticleFontPreset.values.length,
      separatorBuilder: (_, _) =>
          SizedBox(width: AppSpacing.filterTemplateItemGap),
      itemBuilder: (context, index) {
        final preset = ArticleFontPreset.values[index];
        final isSelected = preset == selected;
        final stack = resolveArticleFontStack(preset);
        return GestureDetector(
          onTap: () => onSelected(preset),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeOutCubic,
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.containerSm,
              vertical: AppSpacing.sm,
            ),
            decoration: BoxDecoration(
              color: isSelected
                  ? CupertinoColors.tertiarySystemFill.resolveFrom(context)
                  : CupertinoColors.systemBackground
                        .resolveFrom(context)
                        .withValues(alpha: 0),
              borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
              border: Border.all(
                color: isSelected
                    ? AppColors.iosAccent(context)
                    : CupertinoColors.separator.resolveFrom(context),
                width: isSelected ? 2 : 0.5,
              ),
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: <Widget>[
                Text(
                  CreatePageText.fontPreviewSample,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    fontFamily: stack.fontFamily,
                    fontFamilyFallback: stack.fontFamilyFallback,
                    color: CupertinoColors.label.resolveFrom(context),
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  preset.label,
                  style: TextStyle(
                    fontSize: AppTypography.xxs,
                    fontWeight: isSelected
                        ? AppTypography.semiBold
                        : AppTypography.regular,
                    color: isSelected
                        ? CupertinoColors.label.resolveFrom(context)
                        : labelColor,
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
