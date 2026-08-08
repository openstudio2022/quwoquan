import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/di/forward_share_dependencies.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_surface.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/runtime/shell/share/forward_share_models.dart';
import 'package:quwoquan_app/runtime/shell/share/forward_recipient_widgets.dart';

class ForwardConfirmSheet extends ConsumerStatefulWidget {
  const ForwardConfirmSheet({
    super.key,
    required this.payload,
    required this.recipient,
  });

  static const int maxMessageLines = 5;

  final AppForwardPayload payload;
  final AppForwardRecipient recipient;

  static Future<bool?> show(
    BuildContext context, {
    required AppForwardPayload payload,
    required AppForwardRecipient recipient,
  }) {
    return showAppBottomModal<bool>(
      context: context,
      builder: (sheetContext) {
        final isDark =
            CupertinoTheme.of(sheetContext).brightness == Brightness.dark;
        final keyboardInset = MediaQuery.viewInsetsOf(sheetContext).bottom;
        return AnimatedPadding(
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOutCubic,
          padding: EdgeInsets.only(bottom: keyboardInset),
          child: AppBottomModalSurface(
            onDismiss: () => Navigator.of(sheetContext).pop(false),
            backgroundColor:
                SettingsSemanticConstants.conversationSheetPanelBackground(
                  isDark,
                ),
            contentPadding: EdgeInsets.fromLTRB(
              SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
              SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
              SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
              SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
            ),
            maxHeightRatio: AppSpacing.modalSheetMaxHeightRatio,
            showHandle: false,
            child: ForwardConfirmSheet(payload: payload, recipient: recipient),
          ),
        );
      },
    );
  }

  @override
  ConsumerState<ForwardConfirmSheet> createState() =>
      _ForwardConfirmSheetState();
}

class _ForwardConfirmSheetState extends ConsumerState<ForwardConfirmSheet> {
  final TextEditingController _messageController = TextEditingController();
  final FocusNode _focusNode = FocusNode();
  bool _busy = false;
  bool _inputFocused = false;
  final String _clientMsgId =
      'forward_${DateTime.now().microsecondsSinceEpoch}';

  @override
  void initState() {
    super.initState();
    _focusNode.addListener(_handleFocusChanged);
  }

  @override
  void dispose() {
    _focusNode.removeListener(_handleFocusChanged);
    _focusNode.dispose();
    _messageController.dispose();
    super.dispose();
  }

