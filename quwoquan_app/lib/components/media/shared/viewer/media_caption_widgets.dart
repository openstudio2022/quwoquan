import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/media/shared/viewer/immersive_viewer_layout.dart';

class MediaCaptionBlock extends StatelessWidget {
  const MediaCaptionBlock({
    super.key,
    required this.title,
    required this.caption,
    required this.isExpanded,
    required this.onToggle,
    this.layoutSpec = ImmersiveViewerStageLayoutSpec.feedRail,
    this.railKey,
    this.header,
    this.titleTrailing,
    this.preCaption,
    this.footer,
  });

  final String title;
  final String caption;
  final bool isExpanded;
  final VoidCallback onToggle;
  final ImmersiveViewerStageLayoutSpec layoutSpec;
  final Key? railKey;
  final Widget? header;
  final Widget? titleTrailing;
  final Widget? preCaption;
  final Widget? footer;

  @override
  Widget build(BuildContext context) {
    final titleStyle = TextStyle(
      color: AppColors.white,
      fontSize: AppTypography.lg,
      fontWeight: FontWeight.w600,
    );
    final captionStyle = TextStyle(
      color: AppColors.white,
      fontSize: AppTypography.base,
      fontWeight: FontWeight.normal,
    );

    return ImmersiveViewerLayout.alignToRail(
      context: context,
      layoutSpec: layoutSpec,
      child: SizedBox(
        key: railKey,
        width: double.infinity,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (header != null) ...[
              Align(alignment: Alignment.center, child: header!),
              SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.xs)),
            ],
            if (title.isNotEmpty)
              Padding(
                padding: EdgeInsets.only(
                  bottom: context.safeGetIntraGroupSpacing(SpacingSize.xs),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Text(
                        title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: titleStyle,
                      ),
                    ),
                    if (titleTrailing != null) ...[
                      SizedBox(
                        width: context.safeGetIntraGroupSpacing(SpacingSize.sm),
                      ),
                      titleTrailing!,
                    ],
                  ],
                ),
              ),
            if (title.isEmpty && preCaption != null) ...[
              preCaption!,
              SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.xs)),
            ],
            if (caption.isNotEmpty)
              _buildExpandableCaption(
                context,
                caption: caption,
                isExpanded: isExpanded,
                onToggle: onToggle,
                captionStyle: captionStyle,
              ),
            if (footer != null) ...[
              SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.xs)),
              footer!,
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildExpandableCaption(
    BuildContext context, {
    required String caption,
    required bool isExpanded,
    required VoidCallback onToggle,
    required TextStyle captionStyle,
  }) {
    return LayoutBuilder(
      builder: (context, constraints) {
        // 溢出判断必须使用固定行数，不能依赖 isExpanded：若用 maxLines: isExpanded ? null : 3，
        // didExceedMaxLines 在展开时恒为 false，会走下面 early return 导致无法显示「收起」按钮。
        const int captionOverflowMaxLines = 3;
        final overflowPainter = TextPainter(
          text: TextSpan(text: caption, style: captionStyle),
          maxLines: captionOverflowMaxLines,
          textDirection: TextDirection.ltr,
        )..layout(maxWidth: constraints.maxWidth);
        final isOverflow = overflowPainter.didExceedMaxLines;

        if (!isOverflow) {
          return Text(caption, style: captionStyle);
        }

        return GestureDetector(
          onTap: onToggle,
          child: isExpanded
              ? ConstrainedBox(
                  constraints: BoxConstraints(
                    maxHeight:
                        (captionStyle.fontSize ?? AppTypography.base) * 12,
                  ),
                  child: SingleChildScrollView(
                    child: Text.rich(
                      TextSpan(
                        children: [
                          TextSpan(text: caption, style: captionStyle),
                          TextSpan(
                            text: UITextConstants.collapse,
                            style: captionStyle.copyWith(
                              color: AppColors.primaryColor,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                )
              : Text.rich(
                  TextSpan(
                    children: [
                      TextSpan(
                        text: _truncateCaption(
                          caption,
                          overflowPainter,
                          constraints.maxWidth,
                        ),
                        style: captionStyle,
                      ),
                      TextSpan(
                        text: UITextConstants.fullText,
                        style: captionStyle.copyWith(
                          color: AppColors.primaryColor,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
        );
      },
    );
  }

  String _truncateCaption(
    String caption,
    TextPainter textPainter,
    double maxWidth,
  ) {
    final position = textPainter.getPositionForOffset(
      Offset(maxWidth, textPainter.height),
    );
    final truncatedLength = (position.offset - 4).clamp(0, caption.length);
    return '${caption.substring(0, truncatedLength)}${UITextConstants.ellipsis}';
  }
}

class MediaBlurCaptionOverlay extends StatelessWidget {
  const MediaBlurCaptionOverlay({
    super.key,
    required this.title,
    required this.caption,
    required this.isExpanded,
    required this.onToggle,
    this.footer,
  });

  final String title;
  final String caption;
  final bool isExpanded;
  final VoidCallback onToggle;
  final Widget? footer;

  @override
  Widget build(BuildContext context) {
    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: AppSpacing.sm, sigmaY: AppSpacing.sm),
        child: Container(
          padding: EdgeInsets.symmetric(
            vertical: context.safeGetIntraGroupSpacing(SpacingSize.sm),
          ),
          color: AppColors.overlayLight,
          child: MediaCaptionBlock(
            title: title,
            caption: caption,
            isExpanded: isExpanded,
            onToggle: onToggle,
            footer: footer,
          ),
        ),
      ),
    );
  }
}
