import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../object_scenario_seed_reader.dart';

/// Alpha-only 关注主体读面与访问回执；状态只来自不可变 contract fixture。
final class AlphaFollowingSubjectFacet
    implements FollowingSubjectQuery, FollowedSubjectVisitCommandWriter {
  AlphaFollowingSubjectFacet({ObjectScenarioSeedReader? fixtures})
    : _items = _load(fixtures ?? objectScenarioSeedReader);

  final List<FollowingSubjectResult> _items;

  static List<FollowingSubjectResult> _load(ObjectScenarioSeedReader fixtures) {
    final seed = fixtures.requireSeedSet('user', 'following_subject_core');
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
    _items[index] = FollowingSubjectResult(
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
