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
    final primaryText =
        SettingsSemanticConstants.conversationSheetPrimaryLabelColor(isDark);

    final createActions = <_SheetActionSpec>[
      _SheetActionSpec(
        label: UITextConstants.createActionPostPhotoShort,
        labelKey: TestKeys.createActionGallery,
        onPressed: () => onCreateAction(EditorStartAction.gallery),
      ),
      _SheetActionSpec(
        label: UITextConstants.createActionPostVideoShort,
        labelKey: TestKeys.createActionCapture,
        onPressed: () => onCreateAction(EditorStartAction.capture),
      ),
      _SheetActionSpec(
        label: UITextConstants.createActionWriteLong,
        labelKey: TestKeys.createActionWrite,
        onPressed: () => onCreateAction(EditorStartAction.write),
      ),
      _SheetActionSpec(
        label: UITextConstants.createActionResumeDraft,
        labelKey: TestKeys.createActionContinueFromDraft,
        onPressed: onContinueFromDraft,
      ),
    ];

    final socialActions = <_SheetActionSpec>[
      _SheetActionSpec(
        label: UITextConstants.createActionAddContactShort,
        onPressed: onAddContact,
      ),
      _SheetActionSpec(
        label: UITextConstants.createActionCreateGroupShort,
        onPressed: onStartGroupChat,
      ),
      if (onCreateCircle != null)
        _SheetActionSpec(
          label: UITextConstants.createActionCreateCircleShort,
          onPressed: onCreateCircle!,
        ),
    ];

    final orderedGroups = priority == CreateActionSheetPriority.createPrimary
        ? <_SheetActionGroupSpec>[
            _SheetActionGroupSpec(
              title: UITextConstants.createActionPublishGroupTitle,
              actions: createActions,
            ),
            _SheetActionGroupSpec(
              title: UITextConstants.createActionSocialGroupTitle,
              actions: socialActions,
            ),
          ]
        : <_SheetActionGroupSpec>[
            _SheetActionGroupSpec(
              title: UITextConstants.createActionSocialGroupTitle,
              actions: socialActions,
            ),
            _SheetActionGroupSpec(
              title: UITextConstants.createActionPublishGroupTitle,
              actions: createActions,
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
                        AppSpacing.interGroupSm -
                        AppSpacing.createActionSheetGroupTrailingGap)
                    .clamp(AppSpacing.minInteractiveSize * 2, double.infinity)
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
                      for (var i = 0; i < orderedGroups.length; i++) ...[
                        _SheetActionGroup(
                          title: orderedGroups[i].title,
                          actions: orderedGroups[i].actions,
                          isDark: isDark,
                          titleColor: primaryText,
                          accentColor:
                              SettingsSemanticConstants.createSheetSectionAccentColor(
                                isDark,
                              ),
                        ),
                        SizedBox(
                          height: i == orderedGroups.length - 1
                              ? AppSpacing.createActionSheetGroupTrailingGap
                              : AppSpacing.createActionSheetGroupGap,
                        ),
                      ],
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

class _SheetActionGroupSpec {
  const _SheetActionGroupSpec({required this.title, required this.actions});

  final String title;
  final List<_SheetActionSpec> actions;
}

class _SheetActionGroup extends StatelessWidget {
  const _SheetActionGroup({
    required this.title,
    required this.actions,
    required this.isDark,
    required this.titleColor,
    required this.accentColor,
  });

  final String title;
  final List<_SheetActionSpec> actions;
  final bool isDark;
  final Color titleColor;
  final Color accentColor;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _SheetSectionTitle(
          title: title,
          color: titleColor,
          accentColor: accentColor,
        ),
        SizedBox(height: AppSpacing.createActionSheetSectionTitleGap),
        ConversationSheetListCard(
          isDark: isDark,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (var i = 0; i < actions.length; i++) ...[
                _SheetActionListRow(spec: actions[i], labelColor: titleColor),
                if (i != actions.length - 1)
                  ConversationSheetDivider(
                    isDark: isDark,
                    dividerLeftInset: AppSpacing.containerMd,
                  ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _SheetSectionTitle extends StatelessWidget {
  const _SheetSectionTitle({
    required this.title,
    required this.color,
    required this.accentColor,
  });

  final String title;
  final Color color;
  final Color accentColor;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: AppSpacing.createActionSheetSectionMarkerWidth,
          height: AppSpacing.createActionSheetSectionMarkerHeight,
          decoration: BoxDecoration(
            color: accentColor,
            borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          ),
        ),
        SizedBox(width: AppSpacing.containerXs),
        Text(
          title,
          style: TextStyle(
            fontSize: AppTypography.iosBody,
            fontWeight: AppTypography.bold,
            color: color,
            height: AppTypography.lineHeightTight,
          ),
        ),
      ],
    );
  }
}

class _SheetActionListRow extends StatelessWidget {
  const _SheetActionListRow({required this.spec, required this.labelColor});

  final _SheetActionSpec spec;
  final Color labelColor;

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
            child: Text(
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
          ),
        ),
      ),
    );
  }
}
