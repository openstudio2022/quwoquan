import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';
import 'package:quwoquan_app/components/object_page/profile_ios_components.dart';

class ProfileStatsRow extends StatelessWidget {
  const ProfileStatsRow({
    super.key,
    required this.isDark,
    required this.profile,
    this.onStatTap,
  });

  final bool isDark;
  final SubAccountProfileViewData? profile;
  final void Function(String type)? onStatTap;

  String _formatCount(int count) {
    return formatCompactActionCount(count);
  }

  @override
  Widget build(BuildContext context) {
    final fg = AppColors.iosLabel(context);
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final separator = SettingsSemanticConstants.conversationSheetDividerColor(
      isDark,
    ).withValues(alpha: 0.9);
    final subject = profile;

    // 体验规格四列统计：关注 / 粉丝 / 获赞 / 作品（获赞、作品无列表页，不可点）。
    final items = [
      _StatItem(
        value: _formatCount(subject?.followingCount ?? 0),
        label: UITextConstants.follow,
        type: 'following',
      ),
      _StatItem(
        value: _formatCount(subject?.followerCount ?? 0),
        label: UITextConstants.circleFans,
        type: 'fans',
      ),
      _StatItem(
        value: _formatCount(subject?.likeCount ?? 0),
        label: UITextConstants.circleLikes,
        type: '',
      ),
      _StatItem(
        value: _formatCount(subject?.postCount ?? 0),
        label: UITextConstants.discoveryRailWorks,
        type: '',
      ),
    ];

    return ProfileIosSectionCard(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.containerSm),
      backgroundColor: SettingsSemanticConstants.conversationSheetCardSurface(
        isDark,
      ),
      borderColor: SettingsSemanticConstants.conversationSheetCardBorderColor(
        isDark,
      ),
      child: Row(
        children: <Widget>[
          for (var i = 0; i < items.length; i += 1) ...<Widget>[
            Expanded(
              child: _buildStatCell(items[i], fg, fgSecondary),
            ),
            if (i != items.length - 1)
              Container(
                width: AppSpacing.hairline,
                height: AppSpacing.buttonHeightSm,
                color: separator,
              ),
          ],
        ],
      ),
    );
  }
}

extension on ProfileStatsRow {
  Widget _buildStatCell(_StatItem item, Color fg, Color fgSecondary) {
    final content = Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupXs),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(
            item.value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosTitle3,
              fontWeight: AppTypography.semiBold,
              color: fg,
              letterSpacing: -0.32,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs / 2),
          Text(
            item.label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              fontWeight: AppTypography.medium,
              color: fgSecondary,
            ),
          ),
        ],
      ),
    );
    // 无列表页的列（获赞/作品）渲染为静态格，避免 disabled 按钮的降透明视觉。
    if (onStatTap == null || item.type.isEmpty) {
      return content;
    }
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: () => onStatTap!(item.type),
      child: content,
    );
  }
}

class _StatItem {
  const _StatItem({
    required this.value,
    required this.label,
    required this.type,
  });
  final String value;
  final String label;
  final String type;
}
