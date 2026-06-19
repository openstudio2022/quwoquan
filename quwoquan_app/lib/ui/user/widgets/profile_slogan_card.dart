import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class ProfileSloganCard extends StatelessWidget {
  const ProfileSloganCard({
    super.key,
    required this.isDark,
    required this.bio,
    this.onTap,
  });

  final bool isDark;
  final String? bio;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final text = bio?.trim() ?? '';
    if (text.isEmpty) {
      return const SizedBox.shrink();
    }
    final accent = AppColors.iosAccent(context);
    final surface = accent.withValues(alpha: isDark ? 0.16 : 0.07);
    final border = accent.withValues(alpha: isDark ? 0.16 : 0.08);
    final card = Container(
      key: const ValueKey<String>('profile-slogan-card'),
      width: double.infinity,
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.containerXs,
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
                fontSize: AppTypography.iosSubheadline,
                height: AppSpacing.textLineHeightFootnote,
                color: accent.withValues(alpha: isDark ? 0.92 : 0.88),
                letterSpacing: -0.08,
              ),
            ),
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          Icon(
            CupertinoIcons.sparkles,
            size: AppSpacing.iconSmall,
            color: accent.withValues(alpha: isDark ? 0.88 : 0.78),
          ),
        ],
      ),
    );
    if (onTap == null) {
      return card;
    }
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: card,
    );
  }
}
