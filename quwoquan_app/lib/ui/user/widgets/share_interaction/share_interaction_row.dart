import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/ui/user/models/share_interaction_models.dart';
import 'package:quwoquan_app/ui/user/widgets/share_interaction/share_target_preview.dart';

class ShareInteractionRow extends StatelessWidget {
  const ShareInteractionRow({
    super.key,
    required this.item,
    required this.isLast,
    this.onOpenUser,
    this.onOpenTarget,
    this.onOpenImpact,
  });

  final ShareInteractionItem item;
  final bool isLast;
  final VoidCallback? onOpenUser;
  final VoidCallback? onOpenTarget;
  final VoidCallback? onOpenImpact;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.brightnessOf(context) == Brightness.dark;
    final primary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final secondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final unreadBackground = AppColors.iosAccent(
      context,
    ).withValues(alpha: isDark ? 0.08 : 0.035);
    final divider = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );

    return Semantics(
      button: onOpenTarget != null,
      label: _actionText,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onOpenTarget,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: item.isUnread ? unreadBackground : AppColors.transparent,
            border: isLast
                ? null
                : Border(
                    bottom: BorderSide(
                      color: divider,
                      width: AppSpacing.hairline,
                    ),
                  ),
          ),
          child: ConstrainedBox(
            constraints: const BoxConstraints(
              minHeight: AppSpacing.profileShareInteractionRowMinHeight,
            ),
            child: Padding(
              padding: EdgeInsetsDirectional.only(
                start: AppSpacing.containerMd,
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Padding(
                    padding: EdgeInsets.only(top: AppSpacing.md),
                    child: _AvatarButton(item: item, onPressed: onOpenUser),
                  ),
                  SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Padding(
                      padding: EdgeInsets.symmetric(vertical: AppSpacing.md),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Row(
                            children: <Widget>[
                              Expanded(
                                child: GestureDetector(
                                  behavior: HitTestBehavior.opaque,
                                  onTap: onOpenUser,
                                  child: Text(
                                    item.displayName,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      color: primary,
                                      fontSize: AppTypography.iosSubheadline,
                                      fontWeight: AppTypography
                                          .secondaryTabSelectedWeight,
                                    ),
                                  ),
                                ),
                              ),
                              if (item.isUnread)
                                SizedBox.square(
                                  dimension: AppSpacing
                                      .profileShareInteractionUnreadBadgeSize,
                                  child: Center(
                                    child: DecoratedBox(
                                      decoration: BoxDecoration(
                                        color: AppColors.iosAccent(context),
                                        shape: BoxShape.circle,
                                      ),
                                      child: SizedBox.square(
                                        dimension: AppSpacing.xs,
                                      ),
                                    ),
                                  ),
                                ),
                            ],
                          ),
                          SizedBox(height: AppSpacing.intraGroupXs),
                          Text(
                            _actionText,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              color: primary,
                              fontSize: AppTypography.iosFootnote,
                            ),
                          ),
                          if (item.shareText.trim().isNotEmpty) ...<Widget>[
                            SizedBox(height: AppSpacing.intraGroupXs),
                            Text(
                              item.shareText.trim(),
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                color: secondary,
                                fontSize: AppTypography.iosFootnote,
                              ),
                            ),
                          ],
                          SizedBox(height: AppSpacing.intraGroupXs),
                          Row(
                            children: <Widget>[
                              Text(
                                _timeLabel(item.occurredAt),
                                style: TextStyle(
                                  color: secondary,
                                  fontSize: AppTypography.iosCaption1,
                                ),
                              ),
                              if (item.hasImpact) ...<Widget>[
                                SizedBox(width: AppSpacing.sm),
                                Expanded(
                                  child: CupertinoButton(
                                    minimumSize: const Size(
                                      AppSpacing.minInteractiveSize,
                                      AppSpacing.minInteractiveSize,
                                    ),
                                    alignment: AlignmentDirectional.centerStart,
                                    padding: EdgeInsets.zero,
                                    onPressed: item.impactIsNavigable
                                        ? onOpenImpact
                                        : null,
                                    child: Text(
                                      item.impactPrimaryText,
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: TextStyle(
                                        color: item.impactIsNavigable
                                            ? AppColors.iosAccent(context)
                                            : secondary,
                                        fontSize: AppTypography.iosCaption1,
                                      ),
                                    ),
                                  ),
                                ),
                              ],
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                  SizedBox(width: AppSpacing.sm),
                  Padding(
                    padding: EdgeInsetsDirectional.only(
                      top: AppSpacing.md,
                      end: AppSpacing.containerMd,
                    ),
                    child: ShareTargetPreview(item: item, onTap: onOpenTarget),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  String get _actionText {
    final suffix = item.targetKind == ShareTargetKind.discussion
        ? UITextConstants.profileShareInitiatedDiscussionSuffix
        : UITextConstants.profileShareInitiatedRecordSuffix;
    if (item.direction == ShareInteractionDirection.initiated) {
      return '${UITextConstants.profileShareInitiatedRecordPrefix} ${item.displayName}$suffix';
    }
    return item.targetKind == ShareTargetKind.discussion
        ? UITextConstants.profileShareReceivedDiscussionAction
        : UITextConstants.profileShareReceivedRecordAction;
  }
}

class _AvatarButton extends StatelessWidget {
  const _AvatarButton({required this.item, required this.onPressed});

  final ShareInteractionItem item;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      minimumSize: const Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.minInteractiveSize,
      ),
      padding: EdgeInsets.zero,
      onPressed: onPressed,
      child: ClipOval(
        child: SizedBox.square(
          dimension: AppSpacing.profileShareInteractionAvatarSize,
          child: item.displayAvatarUrl.trim().isEmpty
              ? ColoredBox(
                  color: AppColorsFunctional.getColor(
                    CupertinoTheme.brightnessOf(context) == Brightness.dark,
                    ColorType.backgroundSecondary,
                  ),
                  child: Icon(
                    CupertinoIcons.person_fill,
                    color: AppColors.iosSecondaryLabel(context),
                  ),
                )
              : AppCachedNetworkImage(
                  imageUrl: item.displayAvatarUrl,
                  fit: BoxFit.cover,
                  errorWidget: Icon(
                    CupertinoIcons.person_fill,
                    color: AppColors.iosSecondaryLabel(context),
                  ),
                ),
        ),
      ),
    );
  }
}

String _timeLabel(DateTime value) {
  final local = value.toLocal();
  final hour = local.hour.toString().padLeft(2, '0');
  final minute = local.minute.toString().padLeft(2, '0');
  return '$hour:$minute';
}
