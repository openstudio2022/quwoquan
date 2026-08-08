import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/media/app_media_image.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/contact_candidate_vm.dart';

/// 添加联系人候选行：头像 + 昵称/副标题 + 能力位驱动的「添加 / 回关 / 已添加」按钮。
/// 搜索结果页、手机通讯录页共用（单一渲染真相源）。
class ContactCandidateRow extends StatelessWidget {
  const ContactCandidateRow({
    super.key,
    required this.candidate,
    required this.onAdd,
    this.onTap,
    this.pending = false,
  });

  final ContactCandidateVm candidate;
  final VoidCallback onAdd;
  final VoidCallback? onTap;
  final bool pending;

  @override
  Widget build(BuildContext context) {
    final subtitle = candidate.subtitle?.trim().isNotEmpty == true
        ? candidate.subtitle!.trim()
        : (candidate.userHandle.isNotEmpty ? candidate.userHandle : null);
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerMd,
          vertical: AppSpacing.containerSm,
        ),
        child: Row(
          children: <Widget>[
            _Avatar(
              url: candidate.avatarUrl ?? '',
              name: candidate.displayName,
            ),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    candidate.displayName,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosBody,
                      fontWeight: AppTypography.semiBold,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                  if (subtitle != null) ...<Widget>[
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Text(
                      subtitle,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        color: AppColors.iosSecondaryLabel(context),
                      ),
                    ),
                  ],
                ],
              ),
            ),
            SizedBox(width: AppSpacing.containerSm),
            _AddActionButton(
              addState: candidate.addState,
              pending: pending,
              onAdd: onAdd,
            ),
          ],
        ),
      ),
    );
  }
}

class _Avatar extends StatelessWidget {
  const _Avatar({required this.url, required this.name});

  final String url;
  final String name;

  @override
  Widget build(BuildContext context) {
    final initial = name.trim().isNotEmpty
        ? name.trim().characters.first.toUpperCase()
        : '';
    final fallback = ColoredBox(
      color: AppColors.iosAccent(context).withValues(alpha: 0.12),
      child: Center(
        child: initial.isEmpty
            ? Icon(
                CupertinoIcons.person_fill,
                size: AppSpacing.iconSmall,
                color: AppColors.iosAccent(context),
              )
            : Text(
                initial,
                style: TextStyle(
                  fontSize: AppTypography.iosBody,
                  fontWeight: AppTypography.semiBold,
                  color: AppColors.iosAccent(context),
                ),
              ),
      ),
    );
    return ClipOval(
      child: SizedBox(
        width: AppSpacing.avatarUserLg,
        height: AppSpacing.avatarUserLg,
        child: url.trim().isEmpty
            ? fallback
            : AppMediaImage(
                imageSource: url,
                fit: BoxFit.cover,
                width: AppSpacing.avatarUserLg,
                height: AppSpacing.avatarUserLg,
                placeholder: fallback,
                errorWidget: fallback,
              ),
      ),
    );
  }
}

class _AddActionButton extends StatelessWidget {
  const _AddActionButton({
    required this.addState,
    required this.pending,
    required this.onAdd,
  });

  final ContactAddState addState;
  final bool pending;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) {
    if (addState == ContactAddState.isSelf) {
      return const SizedBox.shrink();
    }
    final accent = AppColors.iosAccent(context);
    final isAdded = addState == ContactAddState.added;
    final isUnavailable = addState == ContactAddState.unavailable;
    final label = switch (addState) {
      ContactAddState.added => ContactText.contactAlreadyAdded,
      ContactAddState.canFollowBack => ContactText.contactAddBack,
      _ => ContactText.addContact,
    };
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.intraGroupXs,
      ),
      minimumSize: Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.buttonHeightSm,
      ),
      borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
      color: (isAdded || isUnavailable) ? null : accent,
      onPressed: isAdded || isUnavailable || pending ? null : onAdd,
      child: pending
          ? AppRequestFeedback.inline()
          : Text(
              label,
              style: TextStyle(
                fontSize: AppTypography.iosCallout,
                fontWeight: AppTypography.semiBold,
                color: (isAdded || isUnavailable)
                    ? AppColors.iosSecondaryLabel(context)
                    : AppColors.white,
              ),
            ),
    );
  }
}
