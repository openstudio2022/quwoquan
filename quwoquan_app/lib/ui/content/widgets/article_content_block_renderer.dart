import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/article_detail_view.dart';

class ArticleContentSurface extends StatelessWidget {
  const ArticleContentSurface({
    super.key,
    required this.child,
    this.highlighted = false,
    this.padding,
    this.backgroundColor,
  });

  final Widget child;
  final bool highlighted;
  final EdgeInsets? padding;
  final Color? backgroundColor;

  @override
  Widget build(BuildContext context) {
    final panelColor =
        backgroundColor ??
        CupertinoColors.systemBackground.resolveFrom(context);
    final borderColor = highlighted
        ? CupertinoColors.activeBlue.resolveFrom(context)
        : CupertinoColors.separator
              .resolveFrom(context)
              .withValues(alpha: 0.14);
    return Container(
      padding: padding ?? EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: panelColor,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        border: Border.all(color: borderColor),
      ),
      child: child,
    );
  }
}

class ArticleContentBlockRenderer extends StatelessWidget {
  const ArticleContentBlockRenderer({
    super.key,
    required this.block,
    this.highlighted = false,
    this.onTap,
    this.backgroundColor,
    this.padding,
  });

  final ArticleContentBlockView block;
  final bool highlighted;
  final VoidCallback? onTap;
  final Color? backgroundColor;
  final EdgeInsets? padding;

  @override
  Widget build(BuildContext context) {
    final titleColor = CupertinoColors.label.resolveFrom(context);
    final bodyColor = CupertinoColors.secondaryLabel.resolveFrom(context);

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: ArticleContentSurface(
        highlighted: highlighted,
        backgroundColor: backgroundColor,
        padding: padding,
        child: switch (block.type) {
          'image' => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
                child: AspectRatio(
                  aspectRatio: 4 / 3,
                  child: ArticleAdaptiveImage(imageUrl: block.imageUrl ?? ''),
                ),
              ),
              if ((block.caption ?? '').trim().isNotEmpty) ...[
                SizedBox(height: AppSpacing.intraGroupSm),
                Text(
                  block.caption!,
                  style: TextStyle(
                    color: bodyColor,
                    fontSize: AppTypography.sm,
                  ),
                ),
              ],
            ],
          ),
          'ordered_item' => Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 28,
                height: 28,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: CupertinoColors.activeBlue
                      .resolveFrom(context)
                      .withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(
                    AppSpacing.radiusNinetyNine,
                  ),
                ),
                child: Text(
                  '${block.orderedIndex ?? 1}',
                  style: TextStyle(
                    color: CupertinoColors.activeBlue.resolveFrom(context),
                    fontSize: AppTypography.sm,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
              ),
              SizedBox(width: AppSpacing.containerSm),
              Expanded(
                child: Text(
                  block.body,
                  style: TextStyle(
                    color: titleColor,
                    fontSize: AppTypography.base,
                    height: 1.8, // ignore: verify_dart_semantic
                  ),
                ),
              ),
            ],
          ),
          'wrapped_paragraph' => ArticleWrappedParagraph(
            imageUrl: block.imageUrl ?? '',
            body: block.body,
            imageLayout: block.imageLayout,
          ),
          'section' => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if ((block.imageUrl ?? '').isNotEmpty) ...[
                ClipRRect(
                  borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
                  child: AspectRatio(
                    aspectRatio: 16 / 10,
                    child: ArticleAdaptiveImage(imageUrl: block.imageUrl!),
                  ),
                ),
                SizedBox(height: AppSpacing.interGroupSm),
              ],
              if (block.title.trim().isNotEmpty) ...[
                Text(
                  block.title,
                  style: TextStyle(
                    color: titleColor,
                    fontSize: AppTypography.xl,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupSm),
              ],
              if (block.body.trim().isNotEmpty)
                Text(
                  block.body,
                  style: TextStyle(
                    color: titleColor,
                    fontSize: AppTypography.base,
                    height: 1.8, // ignore: verify_dart_semantic
                  ),
                ),
              if ((block.caption ?? '').trim().isNotEmpty) ...[
                SizedBox(height: AppSpacing.intraGroupSm),
                Text(
                  block.caption!,
                  style: TextStyle(
                    color: bodyColor,
                    fontSize: AppTypography.sm,
                  ),
                ),
              ],
            ],
          ),
          _ => Text(
            block.body,
            style: TextStyle(
              color: titleColor,
              fontSize: AppTypography.base,
              height: 1.9, // ignore: verify_dart_semantic
            ),
          ),
        },
      ),
    );
  }
}

