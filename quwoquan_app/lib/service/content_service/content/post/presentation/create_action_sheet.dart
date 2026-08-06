import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_surface.dart';
import 'package:quwoquan_app/design_system/surfaces/conversation_sheet.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';

typedef CreateActionSelected = void Function(EditorStartAction action);

class CreateActionSheet extends StatefulWidget {
  const CreateActionSheet({
    super.key,
    required this.onCreateAction,
    required this.onStartGathering,
    required this.onStartGroupChat,
    required this.onCancel,
  });

  final CreateActionSelected onCreateAction;
  final VoidCallback onStartGathering;
  final VoidCallback onStartGroupChat;
  final VoidCallback onCancel;

  @override
  State<CreateActionSheet> createState() => _CreateActionSheetState();
}

class _CreateActionSheetState extends State<CreateActionSheet> {
  bool _showsContentActions = false;

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

    final primaryActions = <_SheetActionSpec>[
      _SheetActionSpec(
        label: CreationText.createActionPublishContent,
        labelKey: TestKeys.createActionPublishContent,
        onPressed: () => setState(() => _showsContentActions = true),
      ),
      _SheetActionSpec(
        label: CommunityText.createActionStartGathering,
        labelKey: TestKeys.createActionStartGathering,
        onPressed: widget.onStartGathering,
      ),
      _SheetActionSpec(
        label: ChatText.createActionCreateGroupShort,
        labelKey: TestKeys.createActionStartGroupChat,
        onPressed: widget.onStartGroupChat,
      ),
    ];
    final contentActions = <_SheetActionSpec>[
      _SheetActionSpec(
        label: CreationText.createActionPostPhotoShort,
        subtitle: CreationText.createActionPhotoSubtitle,
        labelKey: TestKeys.createActionGallery,
        onPressed: () => widget.onCreateAction(EditorStartAction.gallery),
      ),
      _SheetActionSpec(
        label: CreationText.createActionPostVideoShort,
        subtitle: CreationText.createActionCameraSubtitle,
        labelKey: TestKeys.createActionCapture,
        onPressed: () => widget.onCreateAction(EditorStartAction.video),
      ),
      _SheetActionSpec(
        label: CreationText.createActionWriteLong,
        labelKey: TestKeys.createActionWrite,
        onPressed: () => widget.onCreateAction(EditorStartAction.write),
      ),
    ];
    final actions = _showsContentActions ? contentActions : primaryActions;

    return AppBottomModalSurface(
      onDismiss: widget.onCancel,
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
                        actions: actions,
                        labelColor: primaryText,
                      ),
                      const SizedBox(
                        height: AppSpacing.createActionSheetGroupTrailingGap,
                      ),
                    ],
                  ),
                ),
              ),
              ConversationSheetCancelBar(
                isDark: isDark,
                label: FoundationText.cancel,
                onTap: widget.onCancel,
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
