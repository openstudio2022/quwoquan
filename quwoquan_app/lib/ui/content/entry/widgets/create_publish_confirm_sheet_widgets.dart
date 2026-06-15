import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class PublishConfirmChipWrap extends StatelessWidget {
  const PublishConfirmChipWrap({
    super.key,
    required this.labels,
    required this.onRemove,
  });

  final List<String> labels;
  final ValueChanged<int> onRemove;

  @override
  Widget build(BuildContext context) {
    if (labels.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: EdgeInsets.only(top: AppSpacing.intraGroupSm),
      child: Wrap(
        spacing: AppSpacing.intraGroupXs,
        runSpacing: AppSpacing.intraGroupXs,
        children: <Widget>[
          for (var i = 0; i < labels.length; i++)
            CupertinoButton(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.intraGroupXs,
              ),
              minimumSize: const Size(
                AppSpacing.iconButtonMinSizeSm,
                AppSpacing.iconButtonMinSizeSm,
              ),
              color: AppColors.iosSecondaryFill(context),
              borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
              onPressed: () => onRemove(i),
              child: Text(
                '${labels[i]} ×',
                style: TextStyle(
                  color: AppColors.iosLabel(context),
                  fontSize: AppTypography.sm,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class PublishConfirmExpandablePreviewText extends StatelessWidget {
  const PublishConfirmExpandablePreviewText({
    super.key,
    required this.text,
    required this.expanded,
    required this.onToggle,
  });

  final String text;
  final bool expanded;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    const maxLines = 3;
    final style = TextStyle(
      fontSize: AppTypography.base,
      color: CupertinoColors.label.resolveFrom(context),
      height: AppTypography.lineHeightCompact,
    );

    return LayoutBuilder(
      builder: (context, constraints) {
        final textPainter = TextPainter(
          text: TextSpan(text: text, style: style),
          maxLines: maxLines,
          textDirection: TextDirection.ltr,
        )..layout(maxWidth: constraints.maxWidth);
        final isOverflow = textPainter.didExceedMaxLines;

        if (!isOverflow) {
          return Text(text, style: style);
        }

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(
              text,
              style: style,
              maxLines: expanded ? null : maxLines,
              overflow: expanded ? null : TextOverflow.ellipsis,
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            CupertinoButton(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.intraGroupXs,
              ),
              minimumSize: const Size(
                AppSpacing.buttonHeightXs,
                AppSpacing.buttonHeightXs,
              ),
              color: AppColors.iosAccentLight.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
              onPressed: onToggle,
              child: Text(
                expanded ? '收起' : '展开',
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: AppColors.iosAccentLight,
                  fontWeight: AppTypography.medium,
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

class PublishConfirmSheetEntrance extends StatelessWidget {
  const PublishConfirmSheetEntrance({
    super.key,
    required this.child,
    required this.visible,
    this.beginOffsetY = 0.04,
    this.beginScale = 0.985,
  });

  final Widget child;
  final bool visible;
  final double beginOffsetY;
  final double beginScale;

  @override
  Widget build(BuildContext context) {
    return AnimatedSlide(
      offset: visible ? Offset.zero : Offset(0, beginOffsetY),
      duration: const Duration(milliseconds: 360),
      curve: Curves.easeOutCubic,
      child: AnimatedScale(
        scale: visible ? 1 : beginScale,
        duration: const Duration(milliseconds: 420),
        curve: Curves.easeOutCubic,
        child: AnimatedOpacity(
          opacity: visible ? 1 : 0,
          duration: const Duration(milliseconds: 240),
          curve: Curves.easeOutCubic,
          child: child,
        ),
      ),
    );
  }
}

class PublishConfirmSettingRow extends StatelessWidget {
  const PublishConfirmSettingRow({
    super.key,
    required this.title,
    required this.value,
    this.onTap,
    this.borderRadius = BorderRadius.zero,
  });

  final String title;
  final String value;
  final VoidCallback? onTap;
  final BorderRadius borderRadius;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return IosSelectionOptionTile(
      title: Text(
        title,
        style: TextStyle(
          color: AppColors.iosLabel(context),
          fontSize: AppTypography.iosCallout,
          fontWeight: AppTypography.normal,
        ),
      ),
      additionalInfo: value,
      additionalInfoTextStyle: TextStyle(
        color: SettingsSemanticConstants.createSettingItemValueColor(isDark),
        fontSize: AppTypography.iosCallout,
        fontWeight: AppTypography.normal,
      ),
      showChevron: onTap != null,
      onTap: onTap,
      backgroundColor: AppColors.transparent,
      pressedColor: AppColors.iosSecondaryFill(context),
      borderRadius: borderRadius,
    );
  }
}
