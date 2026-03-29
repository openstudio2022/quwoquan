import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/widgets/app_modal_surface.dart';
import 'package:quwoquan_app/core/widgets/conversation_sheet.dart';

class AppActionSheetItem<T> {
  const AppActionSheetItem({
    required this.label,
    this.value,
    this.description,
    this.icon,
    this.isSelected = false,
    this.isDestructive = false,
    this.enabled = true,
  });

  final String label;
  final T? value;
  final String? description;
  final IconData? icon;
  final bool isSelected;
  final bool isDestructive;
  final bool enabled;
}

class AppActionSheetSection<T> {
  const AppActionSheetSection({required this.items});

  final List<AppActionSheetItem<T>> items;
}

Future<T?> showAppActionSheet<T>(
  BuildContext context, {
  String? title,
  String? message,
  required List<AppActionSheetSection<T>> sections,
  String cancelLabel = UITextConstants.cancel,
  double? maxHeightRatio,
}) {
  return showCupertinoModalPopup<T>(
    context: context,
    barrierColor: Colors.transparent,
    builder: (sheetContext) => _AppActionSheet<T>(
      title: title,
      message: message,
      sections: sections,
      cancelLabel: cancelLabel,
      maxHeightRatio: maxHeightRatio,
    ),
  );
}

/// 选项仅高亮草稿选中态；点「确定」才返回选中值，点「取消」或关闭返回 `null`。
Future<T?> showAppActionSheetForConfirm<T>(
  BuildContext context, {
  String? title,
  String? message,
  required List<AppActionSheetSection<T>> sections,
  required T initialValue,
  String cancelLabel = UITextConstants.cancel,
  String confirmLabel = UITextConstants.ok,
  double? maxHeightRatio,
}) {
  return showCupertinoModalPopup<T>(
    context: context,
    barrierColor: Colors.transparent,
    builder: (sheetContext) => _AppActionSheetForConfirm<T>(
      title: title,
      message: message,
      sections: sections,
      initialValue: initialValue,
      cancelLabel: cancelLabel,
      confirmLabel: confirmLabel,
      maxHeightRatio: maxHeightRatio,
    ),
  );
}

class _AppActionSheet<T> extends StatelessWidget {
  const _AppActionSheet({
    required this.sections,
    required this.cancelLabel,
    this.title,
    this.message,
    this.maxHeightRatio,
  });

  final String? title;
  final String? message;
  final List<AppActionSheetSection<T>> sections;
  final String cancelLabel;
  final double? maxHeightRatio;

  @override
  Widget build(BuildContext context) {
    final isDark =
        (CupertinoTheme.of(context).brightness ??
            MediaQuery.platformBrightnessOf(context)) ==
        Brightness.dark;
    final pageBackground =
        SettingsSemanticConstants.conversationSheetPanelBackground(isDark);

    return AppBottomModalSurface(
      onDismiss: () => Navigator.of(context).pop(),
      backgroundColor: pageBackground,
      maxHeightRatio: maxHeightRatio,
      contentPadding: EdgeInsets.fromLTRB(
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        0,
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
      ),
      child: SingleChildScrollView(
        physics: const BouncingScrollPhysics(),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ConversationSheetHeader(
              isDark: isDark,
              title: title,
              footnote: message,
            ),
            for (final section in sections) ...[
              _ActionSheetSectionCard<T>(
                isDark: isDark,
                section: section,
              ),
              SizedBox(
                height: SettingsSemanticConstants.conversationSheetSectionGap,
              ),
            ],
            ConversationSheetCancelBar(
              isDark: isDark,
              label: cancelLabel,
              onTap: () => Navigator.of(context).pop(),
            ),
          ],
        ),
      ),
    );
  }
}

class _ActionSheetSectionCard<T> extends StatelessWidget {
  const _ActionSheetSectionCard({
    required this.isDark,
    required this.section,
  });

  final bool isDark;
  final AppActionSheetSection<T> section;

