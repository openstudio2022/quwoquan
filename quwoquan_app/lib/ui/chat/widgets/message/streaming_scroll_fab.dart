import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

/// Circular FAB with a progress ring and down-arrow, shown during streaming
/// when content has scrolled past the viewport bottom.
///
/// Tapping it scrolls to the latest content.  The progress ring completes
/// as the stream fills up (indeterminate when total is unknown).
class StreamingScrollFab extends StatelessWidget {
  const StreamingScrollFab({
    super.key,
    this.progress,
    required this.onTap,
    this.size = 40,
  });

  /// 0..1 determinate progress; null → indeterminate spinner.
  final double? progress;
  final VoidCallback onTap;
  final double size;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final bgColor = isDark ? AppColors.iosSystemSurfaceDark : Colors.white;
    final accentColor = isDark
        ? AppColors.iosAccentDark
        : AppColors.iosAccentLight;

    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          color: bgColor,
          shape: BoxShape.circle,
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: isDark ? 0.3 : 0.1),
              blurRadius: 8,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Stack(
          alignment: Alignment.center,
          children: [
            SizedBox(
              width: size - 6,
              height: size - 6,
              child: progress == null
                  ? const CupertinoActivityIndicator()
                  : CircularProgressIndicator(
                      value: progress,
                      strokeWidth: 2.5,
                      backgroundColor: accentColor.withValues(alpha: 0.15),
                      valueColor: AlwaysStoppedAnimation<Color>(accentColor),
                    ),
            ),
            Icon(
              CupertinoIcons.chevron_down,
              size: AppSpacing.iconSmall,
              color: accentColor,
            ),
          ],
        ),
      ),
    );
  }
}
