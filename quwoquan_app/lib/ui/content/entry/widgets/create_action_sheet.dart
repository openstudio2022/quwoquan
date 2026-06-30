import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';

typedef CreateActionSelected = void Function(EditorStartAction action);

enum CreateActionSheetPriority { createPrimary, socialPrimary }

class CreateActionSheet extends StatelessWidget {
  const CreateActionSheet({
    super.key,
    required this.onCreateAction,
    required this.onCancel,
    this.onContinueFromDraft,
    this.onStartGroupChat,
    this.onAddContact,
    this.onCreateCircle,
    this.onInterestMatch,
    this.priority = CreateActionSheetPriority.createPrimary,
  });

  final CreateActionSelected onCreateAction;
  final VoidCallback onCancel;
  final VoidCallback? onContinueFromDraft;
  final VoidCallback? onStartGroupChat;
  final VoidCallback? onAddContact;
  final VoidCallback? onCreateCircle;
  final VoidCallback? onInterestMatch;
  final CreateActionSheetPriority priority;

  @override
  Widget build(BuildContext context) {
    final brightness =
        CupertinoTheme.of(context).brightness ??
        MediaQuery.platformBrightnessOf(context);
    final isDark = brightness == Brightness.dark;
    final pageBackground =
        SettingsSemanticConstants.conversationSheetPanelBackground(isDark);
    final primaryText =
        SettingsSemanticConstants.conversationSheetPrimaryLabelColor(isDark);

    final createActions = <_SheetActionSpec>[
      _SheetActionSpec(
        label: UITextConstants.createActionPostPhotoShort,
        subtitle: UITextConstants.createActionPhotoSubtitle,
        labelKey: TestKeys.createActionGallery,
        onPressed: () => onCreateAction(EditorStartAction.gallery),
      ),
      _SheetActionSpec(
        label: UITextConstants.createActionPostVideoShort,
        subtitle: UITextConstants.createActionCameraSubtitle,
        labelKey: TestKeys.createActionCapture,
        onPressed: () => onCreateAction(EditorStartAction.video),
      ),
      _SheetActionSpec(
        label: UITextConstants.createActionWriteLong,
        labelKey: TestKeys.createActionWrite,
        onPressed: () => onCreateAction(EditorStartAction.write),
      ),
    ];
    final socialActions = <_SheetActionSpec>[
      if (onAddContact != null)
        _SheetActionSpec(
          label: UITextConstants.createActionAddContactShort,
          onPressed: onAddContact!,
        ),
      if (onStartGroupChat != null)
        _SheetActionSpec(
          label: UITextConstants.createActionCreateGroupShort,
          onPressed: onStartGroupChat!,
        ),
      if (onCreateCircle != null)
        _SheetActionSpec(
          label: UITextConstants.createActionCreateCircleShort,
          onPressed: onCreateCircle!,
        ),
      if (onInterestMatch != null)
        _SheetActionSpec(
          label: UITextConstants.createActionInterestMatchShort,
          subtitle: UITextConstants.createActionInterestMatchSubtitle,
          labelKey: TestKeys.createActionInterestMatch,
          onPressed: onInterestMatch!,
        ),
    ];

    return AppBottomModalSurface(
      onDismiss: onCancel,
      backgroundColor: pageBackground,
      contentPadding: EdgeInsets.fromLTRB(
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        0,
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        AppSpacing.containerMd,
      ),
      panelKey: TestKeys.modalBottomSheetPanel,
      child: LayoutBuilder(
        builder: (context, constraints) {
          final maxActionHeight = constraints.maxHeight.isFinite
              ? (constraints.maxHeight -
                        AppSpacing.buttonHeight -
                        AppSpacing.interGroupSm)
                    .clamp(AppSpacing.minInteractiveSize * 3, double.infinity)
                    .toDouble()
              : double.infinity;

          return Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ConstrainedBox(
                constraints: BoxConstraints(maxHeight: maxActionHeight),
                child: SingleChildScrollView(
                  physics: const BouncingScrollPhysics(),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      _SheetActionListCard(
                        isDark: isDark,
                        actions: createActions,
                        labelColor: primaryText,
                      ),
                      if (socialActions.isNotEmpty) ...[
                        const SizedBox(
                          height: AppSpacing.createActionSheetGroupTrailingGap,
                        ),
                        _SheetActionListCard(
                          isDark: isDark,
                          actions: socialActions,
                          labelColor: primaryText,
                        ),
                      ],
                      const SizedBox(
                        height: AppSpacing.createActionSheetGroupTrailingGap,
                      ),
                    ],
                  ),
                ),
              ),
              ConversationSheetCancelBar(
                isDark: isDark,
                label: UITextConstants.cancel,
                onTap: onCancel,
              ),
            ],
          );
        },
      ),
    );
  }
}

class _SheetActionListCard extends StatelessWidget {
  const _SheetActionListCard({
    required this.isDark,
    required this.actions,
    required this.labelColor,
  });

  final bool isDark;
  final List<_SheetActionSpec> actions;
  final Color labelColor;

  @override
  Widget build(BuildContext context) {
    return ConversationSheetListCard(
      isDark: isDark,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < actions.length; i++) ...[
            _SheetActionListRow(
              spec: actions[i],
              labelColor: labelColor,
              subtitleColor:
                  SettingsSemanticConstants.conversationSheetSecondaryLabelColor(
                    isDark,
                  ),
            ),
            if (i != actions.length - 1)
              ConversationSheetDivider(isDark: isDark, dividerLeftInset: 0),
          ],
        ],
      ),
    );
  }
}

class _SheetActionSpec {
  const _SheetActionSpec({
    required this.label,
    required this.onPressed,
    this.subtitle,
    this.labelKey,
  });

  final String label;
  final VoidCallback onPressed;
  final String? subtitle;
  final Key? labelKey;
}

class _SheetActionListRow extends StatelessWidget {
  const _SheetActionListRow({
    required this.spec,
    required this.labelColor,
    required this.subtitleColor,
  });

  final _SheetActionSpec spec;
  final Color labelColor;
  final Color subtitleColor;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: spec.onPressed,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            minHeight: AppSpacing.buttonHeight + AppSpacing.containerXs,
          ),
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  spec.label,
                  key: spec.labelKey,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: AppTypography.iosBody,
                    fontWeight: AppTypography.medium,
                    color: labelColor,
                    height: AppTypography.lineHeightTight,
                  ),
                ),
                if (spec.subtitle != null) ...[
                  SizedBox(height: AppSpacing.xs),
                  Text(
                    spec.subtitle!,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      fontWeight: AppTypography.regular,
                      color: subtitleColor,
                      height: AppTypography.lineHeightTight,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
