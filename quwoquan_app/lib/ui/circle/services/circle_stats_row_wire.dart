import 'package:quwoquan_app/ui/circle/models/circle_stats_list_view_data.dart';

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
  final id = (dm['_id'] ?? dm['id'] ?? '').toString();
  final mc = dm['memberCount'];
  final label = mc is num
      ? mc.toString()
      : (dm['memberCountLabel'] ?? '—').toString();
  return CircleStatsGroupRowViewData(
    id: id.isNotEmpty ? id : 'g_unknown',
    name: (dm['name'] ?? '').toString(),
    memberCountLabel: label,
  );
}
