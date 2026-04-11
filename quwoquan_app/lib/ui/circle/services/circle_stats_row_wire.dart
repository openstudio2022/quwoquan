import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_group_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_member_roster_item_dto.dart';
import 'package:quwoquan_app/ui/circle/models/circle_stats_list_view_data.dart';

CircleStatsMemberRowViewData circleStatsMemberRowFromRosterItem(
  CircleMemberRosterItemDto r,
) {
  final id = r.userId.isNotEmpty ? r.userId : r.membershipId;
  return CircleStatsMemberRowViewData(
    id: id.isNotEmpty ? id : 'unknown',
    name: (r.displayName ?? id).toString(),
    avatarUrl: (r.avatarUrl ?? '').toString(),
    worksCountLabel: (r.worksCountLabel ?? '—').toString(),
    fansCountLabel: (r.fansCountLabel ?? '—').toString(),
    likesCountLabel: (r.likesCountLabel ?? '—').toString(),
    isFollowed: r.isFollowed,
  );
}

CircleStatsMemberRowViewData circleStatsMemberRowFromWireMap(
  Map<String, Object?> m,
) {
  final dm = Map<String, dynamic>.from(m);
  final id = (dm['userId'] ?? dm['id'] ?? '').toString();
  return CircleStatsMemberRowViewData(
    id: id.isNotEmpty ? id : 'unknown',
    name: (dm['displayName'] ?? dm['name'] ?? id).toString(),
    avatarUrl: (dm['avatarUrl'] ?? dm['avatar'] ?? '').toString(),
    worksCountLabel:
        (dm['worksCountLabel'] ?? dm['worksCount'] ?? '—').toString(),
    fansCountLabel: (dm['fansCountLabel'] ?? dm['fansCount'] ?? '—').toString(),
    likesCountLabel:
        (dm['likesCountLabel'] ?? dm['likesCount'] ?? '—').toString(),
    isFollowed: dm['isFollowed'] as bool? ?? false,
  );
}

CircleStatsGroupRowViewData circleStatsGroupRowFromWireMap(
  Map<String, Object?> m,
) {
  final dm = Map<String, dynamic>.from(m);
  return circleStatsGroupRowFromGroupDto(CircleGroupDto.fromMap(dm));
}

CircleStatsGroupRowViewData circleStatsGroupRowFromGroupDto(CircleGroupDto g) {
  final label = g.memberCount.toString();
  return CircleStatsGroupRowViewData(
    id: g.id.isNotEmpty ? g.id : 'g_unknown',
    name: g.name,
    memberCountLabel: label,
  );
}