  @override
  Widget build(BuildContext context) {
    return ConversationSheetListCard(
      isDark: isDark,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: section.items.asMap().entries.map((entry) {
          final index = entry.key;
          final item = entry.value;
          final inset = ConversationSheetSingleSelectRow.dividerInsetForIcon(
            item.icon != null,
          );
          return Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ConversationSheetSingleSelectRow(
                isDark: isDark,
                label: item.label,
                icon: item.icon,
                description: item.description,
                isSelected: item.isSelected,
                isDestructive: item.isDestructive,
                enabled: item.enabled,
                onTap: () => Navigator.of(context).pop(item.value),
              ),
              if (index < section.items.length - 1)
                ConversationSheetDivider(
                  isDark: isDark,
                  dividerLeftInset: inset,
                ),
            ],
          );
        }).toList(),
      ),
    );
  }
}

class _AppActionSheetForConfirm<T> extends StatefulWidget {
  const _AppActionSheetForConfirm({
    required this.sections,
    required this.initialValue,
    required this.cancelLabel,
    required this.confirmLabel,
    this.title,
    this.message,
    this.maxHeightRatio,
  });

  final String? title;
  final String? message;
  final List<AppActionSheetSection<T>> sections;
  final T initialValue;
  final String cancelLabel;
  final String confirmLabel;
  final double? maxHeightRatio;

  @override
  State<_AppActionSheetForConfirm<T>> createState() =>
      _AppActionSheetForConfirmState<T>();
}

class _AppActionSheetForConfirmState<T>
    extends State<_AppActionSheetForConfirm<T>> {
  late T _draft;

  @override
  void initState() {
    super.initState();
    _draft = widget.initialValue;
  }

  @override
  Widget build(BuildContext context) {
    final isDark =
        (CupertinoTheme.of(context).brightness ??
            MediaQuery.platformBrightnessOf(context)) ==
        Brightness.dark;
    final pageBackground =
        SettingsSemanticConstants.conversationSheetPanelBackground(isDark);

    return AppBottomModalSurface(
      onDismiss: () => Navigator.of(context).pop(),
      backgroundColor: pageBackground,
      maxHeightRatio: widget.maxHeightRatio,
      contentPadding: EdgeInsets.fromLTRB(
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        0,
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
      ),
      child: SingleChildScrollView(
        physics: const BouncingScrollPhysics(),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ConversationSheetHeader(
              isDark: isDark,
              title: widget.title,
              footnote: widget.message,
            ),
            for (final section in widget.sections) ...[
              _ActionSheetSectionCardForConfirm<T>(
                isDark: isDark,
                section: section,
                selectedValue: _draft,
                onSelect: (value) {
                  if (value != null) {
                    setState(() => _draft = value);
                  }
                },
              ),
              SizedBox(
                height: SettingsSemanticConstants.conversationSheetSectionGap,
              ),
            ],
            ConversationSheetCancelConfirmBar(
              isDark: isDark,
              cancelLabel: widget.cancelLabel,
              confirmLabel: widget.confirmLabel,
              onCancel: () => Navigator.of(context).pop(),
              onConfirm: () => Navigator.of(context).pop(_draft),
            ),
          ],
        ),
      ),
    );
  }
}

class _ActionSheetSectionCardForConfirm<T> extends StatelessWidget {
  const _ActionSheetSectionCardForConfirm({
    required this.isDark,
    required this.section,
    required this.selectedValue,
    required this.onSelect,
  });

  final bool isDark;
  final AppActionSheetSection<T> section;
  final T selectedValue;
  final void Function(T? value) onSelect;

  @override
  Widget build(BuildContext context) {
    return ConversationSheetListCard(
      isDark: isDark,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: section.items.asMap().entries.map((entry) {
          final index = entry.key;
          final item = entry.value;
          final inset = ConversationSheetSingleSelectRow.dividerInsetForIcon(
            item.icon != null,
          );
          final isSelected = item.value != null && item.value == selectedValue;
          return Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ConversationSheetSingleSelectRow(
                isDark: isDark,
                label: item.label,
                icon: item.icon,
                description: item.description,
                isSelected: isSelected,
                isDestructive: item.isDestructive,
                enabled: item.enabled,
                onTap: () => onSelect(item.value),
              ),
              if (index < section.items.length - 1)
                ConversationSheetDivider(
                  isDark: isDark,
                  dividerLeftInset: inset,
                ),
            ],
          );
        }).toList(),
      ),
    );
  }
}
