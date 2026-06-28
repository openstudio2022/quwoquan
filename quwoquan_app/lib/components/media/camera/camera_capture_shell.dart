import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/components/media/image/editor/icons/image_editor_semantic_icon.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 高保相机共享壳（图片 / 视频两种模式共用）。
///
/// 本文件只承载“共享框架”：强制深色 chrome、顶部栏几何、九宫格、点击对焦视觉、
/// 统一错误/权限态、底部文字动作与主按钮几何。模式相关的状态机、路由结果、
/// 录制/拍照行为留在 `camera_capture_page.dart`，避免视频模式复用拍照专用逻辑。
class CameraShellMetrics {
  const CameraShellMetrics._();

  static const double topBarHeight = 56;
  static const double primaryButtonOuterSize = 74;
  static const double primaryButtonInnerSize = 62;
  static const double focusRingSize = 68;
}

/// 强制深色 chrome + 状态栏样式，图片/视频/错误态统一入口。
Widget cameraForcedDarkChrome({
  required BuildContext context,
  required Color background,
  required Widget child,
}) {
  final theme = CupertinoTheme.of(context);
  final mediaQuery = MediaQuery.maybeOf(context);
  final darkChild = CupertinoTheme(
    data: theme.copyWith(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: background,
      barBackgroundColor: background,
    ),
    child: child,
  );
  return AnnotatedRegion<SystemUiOverlayStyle>(
    value: SystemUiOverlayStyle.light.copyWith(
      statusBarColor: background,
      systemNavigationBarColor: background,
      systemNavigationBarDividerColor: background,
    ),
    child: mediaQuery == null
        ? darkChild
        : MediaQuery(
            data: mediaQuery.copyWith(platformBrightness: Brightness.dark),
            child: darkChild,
          ),
  );
}

/// 共享顶部栏：左返回、居中标题、右侧动作槽（拍照=闪光灯 / 视频=灯光 / 占位）。
class CameraTopBar extends StatelessWidget {
  const CameraTopBar({
    super.key,
    required this.title,
    required this.onBack,
    this.trailing,
  });

  final String title;
  final VoidCallback onBack;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final primary = AppColorsFunctional.getColor(
      true,
      ColorType.foregroundPrimary,
    );
    return SizedBox(
      key: const ValueKey<String>('camera-top-bar'),
      height: CameraShellMetrics.topBarHeight,
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
        child: Row(
          children: [
            CameraRoundIconButton(
              key: const ValueKey<String>('camera-back-action'),
              icon: CupertinoIcons.chevron_back,
              label: UITextConstants.back,
              onTap: onBack,
            ),
            Expanded(
              child: Center(
                child: Text(
                  title,
                  style: TextStyle(
                    color: primary,
                    fontSize: AppTypography.iosBody,
                    fontWeight: AppTypography.semiBold,
                    decoration: TextDecoration.none,
                  ),
                ),
              ),
            ),
            trailing ??
                SizedBox.square(dimension: AppSpacing.minInteractiveSize),
          ],
        ),
      ),
    );
  }
}

class CameraRoundIconButton extends StatelessWidget {
  const CameraRoundIconButton({
    super.key,
    required this.icon,
    required this.label,
    required this.onTap,
    this.enabled = true,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: label,
      button: true,
      child: CupertinoButton(
        minimumSize: Size.square(AppSpacing.minInteractiveSize),
        padding: EdgeInsets.zero,
        onPressed: enabled ? onTap : null,
        child: Icon(
          icon,
          color: enabled
              ? AppColors.white
              : AppColors.white.withValues(alpha: 0.32),
          size: AppSpacing.iconMedium,
        ),
      ),
    );
  }
}

class CameraRuleOfThirdsGrid extends StatelessWidget {
  const CameraRuleOfThirdsGrid({super.key});

