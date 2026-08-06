import 'package:flutter/cupertino.dart';

/// 声明当前页面内容被外层固定 chrome 遮挡的区域。
///
/// 例如主壳底部导航使用覆盖式布局，子页面仍获得完整高度；终态必须从可见
/// 内容区排除该遮挡量，不能把导航下方的区域计入视觉居中。
class AppViewportObstructionScope extends InheritedWidget {
  const AppViewportObstructionScope({
    super.key,
    required this.obstruction,
    required super.child,
  });

  final EdgeInsets obstruction;

  static EdgeInsets of(BuildContext context) {
    return context
            .dependOnInheritedWidgetOfExactType<AppViewportObstructionScope>()
            ?.obstruction ??
        EdgeInsets.zero;
  }

  @override
  bool updateShouldNotify(AppViewportObstructionScope oldWidget) {
    return obstruction != oldWidget.obstruction;
  }
}

/// 在真实可见视口内居中错误、空内容等页面终态。
///
/// [padding] 是终态自身留白；外层固定 chrome 的遮挡量由
/// [AppViewportObstructionScope] 统一叠加。内容过高时仍可滚动，避免动态字体
/// 或小屏设备裁切恢复动作。
class AppTerminalViewport extends StatelessWidget {
  const AppTerminalViewport({
    super.key,
    required this.child,
    required this.padding,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final direction = Directionality.of(context);
    final basePadding = padding.resolve(direction);
    final obstruction = AppViewportObstructionScope.of(context);
    final effectivePadding = EdgeInsets.fromLTRB(
      basePadding.left + obstruction.left,
      basePadding.top + obstruction.top,
      basePadding.right + obstruction.right,
      basePadding.bottom + obstruction.bottom,
    );
    return LayoutBuilder(
      builder: (context, constraints) {
        final height = constraints.hasBoundedHeight
            ? constraints.maxHeight
            : MediaQuery.sizeOf(context).height;
        final availableHeight = height - effectivePadding.vertical;
        return SizedBox(
          width: double.infinity,
          height: height,
          child: SingleChildScrollView(
            physics: const BouncingScrollPhysics(),
            padding: effectivePadding,
            child: ConstrainedBox(
              constraints: BoxConstraints(
                minHeight: availableHeight > 0 ? availableHeight : 0,
              ),
              child: Center(child: child),
            ),
          ),
        );
      },
    );
  }
}
