import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class ProfileSloganCard extends StatelessWidget {
  const ProfileSloganCard({super.key, required this.isDark, required this.bio});

  final bool isDark;
  final String? bio;

  @override
  Widget build(BuildContext context) {
    final text = bio?.trim() ?? '';
    if (text.isEmpty) {
      return const SizedBox.shrink();
    }
    final surface = isDark
        ? AppColors.iosFill(context).withValues(alpha: 0.62)
        : AppColors.iosFill(context).withValues(alpha: 0.54);
    final border = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.16 : 0.08);
    return Container(
      key: const ValueKey<String>('profile-slogan-card'),
      width: double.infinity,
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.containerSm,
      ),
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(color: border, width: AppSpacing.hairline),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: <Widget>[
          Expanded(
            child: Text(
              text,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                height: AppSpacing.textLineHeightBody,
                color: AppColors.iosLabel(context).withValues(alpha: 0.86),
                letterSpacing: -0.08,
              ),
            ),
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          Icon(
            CupertinoIcons.sparkles,
            size: AppSpacing.iconSmall,
            color: AppColors.iosAccent(context),
          ),
        ],
      ),
    );
  }
}
