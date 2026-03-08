import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

enum RegenerateOption {
  regenerate,
  concise,
  detailed,
  casual,
  deepThink,
}

extension RegenerateOptionLabel on RegenerateOption {
  String get label {
    switch (this) {
      case RegenerateOption.regenerate:
        return '重新生成';
      case RegenerateOption.concise:
        return '更加简洁';
      case RegenerateOption.detailed:
        return '更加详细';
      case RegenerateOption.casual:
        return '更口语化';
      case RegenerateOption.deepThink:
        return '深度思考';
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

/// Popup that appears above the regenerate button with 5 options.
class RegenerateOptionsPopup extends StatelessWidget {
  const RegenerateOptionsPopup({
    super.key,
    required this.anchorRect,
    this.onSelected,
  });

  final Rect anchorRect;
  final void Function(RegenerateOption option)? onSelected;

  static const _options = RegenerateOption.values;
  static const double _itemHeight = 40;
  static const double _popupWidth = 160;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final bgColor = isDark ? const Color(0xFF2C2C2E) : Colors.white;
    final textColor = isDark ? const Color(0xFFEBEBF5) : const Color(0xFF1C1C1E);
    final dividerColor = isDark
        ? const Color(0xFF38383A)
        : const Color(0xFFE5E5EA);

    final popupHeight = _options.length * _itemHeight;
    final popupTop = anchorRect.top - popupHeight - 8;
    final popupLeft = anchorRect.right - _popupWidth;

    return Stack(
      children: [
        GestureDetector(
          onTap: () => Navigator.of(context).pop(),
          behavior: HitTestBehavior.translucent,
          child: const SizedBox.expand(),
        ),
        Positioned(
          left: popupLeft.clamp(8.0, MediaQuery.of(context).size.width - _popupWidth - 8),
          top: popupTop.clamp(8.0, MediaQuery.of(context).size.height - popupHeight - 8),
          child: Material(
            color: Colors.transparent,
            child: Container(
              width: _popupWidth,
              decoration: BoxDecoration(
                color: bgColor,
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: isDark ? 0.4 : 0.12),
                    blurRadius: 16,
                    offset: const Offset(0, -4),
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
                          height: 0.5,
                          margin: const EdgeInsets.symmetric(horizontal: 12),
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
          padding: const EdgeInsets.symmetric(horizontal: 14),
          child: Row(
            children: [
              Icon(option.icon, size: 16, color: textColor),
              const SizedBox(width: 10),
              Text(
                option.label,
                style: TextStyle(
                  fontSize: 14,
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
