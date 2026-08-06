import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_view_data.dart';
import 'package:quwoquan_app/design_system/object_page/object_stats_row.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/formatters/compact_count_formatter.dart';

/// 用户主页统计行 —— 共享 [ObjectStatsRow] 的薄封装。
///
/// 真相源已下沉到 `object_page/object_stats_row.dart`；此处把 [PersonaProfileViewData]
/// 映射为粉丝/关注/获赞/圈子四项 [ObjectStatItem]，保留 `profile-stats-inline-row` 根 key
/// 与既有点击分发顺序（fans/following/likes/circles）。
class ProfileStatsRow extends StatelessWidget {
  const ProfileStatsRow({
    super.key,
    required this.isDark,
    required this.profile,
    this.onStatTap,
  });

  final bool isDark;
  final PersonaProfileViewData? profile;
  final void Function(String type)? onStatTap;

  @override
  Widget build(BuildContext context) {
    final subject = profile;
    final items = <ObjectStatItem>[
      ObjectStatItem(
        value: formatCompactActionCount(subject?.followerCount ?? 0),
        label: ProfileText.profileStatFollowers,
        type: 'fans',
      ),
      ObjectStatItem(
        value: formatCompactActionCount(subject?.followingCount ?? 0),
        label: FoundationText.follow,
        type: 'following',
      ),
      ObjectStatItem(
        value: formatCompactActionCount(subject?.likeCount ?? 0),
        label: CommunityText.circleLikes,
        type: 'likes',
      ),
      ObjectStatItem(
        value: formatCompactActionCount(subject?.circleCount ?? 0),
        label: ChatText.contactsTabCircles,
        type: 'circles',
      ),
    ];
    return ObjectStatsRow(
      isDark: isDark,
      items: items,
      onStatTap: onStatTap,
      rowKey: const ValueKey<String>('profile-stats-inline-row'),
    );
  }
}