class ArticleAdaptiveImage extends StatelessWidget {
  const ArticleAdaptiveImage({super.key, required this.imageUrl});

  final String imageUrl;

  @override
  Widget build(BuildContext context) {
    if (imageUrl.trim().isEmpty) {
      return Container(color: CupertinoColors.systemGrey5.resolveFrom(context));
    }
    if (imageUrl.startsWith('http://') || imageUrl.startsWith('https://')) {
      return CachedNetworkImage(
        imageUrl: imageUrl,
        fit: BoxFit.cover,
        placeholder: (context, url) =>
            Container(color: CupertinoColors.systemGrey5.resolveFrom(context)),
        errorWidget: (context, url, error) =>
            Container(color: CupertinoColors.systemGrey5.resolveFrom(context)),
      );
    }
    return Image.file(
      File(imageUrl),
      fit: BoxFit.cover,
      errorBuilder: (context, error, stackTrace) =>
          Container(color: CupertinoColors.systemGrey5.resolveFrom(context)),
    );
  }
}

class ArticleWrappedParagraph extends StatelessWidget {
  const ArticleWrappedParagraph({
    super.key,
    required this.imageUrl,
    required this.body,
    required this.imageLayout,
  });

  final String imageUrl;
  final String body;
  final String imageLayout;

  @override
  Widget build(BuildContext context) {
    final textStyle = TextStyle(
      color: CupertinoColors.label.resolveFrom(context),
      fontSize: AppTypography.base,
      height: 1.85, // ignore: verify_dart_semantic
    );
    const imageWidth = 120.0;
    const imageHeight = 120.0;
    final horizontalGap = AppSpacing.containerSm;
    return LayoutBuilder(
      builder: (context, constraints) {
        final sideWidth = (constraints.maxWidth - imageWidth - horizontalGap)
            .clamp(120.0, constraints.maxWidth)
            .toDouble();
        final lineHeight =
            (textStyle.fontSize ?? AppTypography.base) *
            (textStyle.height ?? 1.0);
        final maxLinesBesideImage = (imageHeight / lineHeight).floor().clamp(
          2,
          8,
        );
        final splitIndex = resolveWrappedSplitIndex(
          text: body,
          sideWidth: sideWidth,
          style: textStyle,
          maxLines: maxLinesBesideImage,
        );
        final leadingText = body.substring(0, splitIndex).trim();
        final trailingText = body.substring(splitIndex).trim();
        final textColumn = Expanded(
          child: Text(
            leadingText.isEmpty ? body : leadingText,
            style: textStyle,
          ),
        );
        final image = SizedBox(
          width: imageWidth,
          height: imageHeight,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
            child: ArticleAdaptiveImage(imageUrl: imageUrl),
          ),
        );
        final rowChildren = imageLayout == 'wrapRight'
            ? <Widget>[textColumn, SizedBox(width: horizontalGap), image]
            : <Widget>[image, SizedBox(width: horizontalGap), textColumn];
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: rowChildren,
            ),
            if (trailingText.isNotEmpty) ...[
              SizedBox(height: AppSpacing.intraGroupSm),
              Text(trailingText, style: textStyle),
            ],
          ],
        );
      },
    );
  }
}

int resolveWrappedSplitIndex({
  required String text,
  required double sideWidth,
  required TextStyle style,
  required int maxLines,
}) {
  var low = 0;
  var high = text.length;
  var best = 0;
  while (low <= high) {
    final mid = (low + high) ~/ 2;
    final painter = TextPainter(
      text: TextSpan(text: text.substring(0, mid), style: style),
      textDirection: TextDirection.ltr,
      maxLines: maxLines,
    )..layout(maxWidth: sideWidth);
    if (!painter.didExceedMaxLines) {
      best = mid;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  return best.clamp(0, text.length);
}
