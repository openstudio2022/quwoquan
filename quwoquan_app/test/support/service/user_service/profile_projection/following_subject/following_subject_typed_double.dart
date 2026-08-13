import 'package:quwoquan_app/service/user_service/profile_projection/following_subject/application/public/following_subject_reader.dart';
import 'package:quwoquan_app/service/user_service/relationship/followed_subject_visit_state/application/public/followed_subject_visit_state_writer.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Alpha-only 关注主体读面与访问回执；状态只来自不可变 contract fixture。
final class InMemoryFollowingSubjectFacet
    implements FollowingSubjectReader, FollowedSubjectVisitStateWriter {
  InMemoryFollowingSubjectFacet({
    Map<String, Object?>? followingSubjectWireExample,
  }) : _items = _load(
         followingSubjectWireExample ?? _followingSubjectWireExample(),
       );

  final List<FollowingSubjectItemView> _items;

  static List<FollowingSubjectItemView> _load(Map<String, Object?> seed) {
    final rawItems = seed['items'];
    if (rawItems is! List<Object?>) {
      throw const FormatException(
        'user/profile_projection/following_subject_core.items must be an array',
      );
    }
    return decodeFollowingSubjectSlice(<String, Object?>{
      'items': rawItems,
    }).items.toList(growable: true);
  }

  @override
  Future<FollowingSubjectSlice> listFollowingSubjects(
    ListFollowingSubjectsQuery query,
  ) async {
    final filtered = _items
        .where(
          (item) =>
              query.subjectType == null ||
              item.subjectType == query.subjectType,
        )
        .toList(growable: false);
    final start = int.tryParse(query.cursor?.trim() ?? '') ?? 0;
    final safeStart = start.clamp(0, filtered.length);
    final limit = query.limit.clamp(1, 100);
    final end = (safeStart + limit).clamp(0, filtered.length);
    return FollowingSubjectSlice(
      items: filtered.sublist(safeStart, end),
      nextCursor: end < filtered.length ? '$end' : null,
    );
  }

  @override
  Future<FollowedSubjectVisitResult> markFollowedSubjectVisited(
    MarkFollowedSubjectVisitedCommand command,
  ) async {
    final index = _items.indexWhere(
      (item) =>
          item.subjectId == command.subjectId &&
          item.subjectType == command.subjectType,
    );
    if (index < 0) {
      throw StateError('following subject not found');
    }
    final current = _items[index];
    final visitedAt = command.visitedAt.toUtc();
    _items[index] = FollowingSubjectItemView(
      subjectId: current.subjectId,
      subjectType: current.subjectType,
      displayName: current.displayName,
      avatarUrl: current.avatarUrl,
      coverUrl: current.coverUrl,
      subtitle: current.subtitle,
      targetRouteId: current.targetRouteId,
      targetObjectId: current.targetObjectId,
      followedAt: current.followedAt,
      lastVisitedAt: visitedAt,
      latestChangedAt: current.latestChangedAt,
      unreadChangeCount: 0,
      hasUnreadChanges: false,
      latestChangeReason: current.latestChangeReason,
    );
    return FollowedSubjectVisitResult(
      subjectId: command.subjectId,
      subjectType: command.subjectType,
      lastVisitedAt: visitedAt,
      hasUnreadChanges: false,
    );
  }
}

Map<String, Object?> _followingSubjectWireExample() => <String, Object?>{
  'items': const <Map<String, Object?>>[
    <String, Object?>{
      'subjectId': 'user_travel_photographer',
      'subjectType': 'persona',
      'displayName': '旅行摄影师',
      'avatarUrl':
          'media/avatar/s/archived-avatar/user/fixture_user_photo/v1/avatar.png',
      'coverUrl': '',
      'subtitle': '对象级动态',
      'targetRouteId': 'persona_detail',
      'targetObjectId': 'user_travel_photographer',
      'followedAt': '2026-05-20T08:00:00Z',
      'lastVisitedAt': '2026-06-01T08:00:00Z',
      'latestChangedAt': '2026-06-02T00:30:00Z',
      'unreadChangeCount': 1,
      'hasUnreadChanges': true,
      'latestChangeReason': '发布了新内容',
    },
    <String, Object?>{
      'subjectId': 'circle_sichuan_travel',
      'subjectType': 'circle',
      'displayName': '四川旅行圈',
      'avatarUrl': '',
      'coverUrl':
          'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
      'subtitle': '对象级动态',
      'targetRouteId': 'circle_detail',
      'targetObjectId': 'circle_sichuan_travel',
      'followedAt': '2026-05-20T08:00:00Z',
      'lastVisitedAt': '2026-06-01T08:00:00Z',
      'latestChangedAt': '2026-06-02T00:30:00Z',
      'unreadChangeCount': 0,
      'hasUnreadChanges': false,
      'latestChangeReason': '',
    },
  ],
};
