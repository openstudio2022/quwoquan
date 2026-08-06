import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/discovery_feed_text_constants.dart';

/// 槽④ 交集生命周期弱标（canonical 交集设计 · A–E 横切复用）。
///
/// 真相源是云侧 `lifecycleState` 枚举（`new/strengthened/stable/weakened/reactivated`）。
/// 端只负责把状态弱化为「红点 / 增强 / 重新活跃」标识：
/// - `new`：红色弱标（紧凑面也允许仅红点）。
/// - `strengthened`：弱 accent 标，可叠 `+N`（来自 `strengthDelta`）。
/// - `reactivated`：弱 accent 标。
/// - `stable`/`weakened`/未知：不渲染（返回零尺寸）。
///
/// 强约束（§21.3 / G2）：弱标**不进结论句**、不变蓝主色、不堆叠成第二句。
class IntersectionLifecycleBadge extends StatelessWidget {
  const IntersectionLifecycleBadge({
    super.key,
    required this.lifecycleState,
    this.strengthDelta = 0,
    this.dotOnlyForNew = false,
  });

  final String lifecycleState;
  final int strengthDelta;

  /// 紧凑面（feed/spotlight/记录卡）下 `new` 仅渲染红点、不带文字。
  final bool dotOnlyForNew;

  bool get _isNew => lifecycleState.trim() == 'new';
  bool get _isStrengthened => lifecycleState.trim() == 'strengthened';
  bool get _isReactivated => lifecycleState.trim() == 'reactivated';

  @override
  Widget build(BuildContext context) {
    if (!_isNew && !_isStrengthened && !_isReactivated) {
      return const SizedBox.shrink();
    }

    if (_isNew && dotOnlyForNew) {
      return Container(
        width: AppSpacing.intraGroupSm,
        height: AppSpacing.intraGroupSm,
        decoration: BoxDecoration(
          color: AppColors.iosDestructive(context),
          shape: BoxShape.circle,
        ),
      );
    }

    final Color fg;
    final Color bg;
    if (_isNew) {
      fg = AppColors.iosDestructive(context);
      bg = fg.withValues(alpha: 0.12);
    } else {
      fg = AppColors.iosAccent(context);
      bg = AppColors.iosSecondaryFill(context);
    }

    var label = DiscoveryFeedText.intersectionLifecycleLabel(lifecycleState);
    if (label.isEmpty) {
      return const SizedBox.shrink();
    }
    if (_isStrengthened && strengthDelta > 0) {
      label = '$label +$strengthDelta';
    }

    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerXs,
        vertical: AppSpacing.intraGroupXs / 2,
      ),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: AppTypography.iosCaption2,
          fontWeight: AppTypography.semiBold,
          color: fg,
          letterSpacing: -0.02,
        ),
      ),
    );
  }
}
