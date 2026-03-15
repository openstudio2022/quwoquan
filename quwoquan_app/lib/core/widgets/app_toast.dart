import 'dart:async';
import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

/// 统一的 iOS 风格 Toast 提示
class AppToast {
  static OverlayEntry? _currentEntry;
  static Timer? _timer;

  static void show(BuildContext context, String message, {Duration duration = const Duration(seconds: 3)}) {
    _currentEntry?.remove();
    _timer?.cancel();

    final overlay = Overlay.of(context);
    _currentEntry = OverlayEntry(
      builder: (context) => _ToastWidget(message: message),
    );

    overlay.insert(_currentEntry!);

    _timer = Timer(duration, () {
      _currentEntry?.remove();
      _currentEntry = null;
    });
  }
}

class _ToastWidget extends StatelessWidget {
  const _ToastWidget({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    
    return Positioned(
      bottom: MediaQuery.of(context).viewInsets.bottom + 100,
      left: AppSpacing.containerMd,
      right: AppSpacing.containerMd,
      child: Center(
        child: Container(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerMd,
            vertical: AppSpacing.containerSm,
          ),
          decoration: BoxDecoration(
            color: isDark ? CupertinoColors.systemGrey6.darkColor.withValues(alpha: 0.9) : CupertinoColors.black.withValues(alpha: 0.9),
            borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          ),
          child: DefaultTextStyle(
            style: TextStyle(
              color: CupertinoColors.white,
              fontSize: AppTypography.base,
              fontWeight: FontWeight.w400,
            ),
            child: Text(
              message,
              textAlign: TextAlign.center,
            ),
          ),
        ),
      ),
    );
  }
}
