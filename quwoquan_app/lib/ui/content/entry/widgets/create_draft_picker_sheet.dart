import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_draft_local_storage.dart';

/// 草稿列表底栏；视觉与 [CreateActionSheet] 对齐（同面板底、外边距、分组圆角、分割线、主色标签、取消组）。
class CreateDraftPickerSheet extends StatefulWidget {
  const CreateDraftPickerSheet({
    super.key,
    required this.initialDrafts,
    required this.onSelect,
    required this.onDismiss,
  });

  final List<CreateDraft> initialDrafts;
  final ValueChanged<CreateDraft> onSelect;
  final VoidCallback onDismiss;

  @override
  State<CreateDraftPickerSheet> createState() => _CreateDraftPickerSheetState();
}

class _CreateDraftPickerSheetState extends State<CreateDraftPickerSheet> {
  late List<CreateDraft> _drafts;

  @override
  void initState() {
    super.initState();
    _drafts = List<CreateDraft>.of(widget.initialDrafts);
  }

  Future<void> _deleteDraft(CreateDraft draft) async {
    await CreateDraftLocalStorage.removeDraftById(draft.id);
    if (!mounted) {
      return;
    }
    setState(() {
      _drafts.removeWhere((d) => d.id == draft.id);
    });
    if (_drafts.isEmpty) {
      Navigator.of(context).pop();
    }
  }

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

    return AppBottomModalSurface(
      onDismiss: widget.onDismiss,
      backgroundColor: pageBackground,
      maxHeightRatio: 0.72,
      contentPadding: EdgeInsets.fromLTRB(
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        0,
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
      ),
      panelKey: TestKeys.createDraftPickerPanel,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          if (_drafts.isEmpty)
            _DraftPickerActionGroup(
              backgroundColor: blockBackground,
              dividerColor: dividerColor,
              child: SizedBox(
                height: AppSpacing.modalHeaderHeight,
                child: Center(
                  child: Text(
                    UITextConstants.createDraftPickerEmptyTitle,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: AppTypography.iosBody,
                      fontWeight: AppTypography.medium,
                      color: cancelForeground,
                    ),
                  ),
                ),
              ),
            )
          else
            Flexible(
              child: _DraftPickerActionGroup(
                backgroundColor: blockBackground,
                dividerColor: dividerColor,
                child: ListView.separated(
                  physics: const ClampingScrollPhysics(),
                  itemCount: _drafts.length,
                  separatorBuilder: (context, index) => Container(
                    height: AppSpacing.hairline,
                    color: dividerColor,
                  ),
                  itemBuilder: (context, index) {
                    final draft = _drafts[index];
                    final preview = draft.previewText.trim().isEmpty
                        ? UITextConstants.createDraftPickerPreviewFallback
                        : draft.previewText.trim();
                    return Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Expanded(
                          child: CupertinoButton(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.containerMd,
                              vertical: AppSpacing.containerSm,
                            ),
                            minimumSize: const Size(0, 0),
                            onPressed: () => widget.onSelect(draft),
                            child: Align(
                              alignment: Alignment.centerLeft,
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                mainAxisSize: MainAxisSize.min,
                                children: <Widget>[
                                  Text(
                                    draft.draftLabel,
                                    style: TextStyle(
                                      fontSize: AppTypography.iosBody,
                                      fontWeight: AppTypography.medium,
                                      color: AppColors.primaryColor,
                                    ),
                                  ),
                                  SizedBox(height: AppSpacing.intraGroupXs),
                                  Text(
                                    preview,
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      fontSize: AppTypography.sm,
                                      fontWeight: AppTypography.regular,
                                      color: cancelForeground,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                        CupertinoButton(
                          padding: EdgeInsets.only(
                            top: AppSpacing.xs,
                            right: AppSpacing.sm,
                          ),
                          minimumSize: Size.zero,
                          onPressed: () => _deleteDraft(draft),
                          child: Text(
                            UITextConstants.messageActionDelete,
                            style: const TextStyle(
                              fontSize: AppTypography.sm,
                              color: CupertinoColors.destructiveRed,
                            ),
                          ),
                        ),
                      ],
                    );
                  },
                ),
              ),
            ),
          SizedBox(height: AppSpacing.interGroupSm),
          _DraftPickerActionGroup(
            backgroundColor: cancelBackground,
            dividerColor: dividerColor,
            child: CupertinoButton(
              padding: EdgeInsets.zero,
              minimumSize: const Size(
                double.infinity,
                AppSpacing.modalHeaderHeight,
              ),
              onPressed: widget.onDismiss,
              child: Text(
                UITextConstants.cancel,
                style: TextStyle(
                  fontSize: AppTypography.iosBody,
                  fontWeight: AppTypography.medium,
                  color: cancelForeground,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _DraftPickerActionGroup extends StatelessWidget {
  const _DraftPickerActionGroup({
    required this.backgroundColor,
    required this.dividerColor,
    required this.child,
  });

  final Color backgroundColor;
  final Color dividerColor;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: backgroundColor,
          border: Border.all(color: dividerColor, width: AppSpacing.hairline),
        ),
        child: child,
      ),
    );
  }
}
