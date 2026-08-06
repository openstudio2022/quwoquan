import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/formatters/chat_time_formatter.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_surface.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ChatMessageReceipt;

/// Conversation-owned modal for the canonical MessageReceiptFact query.
final class MessageReceiptSheet extends StatelessWidget {
  const MessageReceiptSheet({
    super.key,
    required this.receipts,
    this.displayNames = const <String, String>{},
  });

  final List<ChatMessageReceipt> receipts;
  final Map<String, String> displayNames;

  static Future<void> show(
    BuildContext context, {
    required List<ChatMessageReceipt> receipts,
    Map<String, String> displayNames = const <String, String>{},
  }) {
    return showAppBottomModal<void>(
      context: context,
      builder: (_) =>
          MessageReceiptSheet(receipts: receipts, displayNames: displayNames),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final foreground = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    return AppBottomModalSurface(
      panelKey: const ValueKey<String>('message-receipt-sheet'),
      onDismiss: () => Navigator.of(context).pop(),
      maxHeightRatio: 0.56,
      contentPadding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        0,
        AppSpacing.containerMd,
        AppSpacing.containerMd,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: EdgeInsets.only(bottom: AppSpacing.containerSm),
            child: Text(
              ChatText.messageReceiptTitle,
              style: TextStyle(
                color: foreground,
                fontSize: AppTypography.lg,
                fontWeight: AppTypography.semiBold,
              ),
            ),
          ),
          if (receipts.isEmpty)
            Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpacing.containerLg),
              child: Text(
                ChatText.messageReceiptEmpty,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: foreground.withValues(alpha: 0.64),
                  fontSize: AppTypography.base,
                ),
              ),
            )
          else
            Flexible(
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: receipts.length,
                separatorBuilder: (_, _) =>
                    SizedBox(height: AppSpacing.intraGroupSm),
                itemBuilder: (context, index) {
                  final receipt = receipts[index];
                  final displayName = displayNames[receipt.userId]?.trim();
                  return Semantics(
                    label: ChatText.messageReceiptSemanticLabel(
                      displayName?.isNotEmpty == true
                          ? displayName!
                          : ChatText.messageReceiptMember,
                    ),
                    child: Row(
                      children: [
                        Icon(
                          CupertinoIcons.check_mark_circled_solid,
                          color: AppColors.primaryColor,
                          size: AppSpacing.iconMedium,
                        ),
                        SizedBox(width: AppSpacing.containerSm),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                displayName?.isNotEmpty == true
                                    ? displayName!
                                    : ChatText.messageReceiptMember,
                                style: TextStyle(
                                  color: foreground,
                                  fontSize: AppTypography.base,
                                  fontWeight: AppTypography.medium,
                                ),
                              ),
                              Text(
                                ChatTimeFormatter.format(receipt.readAt),
                                style: TextStyle(
                                  color: foreground.withValues(alpha: 0.56),
                                  fontSize: AppTypography.sm,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  );
                },
              ),
            ),
        ],
      ),
    );
  }
}
