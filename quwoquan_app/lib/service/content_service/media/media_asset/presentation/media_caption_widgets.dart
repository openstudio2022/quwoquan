import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_viewer_layout.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/spacing/spacing_extensions.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

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
              SizedBox(
                height: context.safeGetIntraGroupSpacing(SpacingSize.xs),
              ),
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
              SizedBox(
                height: context.safeGetIntraGroupSpacing(SpacingSize.xs),
              ),
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
              SizedBox(
                height: context.safeGetIntraGroupSpacing(SpacingSize.xs),
              ),
              footer!,
            ],
          ],
        ),
      ),
    );
  }

  /// 「全文」/「收起」入口样式：沉浸前景次级层级（REQ-019，非品牌色），
  /// 以字重与透明度区别于正文，不喧宾夺主。
  TextStyle _entryStyle(TextStyle captionStyle) => captionStyle.copyWith(
    color: AppColors.immersiveForeground.withValues(alpha: 0.7),
    fontWeight: AppTypography.medium,
  );

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

        final entryStyle = _entryStyle(captionStyle);

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
                            text: CommunityText.collapse,
                            style: entryStyle,
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
                          caption: caption,
                          captionStyle: captionStyle,
                          entryStyle: entryStyle,
                          basePainter: overflowPainter,
                          maxWidth: constraints.maxWidth,
                          maxLines: captionOverflowMaxLines,
                        ),
                        style: captionStyle,
                      ),
                      TextSpan(
                        text: CommunityText.ellipsis,
                        style: captionStyle,
                      ),
                      TextSpan(text: CommunityText.fullText, style: entryStyle),
                    ],
                  ),
                ),
        );
      },
    );
  }

  /// 截断正文，保证「…全文」完整落在收起态最后一行行尾（REQ-019）：
  /// 先按入口文本实际宽度在末行预留截断锚点，再对完整 rich text 做
  /// maxLines 布局验证，不满足则按字素回退——任何字体/字号/内容组合下
  /// 「全文」都不会断字或被挤到下一行。
  String _truncateCaption({
    required String caption,
    required TextStyle captionStyle,
    required TextStyle entryStyle,
    required TextPainter basePainter,
    required double maxWidth,
    required int maxLines,
  }) {
    final entryPainter = TextPainter(
      text: TextSpan(
        children: [
          TextSpan(text: CommunityText.ellipsis, style: captionStyle),
          TextSpan(text: CommunityText.fullText, style: entryStyle),
        ],
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    final reservedWidth = entryPainter.width;

    var cut = basePainter
        .getPositionForOffset(
          Offset(
            math.max(0, maxWidth - reservedWidth),
            basePainter.height,
          ),
        )
        .offset
        .clamp(0, caption.length);
    // getPositionForOffset 返回 UTF-16 位点，避免切断 surrogate pair。
    while (cut > 0 && _isLowSurrogate(caption.codeUnitAt(cut - 1))) {
      cut -= 1;
    }

    bool fits(String truncated) {
      final probe = TextPainter(
        text: TextSpan(
          children: [
            TextSpan(text: truncated, style: captionStyle),
            TextSpan(text: CommunityText.ellipsis, style: captionStyle),
            TextSpan(text: CommunityText.fullText, style: entryStyle),
          ],
        ),
        maxLines: maxLines,
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: maxWidth);
      return !probe.didExceedMaxLines;
    }

    var truncated = caption.substring(0, cut);
    while (truncated.isNotEmpty && !fits(truncated)) {
      truncated = truncated.characters.skipLast(1).toString();
    }
    return truncated;
  }

  static bool _isLowSurrogate(int codeUnit) =>
      (codeUnit & 0xFC00) == 0xDC00;
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
