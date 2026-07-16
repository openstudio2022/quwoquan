import 'package:quwoquan_app/ui/circle/models/circle_stats_list_view_data.dart';
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
  final id = (dm['userId'] ?? dm['id'] ?? '').toString();
  return CircleStatsMemberRowViewData(
    id: id.isNotEmpty ? id : 'unknown',
    name: (dm['displayName'] ?? dm['name'] ?? id).toString(),
    avatarUrl: (dm['avatarUrl'] ?? dm['avatar'] ?? '').toString(),
    worksCountLabel: (dm['worksCountLabel'] ?? dm['worksCount'] ?? '—')
        .toString(),
    fansCountLabel: (dm['fansCountLabel'] ?? dm['fansCount'] ?? '—').toString(),
    likesCountLabel: (dm['likesCountLabel'] ?? dm['likesCount'] ?? '—')
        .toString(),
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
