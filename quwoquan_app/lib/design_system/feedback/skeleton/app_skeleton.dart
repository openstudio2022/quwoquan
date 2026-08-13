import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';

/// 骨架屏统一 primitives：块 / 行 / 圆位 + 唯一 shimmer 脉冲包装。
///
/// 与 `AppPageErrorState`（错误态）、`AppEmptyState`（空态）、
/// `AppRequestFeedback`（等待文案）同属反馈层积木；页面只声明骨架布局形状，
/// 不得自实现 shimmer、脉冲或第二套占位动画。
///
/// - shimmer 节奏与占位视觉全站唯一（[AppSkeletonShimmer] 语义常量）；
/// - `MediaQuery.disableAnimations` 为真时骨架静止；
/// - 骨架内容经 [ExcludeSemantics] 对辅助技术不可见，等待语义由页面级
///   `AppRequestFeedback` 或加载 semantics 承载。
class AppSkeletonShimmer extends StatefulWidget {
  const AppSkeletonShimmer({super.key, required this.child});

  /// 脉冲最低透明度（谷值）。
  static const double minOpacity = 0.35;

  /// 脉冲最高透明度（峰值）；静止态固定在该值。
  static const double maxOpacity = 0.75;

  /// 单程脉冲时长（往复 repeat）。
  static const Duration pulseDuration = Duration(milliseconds: 900);

  final Widget child;

  @override
  State<AppSkeletonShimmer> createState() => _AppSkeletonShimmerState();
}

class _AppSkeletonShimmerState extends State<AppSkeletonShimmer>
    with SingleTickerProviderStateMixin {
  AnimationController? _pulse;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    if (reduceMotion) {
      _pulse?.dispose();
      _pulse = null;
      return;
    }
    _pulse ??= AnimationController(
      vsync: this,
      duration: AppSkeletonShimmer.pulseDuration,
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulse?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final pulse = _pulse;
    final excluded = ExcludeSemantics(child: widget.child);
    if (pulse == null) {
      return Opacity(
        opacity: AppSkeletonShimmer.maxOpacity,
        child: excluded,
      );
    }
    return AnimatedBuilder(
      animation: pulse,
      builder: (context, child) {
        final opacity =
            AppSkeletonShimmer.minOpacity +
            (AppSkeletonShimmer.maxOpacity - AppSkeletonShimmer.minOpacity) *
                pulse.value;
        return Opacity(opacity: opacity, child: child);
      },
      child: excluded,
    );
  }
}

/// 圆角矩形占位块（媒体位、卡片位）。
class AppSkeletonBlock extends StatelessWidget {
  const AppSkeletonBlock({
    super.key,
    this.width,
    this.height,
    this.borderRadius,
  });

  final double? width;
  final double? height;
  final BorderRadius? borderRadius;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: AppColors.iosFill(context),
        borderRadius:
            borderRadius ?? BorderRadius.circular(AppSpacing.smallBorderRadius),
      ),
    );
  }
}

/// 文字行占位。
class AppSkeletonLine extends StatelessWidget {
  const AppSkeletonLine({super.key, this.width, this.height = AppSpacing.ten});

  final double? width;
  final double height;

  @override
  Widget build(BuildContext context) {
    return AppSkeletonBlock(width: width, height: height);
  }
}

/// 圆形占位（头像位）。
class AppSkeletonCircle extends StatelessWidget {
  const AppSkeletonCircle({super.key, required this.size});

  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: AppColors.iosFill(context),
        shape: BoxShape.circle,
      ),
    );
  }
}
