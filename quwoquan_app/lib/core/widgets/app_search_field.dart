import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/constants/search_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

/// 全局统一的 iOS 搜索输入。
///
/// 保留 `CupertinoSearchTextField` 的原生交互与测试可见性，同时统一
/// 占位字、上下留白、表面层级、描边和细微阴影。
class AppSearchField extends StatelessWidget {
  const AppSearchField({
    super.key,
    this.controller,
    this.focusNode,
    this.placeholder = '',
    this.onChanged,
    this.onSubmitted,
    this.onSuffixTap,
    this.autofocus = false,
    this.autocorrect = false,
    this.enabled = true,
    this.elevated = true,
    this.style,
    this.placeholderStyle,
    this.backgroundColor,
    this.itemColor,
    this.itemSize,
    this.padding,
    this.borderRadius,
    this.prefixIcon,
    this.restorationId,
  });

  final TextEditingController? controller;
  final FocusNode? focusNode;
  final String placeholder;
  final ValueChanged<String>? onChanged;
  final ValueChanged<String>? onSubmitted;
  final VoidCallback? onSuffixTap;
  final bool autofocus;
  final bool autocorrect;
  final bool enabled;
  final bool elevated;
  final TextStyle? style;
  final TextStyle? placeholderStyle;
  final Color? backgroundColor;
  final Color? itemColor;
  final double? itemSize;
  final EdgeInsetsGeometry? padding;
  final BorderRadius? borderRadius;
  final Icon? prefixIcon;
  final String? restorationId;

  @override
  Widget build(BuildContext context) {
    final resolvedRadius =
        borderRadius ??
        BorderRadius.circular(SearchSemanticConstants.fieldBorderRadius);
    final resolvedPadding =
        padding ?? SearchSemanticConstants.fieldContentPadding;
    final resolvedItemColor =
        itemColor ?? SearchSemanticConstants.iconColor(context);
    final resolvedItemSize = itemSize ?? SearchSemanticConstants.fieldIconSize;
    final resolvedStyle =
        style ?? SearchSemanticConstants.inputTextStyle(context);
    final resolvedPlaceholderStyle =
        placeholderStyle ??
        SearchSemanticConstants.placeholderTextStyle(context);
    final resolvedBackground =
        backgroundColor ?? SearchSemanticConstants.backgroundColor(context);
    final resolvedShadows = elevated
        ? SearchSemanticConstants.shadows(context)
        : const <BoxShadow>[];

    return DecoratedBox(
      decoration: BoxDecoration(
        color: resolvedBackground,
        borderRadius: resolvedRadius,
        border: Border.all(
          color: SearchSemanticConstants.borderColor(context),
          width: AppSpacing.hairline,
        ),
        boxShadow: resolvedShadows,
      ),
      child: CupertinoTheme(
        data: CupertinoTheme.of(
          context,
        ).copyWith(primaryColor: AppColors.iosAccent(context)),
        child: CupertinoSearchTextField(
          controller: controller,
          focusNode: focusNode,
          placeholder: placeholder,
          onChanged: onChanged,
          onSubmitted: onSubmitted,
          onSuffixTap: onSuffixTap,
          autofocus: autofocus,
          autocorrect: autocorrect,
          enabled: enabled,
          style: resolvedStyle,
          placeholderStyle: resolvedPlaceholderStyle,
          backgroundColor: Colors.transparent,
          itemColor: resolvedItemColor,
          itemSize: resolvedItemSize,
          padding: resolvedPadding,
          borderRadius: resolvedRadius,
          prefixIcon:
              prefixIcon ??
              Icon(
                CupertinoIcons.search,
                size: resolvedItemSize,
                color: resolvedItemColor,
              ),
          restorationId: restorationId,
        ),
      ),
    );
  }
}
