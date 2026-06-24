import 'package:flutter/cupertino.dart';
import 'package:fluentui_system_icons/fluentui_system_icons.dart';
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
    final secondaryText =
        SettingsSemanticConstants.conversationSheetSecondaryLabelColor(isDark);
    final actionColor = SettingsSemanticConstants.createSheetActionIconColor(
      isDark,
    );
    final actionHaloColor =
        SettingsSemanticConstants.createSheetActionHaloColor(isDark);
    final draftActionColor =
        SettingsSemanticConstants.createSheetDraftActionIconColor(isDark);
    final draftHaloColor =
        SettingsSemanticConstants.createSheetDraftActionHaloColor(isDark);

    final createActions = <_SheetActionSpec>[
      _SheetActionSpec(
        label: UITextConstants.createActionPostPhotoShort,
        labelKey: TestKeys.createActionGallery,
        icon: FluentIcons.image_add_24_regular,
        iconColor: actionColor,
        haloColor: actionHaloColor,
        onPressed: () => onCreateAction(EditorStartAction.gallery),
      ),
      _SheetActionSpec(
        label: UITextConstants.createActionPostVideoShort,
        labelKey: TestKeys.createActionCapture,
        icon: FluentIcons.video_add_24_regular,
        iconColor: actionColor,
        haloColor: actionHaloColor,
        onPressed: () => onCreateAction(EditorStartAction.capture),
      ),
      _SheetActionSpec(
        label: UITextConstants.createActionWriteLong,
        labelKey: TestKeys.createActionWrite,
        icon: FluentIcons.document_edit_24_regular,
        iconColor: actionColor,
        haloColor: actionHaloColor,
        onPressed: () => onCreateAction(EditorStartAction.write),
      ),
      _SheetActionSpec(
        label: UITextConstants.createActionResumeDraft,
        labelKey: TestKeys.createActionContinueFromDraft,
        icon: FluentIcons.document_text_clock_24_regular,
        iconColor: draftActionColor,
        haloColor: draftHaloColor,
        onPressed: onContinueFromDraft,
      ),
    ];

    final socialActions = <_SheetActionSpec>[
      _SheetActionSpec(
        label: UITextConstants.createActionAddContactShort,
        icon: FluentIcons.person_add_24_regular,
        iconColor: actionColor,
        haloColor: actionHaloColor,
        onPressed: onAddContact,
      ),
      _SheetActionSpec(
        label: UITextConstants.createActionCreateGroupShort,
        icon: FluentIcons.chat_multiple_24_regular,
        iconColor: actionColor,
        haloColor: actionHaloColor,
        onPressed: onStartGroupChat,
      ),
      if (onCreateCircle != null)
        _SheetActionSpec(
          label: UITextConstants.createActionCreateCircleShort,
          icon: FluentIcons.people_add_24_regular,
          iconColor: actionColor,
          haloColor: actionHaloColor,
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
                child: ListView(
                  shrinkWrap: true,
                  primary: false,
                  padding: EdgeInsets.zero,
                  physics: const BouncingScrollPhysics(),
                  children: [
                    for (var i = 0; i < orderedGroups.length; i++) ...[
                      _SheetActionGroup(
                        title: orderedGroups[i].title,
                        actions: orderedGroups[i].actions,
                        titleColor: primaryText,
                        labelColor: secondaryText,
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
    required this.icon,
    required this.iconColor,
    required this.haloColor,
    this.labelKey,
  });

  final String label;
  final VoidCallback onPressed;
  final IconData icon;
  final Color iconColor;
  final Color haloColor;
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
    required this.titleColor,
    required this.labelColor,
    required this.accentColor,
  });

  final String title;
  final List<_SheetActionSpec> actions;
  final Color titleColor;
  final Color labelColor;
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
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          children: [
            for (final action in actions)
              Expanded(
                child: _SheetActionTile(spec: action, labelColor: labelColor),
              ),
          ],
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

class _SheetActionTile extends StatelessWidget {
  const _SheetActionTile({required this.spec, required this.labelColor});

  final _SheetActionSpec spec;
  final Color labelColor;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: spec.onPressed,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          DecoratedBox(
            decoration: BoxDecoration(
              color: spec.haloColor,
              shape: BoxShape.circle,
            ),
            child: SizedBox.square(
              dimension: AppSpacing.createActionSheetActionHaloSize,
              child: Center(
                child: Icon(
                  spec.icon,
                  size: AppSpacing.createActionSheetActionIconSize,
                  color: spec.iconColor,
                ),
              ),
            ),
          ),
          SizedBox(height: AppSpacing.createActionSheetActionLabelGap),
          Text(
            spec.label,
            key: spec.labelKey,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosCallout,
              fontWeight: AppTypography.medium,
              color: labelColor,
              height: AppTypography.lineHeightTight,
            ),
          ),
        ],
      ),
    );
  }
}
