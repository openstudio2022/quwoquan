import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/scheduler.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';

/// 统一的 iOS 风格 Toast 提示。
///
/// 轻提示按 [UiErrorTone] 区分性质：错误/警示 tone 在胶囊内前置 token 色
/// 圆点（非图标，保持低打扰），让失败反馈在滚动中、单手弱注意场景下可辨识；
/// 中性提示保持纯文字胶囊。文案仍必须来自统一恢复语义，禁止失败字面量。
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
    UiErrorTone tone = UiErrorTone.neutral,
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
          tone: tone,
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

  /// 错误轻提示：消费 [UiErrorSemantic] 的文案与 tone。
  ///
  /// semantic 为中性 tone 时仍以警示呈现——调用方选择本入口即声明这是一次
  /// 失败反馈，不得与成功提示视觉混同。
  static void showError(
    BuildContext context,
    UiErrorSemantic semantic, {
    Duration duration = const Duration(seconds: 3),
  }) {
    final tone = semantic.tone == UiErrorTone.neutral
        ? UiErrorTone.caution
        : semantic.tone;
    show(context, semantic.message, duration: duration, tone: tone);
  }

  static void dismiss() {
    _timer?.cancel();
    _timer = null;
    _currentEntry?.remove();
    _currentEntry = null;
  }
}

class _ToastWidget extends StatelessWidget {
  const _ToastWidget({
    required this.message,
    this.actionLabel,
    this.onAction,
    this.tone = UiErrorTone.neutral,
  });

  final String message;
  final String? actionLabel;
  final VoidCallback? onAction;
  final UiErrorTone tone;

  /// tone 强调圆点色：toast 底恒为深色，取深色模式前景保证 ≥3:1 非文本对比。
  Color? _toneAccent() {
    return switch (tone) {
      UiErrorTone.critical => AppColors.errorForegroundDark,
      UiErrorTone.caution => AppColors.warning,
      UiErrorTone.info || UiErrorTone.neutral => null,
    };
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final accent = _toneAccent();

    return Positioned(
      bottom: MediaQuery.of(context).viewInsets.bottom + 100,
      left: AppSpacing.containerMd,
      right: AppSpacing.containerMd,
      child: Center(
        child: Semantics(
          container: true,
          liveRegion: true,
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
                  if (accent != null) ...<Widget>[
                    Container(
                      key: const ValueKey<String>('app-toast-tone-dot'),
                      width: AppSpacing.ten,
                      height: AppSpacing.ten,
                      decoration: BoxDecoration(
                        color: accent,
                        shape: BoxShape.circle,
                      ),
                    ),
                    SizedBox(width: AppSpacing.intraGroupSm),
                  ],
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
      ),
    );
  }
}
