import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
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
    return showModalBottomSheet<void>(
      context: context,
      builder: (_) => ContentShareSheet(
        template: template,
        actionHandler: actionHandler,
        onActionCompleted: onActionCompleted,
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
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.template.title,
              style: TextStyle(
                fontSize: AppTypography.lg,
                fontWeight: AppTypography.semiBold,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              widget.template.subtitle,
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: Colors.black54,
              ),
            ),
            if ((widget.template.notice ?? '').trim().isNotEmpty) ...[
              SizedBox(height: AppSpacing.intraGroupSm),
              Text(
                widget.template.notice!,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: widget.template.isBlocked
                      ? Colors.redAccent
                      : Colors.black54,
                ),
              ),
            ],
            if (widget.template.shareTitle.trim().isNotEmpty) ...[
              SizedBox(height: AppSpacing.interGroupSm),
              Text(
                widget.template.shareTitle,
                style: TextStyle(
                  fontSize: AppTypography.base,
                  fontWeight: AppTypography.medium,
                ),
              ),
            ],
            if (widget.template.shareSummary.trim().isNotEmpty) ...[
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                widget.template.shareSummary,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: Colors.black54,
                ),
              ),
            ],
            SizedBox(height: AppSpacing.interGroupMd),
            if (widget.template.isBlocked)
              Text(
                UITextConstants.sharePrivateBlocked,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: Colors.redAccent,
                ),
              )
            else
              ...widget.template.actions.map(
                (action) => ListTile(
                  leading: Icon(_iconForAction(action.id)),
                  title: Text(action.label),
                  trailing: _busyActionId == action.id
                      ? const SizedBox(
                          width: AppSpacing.eighteen,
                          height: AppSpacing.eighteen,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : null,
                  onTap: _busyActionId != null
                      ? null
                      : () => _handleAction(action),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Future<void> _handleAction(ContentShareAction action) async {
    setState(() => _busyActionId = action.id);
    final result = await widget.actionHandler.execute(
      this.context,
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
    Navigator.of(this.context).pop(result);
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
