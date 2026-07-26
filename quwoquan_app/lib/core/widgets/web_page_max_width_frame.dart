import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/platform/platform_providers.dart';

/// 宽屏 Web 认证态页面（消息 / 我的 / 设置 / 更多）统一的最大宽度容器。
///
/// 仅在 [PlatformCapabilities.wideScreenLayout] 且窗口达到宽屏断点时生效：
/// 中间内容区固定 [maxWidth] 并居中，左右用 [sideColor] 填充区分阅读区；
/// 否则原样透传（移动端 / 窄屏不改变任何布局与背景）。
///
/// 单一抽象：所有需要桌面最大宽度的认证态页面都复用本组件，避免每页各自
/// 拼 `ConstrainedBox` 造成第二套尺寸来源。
class WebPageMaxWidthFrame extends ConsumerWidget {
  const WebPageMaxWidthFrame({
    super.key,
    required this.child,
    this.maxWidth = AppSpacing.webPageContentMaxWidth,
    this.sideColor,
    this.contentColor,
  });

  final Widget child;

  /// 中间内容区最大宽度。
  final double maxWidth;

  /// 左右两侧填充色；为空时不绘制独立侧栏背景（沿用上层背景）。
  final Color? sideColor;

  /// 中间内容区背景色；为空时沿用 child 自身背景（如聊天背景层）。
  final Color? contentColor;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final wide =
        ref.watch(platformCapabilitiesProvider).wideScreenLayout &&
        AppSpacing.isWideLayout(context);
    if (!wide) {
      return child;
    }
    final content = contentColor != null
        ? ColoredBox(color: contentColor!, child: child)
        : child;
    final framed = Center(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxWidth),
        child: content,
      ),
    );
    final effectiveSide = sideColor;
    if (effectiveSide == null) {
      return framed;
    }
    return ColoredBox(color: effectiveSide, child: framed);
  }
}
