import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';

typedef CreateActionSelected = void Function(EditorStartAction action);

enum CreateActionSheetPriority { createPrimary, socialPrimary }

class CreateActionSheet extends StatelessWidget {
  const CreateActionSheet({
    super.key,
    required this.onCreateAction,
    required this.onContinueFromDraft,
    required this.onStartGroupChat,
    required this.onAddContact,
    required this.onCancel,
    this.onCreateCircle,
    this.priority = CreateActionSheetPriority.createPrimary,
  });

  final CreateActionSelected onCreateAction;
  final VoidCallback onContinueFromDraft;
  final VoidCallback onStartGroupChat;
  final VoidCallback onAddContact;
  final VoidCallback onCancel;
  final VoidCallback? onCreateCircle;
  final CreateActionSheetPriority priority;

  @override
  Widget build(BuildContext context) {
    final brightness =
        CupertinoTheme.of(context).brightness ??
        MediaQuery.platformBrightnessOf(context);
    final isDark = brightness == Brightness.dark;
    final pageBackground =
        SettingsSemanticConstants.conversationSheetPanelBackground(isDark);
    final blockBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final cancelBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceMuted,
    );
    final dividerColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    final cancelForeground = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );

    final createActions = <_SheetActionSpec>[
      _SheetActionSpec(
        label: UITextConstants.createActionGallery,
        labelKey: TestKeys.createActionGallery,
        onPressed: () => onCreateAction(EditorStartAction.gallery),
      ),
      _SheetActionSpec(
        label: UITextConstants.createActionCapture,
        labelKey: TestKeys.createActionCapture,
        onPressed: () => onCreateAction(EditorStartAction.capture),
      ),
      _SheetActionSpec(
        label: UITextConstants.createActionWrite,
        labelKey: TestKeys.createActionWrite,
        onPressed: () => onCreateAction(EditorStartAction.write),
      ),
      _SheetActionSpec(
        label: UITextConstants.createActionContinueFromDraft,
        labelKey: TestKeys.createActionContinueFromDraft,
        onPressed: onContinueFromDraft,
      ),
    ];

    final socialActions = <_SheetActionSpec>[
      _SheetActionSpec(
        label: UITextConstants.startGroupChat,
        onPressed: onStartGroupChat,
      ),
      _SheetActionSpec(
        label: UITextConstants.addSameInterest,
        onPressed: onAddContact,
      ),
      if (onCreateCircle != null)
        _SheetActionSpec(
          label: UITextConstants.createCircle,
          onPressed: onCreateCircle!,
        ),
    ];

    final orderedGroups = priority == CreateActionSheetPriority.createPrimary
        ? <List<_SheetActionSpec>>[createActions, socialActions]
        : <List<_SheetActionSpec>>[socialActions, createActions];

    return AppBottomModalSurface(
      onDismiss: onCancel,
      backgroundColor: pageBackground,
      contentPadding: EdgeInsets.fromLTRB(
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        0,
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
      ),
      panelKey: TestKeys.modalBottomSheetPanel,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Flexible(
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (var i = 0; i < orderedGroups.length; i++) ...[
                    _SheetActionGroup(
                      actions: orderedGroups[i],
                      backgroundColor: blockBackground,
                      dividerColor: dividerColor,
                      foregroundColor: AppColors.primaryColor,
                    ),
                    SizedBox(height: AppSpacing.interGroupSm),
                  ],
                ],
              ),
            ),
          ),
          _SheetActionGroup(
            actions: <_SheetActionSpec>[
              _SheetActionSpec(
                label: UITextConstants.cancel,
                onPressed: onCancel,
              ),
            ],
            backgroundColor: cancelBackground,
            dividerColor: dividerColor,
            foregroundColor: cancelForeground,
          ),
        ],
      ),
    );
  }
}

class _SheetActionSpec {
  const _SheetActionSpec({
    required this.label,
    required this.onPressed,
    this.labelKey,
  });

  final String label;
  final VoidCallback onPressed;
  final Key? labelKey;
}

class _SheetActionGroup extends StatelessWidget {
  const _SheetActionGroup({
    required this.actions,
    required this.backgroundColor,
    required this.dividerColor,
    required this.foregroundColor,
  });

  final List<_SheetActionSpec> actions;
  final Color backgroundColor;
  final Color dividerColor;
  final Color foregroundColor;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: backgroundColor,
          border: Border.all(color: dividerColor, width: AppSpacing.hairline),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (var i = 0; i < actions.length; i++) ...[
              _SheetActionRow(
                label: actions[i].label,
                labelKey: actions[i].labelKey,
                foregroundColor: foregroundColor,
                onPressed: actions[i].onPressed,
              ),
              if (i < actions.length - 1)
                Container(height: AppSpacing.hairline, color: dividerColor),
            ],
          ],
        ),
      ),
    );
  }
}

class _SheetActionRow extends StatelessWidget {
  const _SheetActionRow({
    required this.label,
    required this.foregroundColor,
    required this.onPressed,
    this.labelKey,
  });

  final String label;
  final Color foregroundColor;
  final VoidCallback onPressed;
  final Key? labelKey;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size(double.infinity, AppSpacing.modalHeaderHeight),
      onPressed: onPressed,
      child: SizedBox(
        height: AppSpacing.modalHeaderHeight,
        child: Center(
          child: Text(
            label,
            key: labelKey,
            style: TextStyle(
              fontSize: AppTypography.iosBody,
              fontWeight: AppTypography.medium,
              color: foregroundColor,
            ),
          ),
        ),
      ),
    );
  }
}
