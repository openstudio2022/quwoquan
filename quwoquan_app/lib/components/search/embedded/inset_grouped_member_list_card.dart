import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

/// 与转让/管理员页一致的分割线左侧缩进。
enum MemberListDividerInsetKind {
  /// 头像 + 与列表内边距对齐。
  navigate,
  /// 多选图标 + 头像。
  multiSelect,
}

double memberListDividerLeadingInset(MemberListDividerInsetKind kind) {
  switch (kind) {
    case MemberListDividerInsetKind.navigate:
      return SettingsSemanticConstants.blockHorizontalPadding +
          AppSpacing.largeButtonSize +
          AppSpacing.interGroupSm;
    case MemberListDividerInsetKind.multiSelect:
      return SettingsSemanticConstants.blockHorizontalPadding +
          AppSpacing.iconMedium +
          AppSpacing.interGroupSm +
          AppSpacing.largeButtonSize +
          AppSpacing.interGroupSm;
  }
}

/// 白（深模式深灰）卡片 + 圆角描边 + 行间分割线。
class InsetGroupedMemberListCard extends StatelessWidget {
  const InsetGroupedMemberListCard({
    super.key,
    required this.isDark,
    required this.dividerKind,
    required this.tileWidgets,
  });

  final bool isDark;
  final MemberListDividerInsetKind dividerKind;
  final List<Widget> tileWidgets;

  @override
  Widget build(BuildContext context) {
    final inset = memberListDividerLeadingInset(dividerKind);
    return Container(
      decoration: BoxDecoration(
        color: SettingsSemanticConstants.blockBackground(isDark),
        borderRadius: BorderRadius.circular(
          SettingsSemanticConstants.selectionCardBorderRadius,
        ),
        border: Border.all(
          color: SettingsSemanticConstants.blockBorderColor(isDark),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < tileWidgets.length; i++) ...[
            tileWidgets[i],
            if (i < tileWidgets.length - 1)
              Container(
                height: SettingsSemanticConstants.dividerThickness,
                margin: EdgeInsets.only(
                  left: inset,
                  right: SettingsSemanticConstants.blockHorizontalPadding,
                ),
                color: SettingsSemanticConstants.dividerColor(isDark),
              ),
          ],
        ],
      ),
    );
  }
}
