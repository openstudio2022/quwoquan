import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/components/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

/// 单个操作按钮描述（主/次/扩展通用）。
///
/// 各主页主次动作不同（实体=关注/发记录，圈子=加入圈子/进入讨论，
/// 用户=管理分身/编辑/关注/私信），但都映射为一致的 [ProfileIosActionButton]，
/// 允许通过 [style] 与显式配色覆盖做样式扩展。
class ObjectAction {
  const ObjectAction({
    required this.label,
    required this.style,
    this.icon,
    this.onPressed,
    this.backgroundColor,
    this.foregroundColor,
    this.borderColor,
    this.labelFontWeight,
  });

  final String label;
  final ProfileIosActionStyle style;
  final IconData? icon;

  /// 为空表示禁用态（如「已加入」「待审核」）。
  final VoidCallback? onPressed;

  final Color? backgroundColor;
  final Color? foregroundColor;
  final Color? borderColor;
  final FontWeight? labelFontWeight;
}

/// 全宽参数化操作栏（对象/圈子/用户主页共享）。
///
/// 单一真相源：合并 `ProfileActionBar` 行渲染、实体 `_HomepageActionBar`、
/// 圈子 `CircleActionBar`；每项等分 [Expanded]，项间 [AppSpacing.sm] 间隔。
class ObjectActionBar extends StatelessWidget {
  const ObjectActionBar({super.key, required this.actions});

  final List<ObjectAction> actions;

  @override
  Widget build(BuildContext context) {
    final usable = actions
        .where((action) => action.label.trim().isNotEmpty)
        .toList(growable: false);
    if (usable.isEmpty) {
      return const SizedBox.shrink();
    }
    return Row(
      children: <Widget>[
        for (var i = 0; i < usable.length; i += 1) ...<Widget>[
          Expanded(child: _buildButton(usable[i])),
          if (i != usable.length - 1) SizedBox(width: AppSpacing.sm),
        ],
      ],
    );
  }

  Widget _buildButton(ObjectAction action) {
    return ProfileIosActionButton(
      label: action.label,
      icon: action.icon,
      onPressed: action.onPressed,
      style: action.style,
      backgroundColor: action.backgroundColor,
      foregroundColor: action.foregroundColor,
      borderColor: action.borderColor,
      labelFontWeight: action.labelFontWeight ?? AppTypography.regular,
    );
  }
}