  @override
  Widget build(BuildContext context) {
    final lineColor = AppColors.white.withValues(alpha: 0.35);
    return IgnorePointer(
      child: Stack(
        children: [
          for (final fraction in const <double>[1 / 3, 2 / 3])
            Align(
              alignment: Alignment(fraction * 2 - 1, 0),
              child: Container(width: AppSpacing.hairline, color: lineColor),
            ),
          for (final fraction in const <double>[1 / 3, 2 / 3])
            Align(
              alignment: Alignment(0, fraction * 2 - 1),
              child: Container(height: AppSpacing.hairline, color: lineColor),
            ),
        ],
      ),
    );
  }
}

class CameraFocusRing extends StatelessWidget {
  const CameraFocusRing({super.key, required this.center});

  final Offset center;

  @override
  Widget build(BuildContext context) {
    const double focusSize = CameraShellMetrics.focusRingSize;
    return Positioned(
      left: center.dx - focusSize / 2,
      top: center.dy - focusSize / 2,
      child: IgnorePointer(
        child: Container(
          width: focusSize,
          height: focusSize,
          decoration: BoxDecoration(
            border: Border.all(
              color: AppColors.white.withValues(alpha: 0.92),
              width: AppSpacing.hairline * 3,
            ),
            borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          ),
          child: Center(
            child: Container(
              width: AppSpacing.intraGroupSm,
              height: AppSpacing.intraGroupSm,
              decoration: const BoxDecoration(
                color: AppColors.primaryColor,
                shape: BoxShape.circle,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// 共享底部文字动作（滤镜 / 翻转）。
class CameraBottomTextAction extends StatelessWidget {
  const CameraBottomTextAction({
    super.key,
    required this.icon,
    required this.label,
    required this.onTap,
    this.semanticIconKey,
    this.selected = false,
    this.enabled = true,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final String? semanticIconKey;
  final bool selected;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final Color color;
    if (!enabled) {
      color = AppColors.white.withValues(alpha: 0.32);
    } else if (selected) {
      color = AppColors.primaryColor;
    } else {
      color = AppColors.white;
    }
    final Color labelColor;
    if (!enabled) {
      labelColor = AppColors.white.withValues(alpha: 0.32);
    } else if (selected) {
      labelColor = AppColors.primaryColor;
    } else {
      labelColor = AppColors.white.withValues(alpha: 0.86);
    }
    return CupertinoButton(
      minimumSize: Size.square(AppSpacing.minInteractiveSize),
      padding: EdgeInsets.zero,
      onPressed: enabled ? onTap : null,
      child: FittedBox(
        fit: BoxFit.scaleDown,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (semanticIconKey == null)
              Icon(icon, color: color, size: AppSpacing.iconMedium)
            else
              ImageEditorSemanticIcon(
                iconKey: semanticIconKey!,
                color: color,
                size: AppSpacing.iconMedium,
              ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              label,
              style: TextStyle(
                color: labelColor,
                fontSize: AppTypography.iosCaption1,
                fontWeight: AppTypography.semiBold,
                decoration: TextDecoration.none,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 拍照模式白色快门。
class CameraShutterButton extends StatelessWidget {
  const CameraShutterButton({super.key, required this.busy, required this.onTap});

  final bool busy;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      key: const ValueKey<String>('camera-capture-action'),
      onTap: busy ? null : onTap,
      child: Container(
        width: CameraShellMetrics.primaryButtonOuterSize,
        height: CameraShellMetrics.primaryButtonOuterSize,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(
            color: AppColors.white,
            width: AppSpacing.hairline * 5,
          ),
        ),
        child: Center(
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 120),
            width: busy
                ? AppSpacing.buttonHeight
                : CameraShellMetrics.primaryButtonInnerSize,
            height: busy
                ? AppSpacing.buttonHeight
                : CameraShellMetrics.primaryButtonInnerSize,
            decoration: const BoxDecoration(
              color: AppColors.white,
              shape: BoxShape.circle,
            ),
          ),
        ),
      ),
    );
  }
}

/// 视频摄像模式品牌蓝录像/停止主按钮。
///
/// idle：白环 + 品牌蓝实心圆；recording：白环 + 品牌蓝圆角方块（停止）。
class CameraRecordButton extends StatelessWidget {
  const CameraRecordButton({
    super.key,
    required this.recording,
    required this.busy,
    required this.onTap,
  });

  final bool recording;
  final bool busy;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final double innerSize = recording
        ? AppSpacing.buttonHeightSm
        : CameraShellMetrics.primaryButtonInnerSize;
    return Semantics(
      label: recording
          ? UITextConstants.cameraVideoStop
          : UITextConstants.cameraVideoRecord,
      button: true,
      child: GestureDetector(
        key: const ValueKey<String>('camera-record-action'),
        onTap: busy ? null : onTap,
        child: Container(
          width: CameraShellMetrics.primaryButtonOuterSize,
          height: CameraShellMetrics.primaryButtonOuterSize,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(
              color: AppColors.white,
              width: AppSpacing.hairline * 5,
            ),
          ),
          child: Center(
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 160),
              width: innerSize,
              height: innerSize,
              decoration: BoxDecoration(
                color: AppColors.primaryColor,
                // 始终矩形 + 圆角，避免 circle<->rectangle 形变中间态非法。
                borderRadius: BorderRadius.circular(
                  recording ? AppSpacing.borderRadius : innerSize / 2,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// 统一深色错误/权限态（相机不可用、相机权限被拒）。
class CameraBlockingState extends StatelessWidget {
  const CameraBlockingState({
    super.key,
    required this.semantic,
    required this.onAction,
  });

  final UiErrorSemantic semantic;
  final ValueChanged<UiErrorAction> onAction;

  @override
  Widget build(BuildContext context) {
    const primary = AppColors.white;
    final secondary = AppColorsFunctional.getColor(
      true,
      ColorType.foregroundSecondary,
    );
    return ColoredBox(
      color: AppColors.iosGroupedBackgroundDark,
      child: Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerLg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                CupertinoIcons.camera,
                color: secondary,
                size: AppSpacing.iconLarge + AppSpacing.iconMedium,
              ),
              SizedBox(height: AppSpacing.interGroupSm),
              Text(
                semantic.title,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: primary,
                  fontSize: AppTypography.iosTitle3,
                  fontWeight: AppTypography.semiBold,
                  decoration: TextDecoration.none,
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupSm),
              Text(
                semantic.message,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: secondary,
                  fontSize: AppTypography.iosBody,
                  decoration: TextDecoration.none,
                ),
              ),
              if ((semantic.secondaryMessage ?? '').trim().isNotEmpty) ...[
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  semantic.secondaryMessage!.trim(),
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: AppColorsFunctional.getColor(
                      true,
                      ColorType.foregroundSecondary,
                    ),
                    fontSize: AppTypography.iosFootnote,
                    decoration: TextDecoration.none,
                  ),
                ),
              ],
              SizedBox(height: AppSpacing.interGroupMd),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  if (semantic.secondaryAction != null)
                    _CameraErrorActionButton(
                      action: semantic.secondaryAction!,
                      primary: false,
                      onAction: onAction,
                    ),
                  if (semantic.secondaryAction != null &&
                      semantic.primaryAction != null)
                    SizedBox(width: AppSpacing.containerSm),
                  if (semantic.primaryAction != null)
                    _CameraErrorActionButton(
                      action: semantic.primaryAction!,
                      primary: true,
                      onAction: onAction,
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CameraErrorActionButton extends StatelessWidget {
  const _CameraErrorActionButton({
    required this.action,
    required this.primary,
    required this.onAction,
  });

  final UiErrorAction action;
  final bool primary;
  final ValueChanged<UiErrorAction> onAction;

  @override
  Widget build(BuildContext context) {
    final fill = primary
        ? AppColors.iosTintedFill(context)
        : AppColors.iosSecondaryFill(context);
    final foreground = primary
        ? AppColors.iosAccent(context)
        : AppColorsFunctional.getColor(true, ColorType.foregroundSecondary);
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.intraGroupSm,
      ),
      borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
      color: fill,
      onPressed: () => onAction(action),
      child: Text(
        action.label,
        style: TextStyle(
          color: foreground,
          fontSize: AppTypography.iosSubheadline,
          fontWeight: AppTypography.semiBold,
        ),
      ),
    );
  }
}
