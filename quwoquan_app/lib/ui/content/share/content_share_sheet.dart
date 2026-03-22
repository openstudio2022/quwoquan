import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/widgets/app_modal_surface.dart';
import 'package:quwoquan_app/ui/content/share/content_share_actions.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';

class ContentShareSheet extends StatefulWidget {
  const ContentShareSheet({
    super.key,
    required this.template,
    this.actionHandler = const DefaultContentShareActionHandler(),
    this.onActionCompleted,
  });

  final ContentShareTemplate template;
  final ContentShareActionHandler actionHandler;
  final Future<void> Function(ContentShareActionResult result)?
  onActionCompleted;

  static Future<void> show(
    BuildContext context, {
    required ContentShareTemplate template,
    ContentShareActionHandler actionHandler =
        const DefaultContentShareActionHandler(),
    Future<void> Function(ContentShareActionResult result)? onActionCompleted,
  }) {
    return showCupertinoModalPopup<void>(
      context: context,
      barrierColor: Colors.transparent,
      builder: (sheetContext) => AppBottomModalSurface(
        onDismiss: () => Navigator.of(sheetContext).pop(),
        backgroundColor: AppColors.iosPageBackground(context),
        contentPadding: const EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          0,
          AppSpacing.containerMd,
          AppSpacing.containerMd,
        ),
        child: ContentShareSheet(
          template: template,
          actionHandler: actionHandler,
          onActionCompleted: onActionCompleted,
        ),
      ),
    );
  }

  @override
  State<ContentShareSheet> createState() => _ContentShareSheetState();
}

class _ContentShareSheetState extends State<ContentShareSheet> {
  String? _busyActionId;

  @override
  Widget build(BuildContext context) {
    final secondaryText = CupertinoColors.secondaryLabel.resolveFrom(context);
    final destructiveText = AppColors.iosDestructive(context);

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SizedBox(
          height: AppSpacing.modalHeaderHeight,
          child: Center(
            child: Text(
              widget.template.title,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.lg,
                fontWeight: AppTypography.semiBold,
              ),
            ),
          ),
        ),
        Text(
          widget.template.subtitle,
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: AppTypography.sm, color: secondaryText),
        ),
        if ((widget.template.notice ?? '').trim().isNotEmpty) ...[
          SizedBox(height: AppSpacing.intraGroupSm),
          Text(
            widget.template.notice!,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.sm,
              color: widget.template.isBlocked
                  ? destructiveText
                  : secondaryText,
            ),
          ),
        ],
        SizedBox(height: AppSpacing.interGroupSm),
        Container(
          decoration: BoxDecoration(
            color: AppColors.iosGroupedSurface(context),
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          ),
          padding: EdgeInsets.all(AppSpacing.containerMd),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (widget.template.shareTitle.trim().isNotEmpty)
                Text(
                  widget.template.shareTitle,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    fontWeight: AppTypography.medium,
                  ),
                ),
              if (widget.template.shareSummary.trim().isNotEmpty) ...[
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  widget.template.shareSummary,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: secondaryText,
                  ),
                ),
              ],
            ],
          ),
        ),
        SizedBox(height: AppSpacing.interGroupSm),
        if (widget.template.isBlocked)
          Container(
            decoration: BoxDecoration(
              color: AppColors.iosGroupedSurface(context),
              borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            ),
            padding: EdgeInsets.all(AppSpacing.containerMd),
            child: Text(
              UITextConstants.sharePrivateBlocked,
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: destructiveText,
              ),
            ),
          )
        else
          Container(
            decoration: BoxDecoration(
              color: AppColors.iosGroupedSurface(context),
              borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            ),
            child: Column(
              children: widget.template.actions.asMap().entries.map((entry) {
                final index = entry.key;
                final action = entry.value;
                return Column(
                  children: [
                    CupertinoButton(
                      padding: EdgeInsets.zero,
                      onPressed: _busyActionId != null
                          ? null
                          : () => _handleAction(action),
                      child: Padding(
                        padding: EdgeInsets.symmetric(
                          horizontal: AppSpacing.containerMd,
                          vertical: AppSpacing.containerSm,
                        ),
                        child: Row(
                          children: [
                            Icon(_iconForAction(action.id)),
                            SizedBox(width: AppSpacing.containerSm),
                            Expanded(child: Text(action.label)),
                            if (_busyActionId == action.id)
                              const SizedBox(
                                width: AppSpacing.eighteen,
                                height: AppSpacing.eighteen,
                                child: CupertinoActivityIndicator(),
                              ),
                          ],
                        ),
                      ),
                    ),
                    if (index < widget.template.actions.length - 1)
                      Container(
                        height: AppSpacing.hairline,
                        margin: EdgeInsets.only(
                          left:
                              AppSpacing.containerMd +
                              AppSpacing.twenty +
                              AppSpacing.containerSm,
                          right: AppSpacing.containerMd,
                        ),
                        color: AppColors.iosSeparator(context),
                      ),
                  ],
                );
              }).toList(),
            ),
          ),
      ],
    );
  }

  Future<void> _handleAction(ContentShareAction action) async {
    setState(() => _busyActionId = action.id);
    final result = await widget.actionHandler.execute(
      context,
      widget.template,
      action,
    );
    if (!mounted) return;
    setState(() => _busyActionId = null);
    if (!result.success) {
      return;
    }
    await widget.onActionCompleted?.call(result);
    if (!mounted) return;
    Navigator.of(context).pop(result);
  }

  IconData _iconForAction(String actionId) {
    switch (actionId) {
      case 'save_poster':
        return Icons.image_outlined;
      case 'system_share':
        return Icons.ios_share_outlined;
      case 'copy_link':
      default:
        return Icons.link;
    }
  }
}
