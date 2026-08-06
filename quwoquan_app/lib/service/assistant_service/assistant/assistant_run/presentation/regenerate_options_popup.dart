import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/l10n/copy/assistant_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

enum RegenerateOption { regenerate, concise, detailed, casual, deepThink }

extension RegenerateOptionLabel on RegenerateOption {
  String get label {
    switch (this) {
      case RegenerateOption.regenerate:
        return AssistantText.assistantActionRegenerate;
      case RegenerateOption.concise:
        return AssistantText.assistantActionBrief;
      case RegenerateOption.detailed:
        return AssistantText.assistantActionDetailed;
      case RegenerateOption.casual:
        return AssistantText.assistantActionCasual;
      case RegenerateOption.deepThink:
        return AssistantText.assistantActionDeepThink;
    }
  }

  IconData get icon {
    switch (this) {
      case RegenerateOption.regenerate:
        return CupertinoIcons.arrow_2_circlepath;
      case RegenerateOption.concise:
        return CupertinoIcons.text_justify;
      case RegenerateOption.detailed:
        return CupertinoIcons.doc_text;
      case RegenerateOption.casual:
        return CupertinoIcons.chat_bubble_text;
      case RegenerateOption.deepThink:
        return CupertinoIcons.lightbulb;
    }
  }
}

class RegenerateOptionsPopup extends StatelessWidget {
  const RegenerateOptionsPopup({
    super.key,
    required this.anchorRect,
    this.onSelected,
  });

  final Rect anchorRect;
  final void Function(RegenerateOption option)? onSelected;

  static const _options = RegenerateOption.values;
  static const double _itemHeight = AppSpacing.forty;
  static const double _popupWidth = AppSpacing.oneHundredSixty;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final bgColor = isDark ? AppColors.iosSystemSurfaceDark : AppColors.white;
    final textColor = isDark
        ? AppColors.iosPopupPrimaryLabelOnDark
        : AppColors.iosPopupPrimaryLabelOnLight;
    final dividerColor = isDark
        ? AppColors.iosPopupHairlineSeparatorDark
        : AppColors.iosPopupHairlineSeparatorLight;

    final popupHeight = _options.length * _itemHeight;
    final popupTop = anchorRect.top - popupHeight - AppSpacing.sm;
    final popupLeft = anchorRect.right - _popupWidth;

    return Stack(
      children: [
        GestureDetector(
          onTap: () => Navigator.of(context).pop(),
          behavior: HitTestBehavior.translucent,
          child: const SizedBox.expand(),
        ),
        Positioned(
          left: popupLeft.clamp(
            AppSpacing.sm,
            MediaQuery.of(context).size.width - _popupWidth - AppSpacing.sm,
          ),
          top: popupTop.clamp(
            AppSpacing.sm,
            MediaQuery.of(context).size.height - popupHeight - AppSpacing.sm,
          ),
          child: ColoredBox(
            color: AppColors.transparent,
            child: Container(
              width: _popupWidth,
              decoration: BoxDecoration(
                color: bgColor,
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                boxShadow: [
                  BoxShadow(
                    color: AppColors.black.withValues(
                      alpha: isDark ? 0.4 : 0.12,
                    ),
                    blurRadius: AppSpacing.md,
                    offset: const Offset(AppSpacing.zero, -AppSpacing.xs),
                  ),
                ],
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    for (int i = 0; i < _options.length; i++) ...[
                      if (i > 0)
                        Container(
                          height: AppSpacing.hairline,
                          margin: EdgeInsets.symmetric(
                            horizontal: AppSpacing.intraGroupLg,
                          ),
                          color: dividerColor,
                        ),
                      _buildItem(_options[i], textColor),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildItem(RegenerateOption option, Color textColor) {
    return GestureDetector(
      onTap: () => onSelected?.call(option),
      behavior: HitTestBehavior.opaque,
      child: SizedBox(
        height: _itemHeight,
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpacing.fourteen),
          child: Row(
            children: [
              Icon(option.icon, size: AppSpacing.iconSmall, color: textColor),
              SizedBox(width: AppSpacing.sm + AppSpacing.xs / 2),
              Text(
                option.label,
                style: TextStyle(
                  fontSize: AppTypography.base,
                  color: textColor,
                  fontWeight: FontWeight.w400,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
