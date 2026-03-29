import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Colors;
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/core/constants/search_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

/// 已选成员头像与搜索框同处一个「搜索框」视觉容器内；头像可换行；点击头像取消选中。
///
/// 使用按行排版而非 [Wrap]+[CupertinoTextField]，避免输入框按「整行 maxWidth」参与排版而误换行。
class EmbeddedMemberSearchBarWithChips extends StatelessWidget {
  const EmbeddedMemberSearchBarWithChips({
    super.key,
    required this.isDark,
    required this.controller,
    required this.placeholder,
    required this.onChanged,
    required this.selectedMembers,
    required this.onSelectedMemberTap,
    this.focusNode,
  });

  final bool isDark;
  final TextEditingController controller;
  final String placeholder;
  final ValueChanged<String> onChanged;
  final List<Map<String, dynamic>> selectedMembers;

  /// 点击已选头像时回调（通常为 `userId`，用于从选中集合移除）。
  final ValueChanged<String> onSelectedMemberTap;
  final FocusNode? focusNode;

  @override
  Widget build(BuildContext context) {
    final chipSize = SearchSemanticConstants.embeddedMemberSearchChipAvatarSize;
    final rowMinH = SearchSemanticConstants.embeddedMemberSearchChipsRowMinHeight;

    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.sm,
        AppSpacing.containerMd,
        AppSpacing.sm,
      ),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: SearchSemanticConstants.backgroundColor(context),
          borderRadius: BorderRadius.circular(
            SearchSemanticConstants.fieldBorderRadius,
          ),
          border: Border.all(
            color: SearchSemanticConstants.borderColor(context),
            width: AppSpacing.hairline,
          ),
          boxShadow: SearchSemanticConstants.shadows(context),
        ),
        child: Padding(
          padding: EdgeInsets.fromLTRB(
            AppSpacing.sm,
            AppSpacing.xs,
            AppSpacing.sm,
            AppSpacing.xs,
          ),
          child: LayoutBuilder(
            builder: (context, constraints) {
              final maxW = constraints.maxWidth;
              return AnimatedSize(
                duration:
                    SearchSemanticConstants.embeddedMemberSearchChipsLayoutDuration,
                curve:
                    SearchSemanticConstants.embeddedMemberSearchChipsLayoutCurve,
                alignment: Alignment.topLeft,
                child: _ChipsInlineSearchLayout(
                  maxWidth: maxW,
                  chipSize: chipSize,
                  rowMinHeight: rowMinH,
                  isDark: isDark,
                  selectedMembers: selectedMembers,
                  onSelectedMemberTap: onSelectedMemberTap,
                  input: CupertinoTheme(
                    data: CupertinoTheme.of(context).copyWith(
                      primaryColor: AppColors.iosAccent(context),
                    ),
                    child: CupertinoTextField(
                      controller: controller,
                      focusNode: focusNode,
                      placeholder: placeholder,
                      onChanged: onChanged,
                      autocorrect: false,
                      style: SearchSemanticConstants.inputTextStyle(context),
                      placeholderStyle: SearchSemanticConstants
                          .embeddedMemberSearchChipsPlaceholderStyle(context),
                      padding: EdgeInsets.fromLTRB(
                        AppSpacing.two,
                        AppSpacing.sm,
                        AppSpacing.sm,
                        AppSpacing.sm,
                      ),
                      decoration: const BoxDecoration(
                        color: Colors.transparent,
                      ),
                      cursorColor: AppColors.iosAccent(context),
                      clearButtonMode: OverlayVisibilityMode.never,
                    ),
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}

/// 按行累加头像宽度；输入框仅占用当前行剩余宽度，占满一行时才单独换行。
class _ChipsInlineSearchLayout extends StatelessWidget {
  const _ChipsInlineSearchLayout({
    required this.maxWidth,
    required this.chipSize,
    required this.rowMinHeight,
    required this.isDark,
    required this.selectedMembers,
    required this.onSelectedMemberTap,
    required this.input,
  });

  final double maxWidth;
  final double chipSize;
  final double rowMinHeight;
  final bool isDark;
  final List<Map<String, dynamic>> selectedMembers;
  final ValueChanged<String> onSelectedMemberTap;
  final Widget input;

  static double _chipOuterWidth(double chipSize) =>
      chipSize + 2 * AppSpacing.one;

  @override
  Widget build(BuildContext context) {
    final gap = AppSpacing.xs;
    final chipOuterW = _chipOuterWidth(chipSize);
    final inputMin =
        SearchSemanticConstants.embeddedMemberSearchChipsInlineInputMinWidth;

    final rows = <List<Widget>>[];
    var line = <Widget>[];
    var usedOnLine = 0.0;

    void commitLine() {
      if (line.isNotEmpty) {
        rows.add(List<Widget>.from(line));
        line = <Widget>[];
        usedOnLine = 0;
      }
    }

    for (final m in selectedMembers) {
      final need = (line.isEmpty ? 0.0 : gap) + chipOuterW;
      if (usedOnLine + need > maxWidth && line.isNotEmpty) {
        commitLine();
      }
      line.add(
        _MemberChipAvatar(
          member: m,
          size: chipSize,
          isDark: isDark,
          onTap: () {
            final id = m['userId'] as String? ?? '';
            if (id.isNotEmpty) {
              onSelectedMemberTap(id);
            }
          },
        ),
      );
      usedOnLine += need;
    }

    final gapBeforeInput = line.isEmpty ? 0.0 : gap;
    final remainingOnLine = maxWidth - usedOnLine - gapBeforeInput;

    if (remainingOnLine >= inputMin) {
      line.add(
        SizedBox(
          width: remainingOnLine,
          height: rowMinHeight,
          child: input,
        ),
      );
    } else {
      commitLine();
      line.add(
        SizedBox(
          width: maxWidth,
          height: rowMinHeight,
          child: input,
        ),
      );
    }
    commitLine();

    final runSpacing = AppSpacing.two;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 0; i < rows.length; i++)
          Padding(
            padding: EdgeInsets.only(
              bottom: i < rows.length - 1 ? runSpacing : 0,
            ),
            child: _RowWithGap(gap: gap, children: rows[i]),
          ),
      ],
    );
  }
}

class _RowWithGap extends StatelessWidget {
  const _RowWithGap({required this.gap, required this.children});

  final double gap;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    if (children.isEmpty) {
      return const SizedBox.shrink();
    }
    final spaced = <Widget>[];
    for (var j = 0; j < children.length; j++) {
      if (j > 0) {
        spaced.add(SizedBox(width: gap));
      }
      spaced.add(children[j]);
    }
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      mainAxisSize: MainAxisSize.min,
      children: spaced,
    );
  }
}

class _MemberChipAvatar extends StatelessWidget {
  const _MemberChipAvatar({
    required this.member,
    required this.size,
    required this.isDark,
    required this.onTap,
  });

  final Map<String, dynamic> member;
  final double size;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final avatar =
        member['avatarUrl'] as String? ?? member['avatar'] as String? ?? '';
    final name =
        member['displayName'] as String? ?? member['name'] as String? ?? '';
    final userId = member['userId'] as String? ?? '';

    return CupertinoButton(
      padding: EdgeInsets.all(AppSpacing.one),
      minimumSize: Size.zero,
      onPressed: onTap,
      child: RoundedSquareAvatar(
        key: ValueKey<String>('chip_$userId'),
        size: size,
        imageUrl: avatar,
        name: name,
        backgroundColor: SettingsSemanticConstants.blockBackground(isDark),
      ),
    );
  }
}
