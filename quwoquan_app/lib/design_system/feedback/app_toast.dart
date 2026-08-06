import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/scheduler.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

/// 统一的 iOS 风格 Toast 提示
class AppToast {
  static OverlayEntry? _currentEntry;
  static Timer? _timer;

  /// Shows a toast.
  ///
  /// Insertion is deferred until after the current frame when the scheduler is
  /// mid-build, avoiding Riverpod `markNeedsBuild during build` when Overlay /
  /// TickerMode resumes provider watchers.
  static void show(
    BuildContext context,
    String message, {
    Duration duration = const Duration(seconds: 3),
    String? actionLabel,
    VoidCallback? onAction,
  }) {
    final overlay = Overlay.maybeOf(context);
    if (overlay == null) {
      return;
    }
    final messengerContext = context;

    void insert() {
      if (!messengerContext.mounted) {
        return;
      }
      final liveOverlay = Overlay.maybeOf(messengerContext);
      if (liveOverlay == null) {
        return;
      }
      _currentEntry?.remove();
      _timer?.cancel();
      _currentEntry = OverlayEntry(
        builder: (context) => _ToastWidget(
          message: message,
          actionLabel: actionLabel,
          onAction: onAction,
        ),
      );
      liveOverlay.insert(_currentEntry!);
      _timer = Timer(duration, () {
        _currentEntry?.remove();
        _currentEntry = null;
        _timer = null;
      });
    }

    final phase = SchedulerBinding.instance.schedulerPhase;
    if (phase == SchedulerPhase.idle ||
        phase == SchedulerPhase.postFrameCallbacks) {
      insert();
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) => insert());
  }

  static void dismiss() {
    _timer?.cancel();
    _timer = null;
    _currentEntry?.remove();
    _currentEntry = null;
  }
}

class _ToastWidget extends StatelessWidget {
  const _ToastWidget({required this.message, this.actionLabel, this.onAction});

  final String message;
  final String? actionLabel;
  final VoidCallback? onAction;

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
            color: isDark
                ? CupertinoColors.systemGrey6.darkColor.withValues(alpha: 0.9)
                : CupertinoColors.black.withValues(alpha: 0.9),
            borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          ),
          child: DefaultTextStyle(
            style: TextStyle(
              color: CupertinoColors.white,
              fontSize: AppTypography.base,
              fontWeight: FontWeight.w400,
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Flexible(child: Text(message, textAlign: TextAlign.center)),
                if (actionLabel != null && onAction != null) ...<Widget>[
                  SizedBox(width: AppSpacing.intraGroupSm),
                  CupertinoButton(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerSm,
                    ),
                    minimumSize: Size.zero,
                    onPressed: () {
                      AppToast.dismiss();
                      onAction?.call();
                    },
                    child: Text(
                      actionLabel!,
                      style: TextStyle(
                        color: CupertinoColors.activeBlue,
                        fontSize: AppTypography.base,
                        fontWeight: AppTypography.semiBold,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
