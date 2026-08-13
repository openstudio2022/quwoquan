import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_stats_list_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

CircleStatsMemberRowViewData circleStatsMemberRowFromMembership(
  CircleMembershipSlice membership,
) => CircleStatsMemberRowViewData(
  id: membership.personaId,
  name: membership.personaId,
  avatarUrl: '',
  worksCountLabel: '—',
  fansCountLabel: '—',
  likesCountLabel: '—',
);

CircleStatsGroupRowViewData circleStatsGroupRowFromGroupSlice(
  CircleGroupSlice group,
) => CircleStatsGroupRowViewData(
  id: group.groupId,
  name: group.name,
  memberCountLabel: group.memberCount.toString(),
  conversationId: (group.conversationId ?? '').trim().isEmpty
      ? null
      : group.conversationId,
);