  void _handleFocusChanged() {
    if (_inputFocused == _focusNode.hasFocus) {
      return;
    }
    setState(() => _inputFocused = _focusNode.hasFocus);
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final primary =
        SettingsSemanticConstants.conversationSheetPrimaryLabelColor(isDark);
    final secondary =
        SettingsSemanticConstants.conversationSheetSecondaryLabelColor(isDark);
    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            ChatText.forwardSendToLabel,
            style: TextStyle(
              fontSize: AppTypography.iosBody,
              fontWeight: AppTypography.semiBold,
              color: primary,
            ),
          ),
          SizedBox(height: AppSpacing.containerSm),
          DecoratedBox(
            decoration: BoxDecoration(
              color: SettingsSemanticConstants.blockBackground(isDark),
              borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
            ),
            child: ForwardRecipientTile(
              isDark: isDark,
              recipient: widget.recipient,
              showChevron: true,
              onTap: () {},
            ),
          ),
          SizedBox(height: AppSpacing.containerMd),
          Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(
                maxWidth: AppSpacing.twoHundredTwenty,
              ),
              child:
                  widget.payload.previewBuilder?.call(context) ??
                  _DefaultForwardPreview(
                    payload: widget.payload,
                    isDark: isDark,
                  ),
            ),
          ),
          SizedBox(height: AppSpacing.containerMd),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: AppColors.iosSystemBackground(context),
                    borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
                    border: Border.all(
                      color: SettingsSemanticConstants.blockBorderColor(isDark),
                      width: AppSpacing.hairline,
                    ),
                  ),
                  child: CupertinoTextField(
                    controller: _messageController,
                    focusNode: _focusNode,
                    placeholder: ChatText.forwardMessagePlaceholder,
                    keyboardType: TextInputType.multiline,
                    minLines: 1,
                    maxLines: ForwardConfirmSheet.maxMessageLines,
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerMd,
                      vertical: AppSpacing.containerSm,
                    ),
                    decoration: const BoxDecoration(
                      color: AppColors.transparent,
                    ),
                    style: TextStyle(
                      fontSize: AppTypography.iosBody,
                      color: primary,
                      height: AppSpacing.textLineHeightBody,
                    ),
                    placeholderStyle: TextStyle(
                      fontSize: AppTypography.iosBody,
                      color: secondary,
                    ),
                  ),
                ),
              ),
              SizedBox(width: AppSpacing.containerSm),
              Icon(
                CupertinoIcons.smiley,
                size: AppSpacing.iconLarge,
                color: primary,
              ),
              if (_inputFocused) ...[
                SizedBox(width: AppSpacing.containerSm),
                _InlineSendButton(busy: _busy, onPressed: _send),
              ],
            ],
          ),
          if (!_inputFocused) ...[
            SizedBox(height: AppSpacing.containerLg),
            Row(
              children: [
                Expanded(
                  child: _SheetActionButton(
                    label: FoundationText.cancel,
                    foregroundColor: primary,
                    backgroundColor: SettingsSemanticConstants.blockBackground(
                      isDark,
                    ),
                    onPressed: _busy
                        ? null
                        : () => Navigator.of(context).pop(false),
                  ),
                ),
                SizedBox(width: AppSpacing.containerMd),
                Expanded(
                  child: _SheetActionButton(
                    label: ChatText.send,
                    foregroundColor: AppColors.white,
                    backgroundColor: AppColors.success,
                    busy: _busy,
                    onPressed: _busy ? null : _send,
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  Future<void> _send() async {
    if (_busy) {
      return;
    }
    setState(() => _busy = true);
    try {
      final note = _messageController.text.trim();
      await ref
          .read(forwardShareDependenciesProvider)
          .sendCard(
            payload: widget.payload,
            recipient: widget.recipient,
            note: note,
            clientMsgId: _clientMsgId,
          );
      if (!mounted) {
        return;
      }
      AppToast.show(context, ChatText.forwardSendSuccess);
      Navigator.of(context).pop(true);
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _busy = false);
      await AppActionErrorFeedback.show(
        context,
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _send();
          }
        },
      );
    }
  }
}

class _DefaultForwardPreview extends StatelessWidget {
  const _DefaultForwardPreview({required this.payload, required this.isDark});

  final AppForwardPayload payload;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final secondary =
        SettingsSemanticConstants.conversationSheetSecondaryLabelColor(isDark);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosSystemBackground(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
        border: Border.all(
          color: SettingsSemanticConstants.blockBorderColor(isDark),
          width: AppSpacing.hairline,
        ),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              payload.title,
              style: TextStyle(
                fontSize: AppTypography.iosSubheadline,
                fontWeight: AppTypography.semiBold,
                color: AppColors.iosLabel(context),
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
            if (payload.subtitle.trim().isNotEmpty) ...[
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                payload.subtitle,
                style: TextStyle(
                  fontSize: AppTypography.iosCaption1,
                  color: secondary,
                ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _SheetActionButton extends StatelessWidget {
  const _SheetActionButton({
    required this.label,
    required this.foregroundColor,
    required this.backgroundColor,
    required this.onPressed,
    this.busy = false,
  });

  final String label;
  final Color foregroundColor;
  final Color backgroundColor;
  final VoidCallback? onPressed;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      minimumSize: Size(AppSpacing.buttonHeightLg, AppSpacing.buttonHeightLg),
      padding: EdgeInsets.zero,
      onPressed: onPressed,
      child: Container(
        height: AppSpacing.buttonHeightLg,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: backgroundColor,
          borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
        ),
        child: busy
            ? AppRequestFeedback.inline()
            : Text(
                label,
                style: TextStyle(
                  fontSize: AppTypography.iosBody,
                  fontWeight: AppTypography.semiBold,
                  color: foregroundColor,
                ),
              ),
      ),
    );
  }
}

class _InlineSendButton extends StatelessWidget {
  const _InlineSendButton({required this.busy, required this.onPressed});

  final bool busy;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size(AppSpacing.buttonHeightLg, AppSpacing.buttonHeightLg),
      onPressed: busy ? null : onPressed,
      child: Container(
        height: AppSpacing.buttonHeightLg,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: AppColors.success,
          borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
        ),
        child: busy
            ? AppRequestFeedback.inline()
            : Text(
                ChatText.send,
                style: TextStyle(
                  color: AppColors.white,
                  fontSize: AppTypography.iosBody,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
      ),
    );
  }
}
