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
  isFollowed: false,
);

CircleStatsMemberRowViewData circleStatsMemberRowFromWireMap(
  Map<String, Object?> m,
) {
  final dm = Map<String, dynamic>.from(m);
  final id = (dm['userId'] ?? '').toString();
  return CircleStatsMemberRowViewData(
    id: id.isNotEmpty ? id : 'unknown',
    name: (dm['displayName'] ?? id).toString(),
    avatarUrl: (dm['avatarUrl'] ?? '').toString(),
    worksCountLabel: (dm['worksCountLabel'] ?? '—').toString(),
    fansCountLabel: (dm['fansCountLabel'] ?? '—').toString(),
    likesCountLabel: (dm['likesCountLabel'] ?? '—').toString(),
    isFollowed: dm['isFollowed'] as bool? ?? false,
  );
}

CircleStatsGroupRowViewData circleStatsGroupRowFromGroupSlice(
  CircleGroupSlice group,
) => CircleStatsGroupRowViewData(
  id: group.groupId,
  name: group.name,
  memberCountLabel: group.memberCount.toString(),
);
