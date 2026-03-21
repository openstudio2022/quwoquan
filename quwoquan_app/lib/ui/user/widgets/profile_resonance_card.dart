import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_ios_components.dart';

class ProfileResonanceCard extends StatelessWidget {
  const ProfileResonanceCard({
    super.key,
    required this.mode,
    required this.isDark,
    this.resonanceCount = 0,
    this.onTap,
  });

  final ProfileMode mode;
  final bool isDark;
  final int resonanceCount;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final primary = AppColors.iosAccent(context);
    final subtitle = AppColors.iosSecondaryLabel(context);
    final fill = primary.withValues(alpha: isDark ? 0.22 : 0.1);

    final text = mode == ProfileMode.mine
        ? '本周有 $resonanceCount 位趣友与你有交集'
        : '你们有 $resonanceCount 个交集点';

    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: ProfileIosSectionCard(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerMd,
          vertical: AppSpacing.containerSm,
        ),
        backgroundColor: fill,
        borderColor: primary.withValues(alpha: isDark ? 0.18 : 0.12),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Container(
              width: AppSpacing.buttonHeightSm,
              height: AppSpacing.buttonHeightSm,
              decoration: BoxDecoration(
                color: primary.withValues(alpha: isDark ? 0.22 : 0.14),
                shape: BoxShape.circle,
              ),
              child: Icon(
                CupertinoIcons.sparkles,
                size: AppSpacing.iconSmall,
                color: primary,
              ),
            ),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Text(
                text,
                style: TextStyle(
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.semiBold,
                  color: subtitle,
                  letterSpacing: -0.18,
                ),
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Icon(
              CupertinoIcons.chevron_forward,
              size: AppSpacing.iconSmall,
              color: AppColors.iosTertiaryLabel(context),
            ),
          ],
        ),
      ),
    );
  }
}
