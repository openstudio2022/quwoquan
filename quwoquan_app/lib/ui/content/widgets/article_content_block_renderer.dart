import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/article_detail_view.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';

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
    final sectionHeadingLineHeight = articleBodyLineHeight() * 0.72;
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
          'heading_2' => Text(
            block.body,
            style: TextStyle(
              color: titleColor,
              fontSize: AppTypography.xl,
              fontWeight: AppTypography.semiBold,
              height: articleBodyLineHeight(),
            ),
          ),
          'heading_3' => Text(
            block.body,
            style: TextStyle(
              color: titleColor,
              fontSize: AppTypography.lg,
              fontWeight: AppTypography.semiBold,
              height: AppSpacing.textLineHeightHeadline,
            ),
          ),
          'section_heading' => Text(
            block.body,
            style: TextStyle(
              color: titleColor,
              fontSize: AppTypography.xl + 2,
              fontWeight: AppTypography.bold,
              height: sectionHeadingLineHeight,
              letterSpacing: 0.18,
            ),
          ),
          'image' => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              AspectRatio(
                aspectRatio: 4 / 3,
                child: ArticleAdaptiveImage(imageUrl: block.imageUrl ?? ''),
              ),
              if ((block.caption ?? '').trim().isNotEmpty) ...[
                SizedBox(height: articleCaptionSpacing()),
                Text(
                  block.caption!,
                  style: TextStyle(
                    color: bodyColor,
                    fontSize: AppTypography.sm,
                    height: articleCaptionLineHeight(),
                  ),
                ),
              ],
            ],
          ),
          'ordered_item' => Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: AppSpacing.twentyEight,
                height: AppSpacing.twentyEight,
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
                    height: articleBodyLineHeight(),
                  ),
                ),
              ),
            ],
          ),
          'bullet_item' => Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: EdgeInsets.only(top: AppSpacing.intraGroupXs),
                child: Container(
                  width: AppSpacing.sm,
                  height: AppSpacing.sm,
                  decoration: BoxDecoration(
                    color: CupertinoColors.activeBlue.resolveFrom(context),
                    borderRadius: BorderRadius.circular(AppSpacing.xs),
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
                    height: articleBodyLineHeight(),
                  ),
                ),
              ),
            ],
          ),
          'wrapped_paragraph' => ArticleWrappedParagraph(
            imageUrl: block.imageUrl ?? '',
            body: block.body,
            imageLayout: block.imageLayout,
            caption: block.caption ?? '',
          ),
          'section' => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if ((block.imageUrl ?? '').isNotEmpty) ...[
                AspectRatio(
                  aspectRatio: 16 / 10,
                  child: ArticleAdaptiveImage(imageUrl: block.imageUrl!),
                ),
                SizedBox(height: articleChapterSpacing()),
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
                    height: articleBodyLineHeight(),
                  ),
                ),
              if ((block.caption ?? '').trim().isNotEmpty) ...[
                SizedBox(height: articleCaptionSpacing()),
                Text(
                  block.caption!,
                  style: TextStyle(
                    color: bodyColor,
                    fontSize: AppTypography.sm,
                    height: articleCaptionLineHeight(),
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
              height: articleBodyLineHeight(),
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
        imageBuilder: (context, imageProvider) => Image(
          image: imageProvider,
          fit: BoxFit.cover,
          filterQuality: FilterQuality.high,
        ),
        placeholder: (context, url) =>
            Container(color: CupertinoColors.systemGrey5.resolveFrom(context)),
        errorWidget: (context, url, error) =>
            Container(color: CupertinoColors.systemGrey5.resolveFrom(context)),
      );
    }
    return Image.file(
      File(imageUrl),
      fit: BoxFit.cover,
      filterQuality: FilterQuality.high,
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
    this.caption = '',
    this.metrics,
  });

  final String imageUrl;
  final String body;
  final String imageLayout;
  final String caption;
  final ArticleCanvasMetrics? metrics;

  @override
  Widget build(BuildContext context) {
    final textStyle = TextStyle(
      color: CupertinoColors.label.resolveFrom(context),
      fontSize: AppTypography.base,
      height: articleBodyLineHeight(),
    );
    final captionStyle = TextStyle(
      color: CupertinoColors.secondaryLabel.resolveFrom(context),
      fontSize: AppTypography.sm,
      height: articleCaptionLineHeight(),
    );
    return LayoutBuilder(
      builder: (context, constraints) {
        final resolvedMetrics = metrics ?? ArticleCanvasMetrics.snapshot();
        final wrap = resolveArticleWrapLayout(
          ArticleWrapLayoutInput(
            body: body,
            rowContentWidth: constraints.maxWidth,
            bodyStyle: textStyle,
            captionText: caption,
            captionStyle: captionStyle,
            captionPlaceholderWhenEmpty: false,
            imageLayout: imageLayout,
            metrics: resolvedMetrics,
          ),
        );
        final textColumn = Expanded(
          child: Text(
            wrap.leadingText.trim().isEmpty ? body : wrap.leadingText.trim(),
            style: textStyle,
          ),
        );
        final image = SizedBox(
          width: wrap.layout.imageWidth,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              SizedBox(
                width: wrap.layout.imageWidth,
                height: wrap.layout.imageHeight,
                child: ArticleAdaptiveImage(imageUrl: imageUrl),
              ),
              if (caption.trim().isNotEmpty) ...<Widget>[
                SizedBox(height: wrap.layout.captionSpacing),
                Text(
                  caption.trim(),
                  textAlign: TextAlign.center,
                  style: captionStyle,
                ),
              ],
            ],
          ),
        );
        final rowChildren = imageLayout == 'wrapRight'
            ? <Widget>[textColumn, SizedBox(width: wrap.layout.sideGap), image]
            : <Widget>[image, SizedBox(width: wrap.layout.sideGap), textColumn];
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: rowChildren,
            ),
            if (wrap.trailingText.trim().isNotEmpty) ...[
              SizedBox(height: wrap.layout.trailingSpacing),
              Text(wrap.trailingText.trim(), style: textStyle),
            ],
          ],
        );
      },
    );
  }
}
