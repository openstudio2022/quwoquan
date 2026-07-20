import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/following_subject_item_view_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/following_subject_visit_result_dto.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

enum FollowingSubjectType {
  user,
  circle,
  homepage;

  static FollowingSubjectType fromWire(String value) {
    return switch (value.trim()) {
      'circle' => FollowingSubjectType.circle,
      'homepage' => FollowingSubjectType.homepage,
      _ => FollowingSubjectType.user,
    };
  }
}

class FollowingSubjectItem {
  const FollowingSubjectItem({
    required this.subjectId,
    required this.subjectType,
    required this.displayName,
    required this.targetRouteId,
    required this.targetObjectId,
    required this.followedAt,
    required this.hasUnreadChanges,
    this.avatarUrl = '',
    this.coverUrl = '',
    this.subtitle = '',
    this.lastVisitedAt = '',
    this.latestChangedAt = '',
    this.unreadChangeCount = 0,
    this.latestChangeReason = '',
  });

  factory FollowingSubjectItem.fromDto(FollowingSubjectItemViewDto dto) {
    return FollowingSubjectItem(
      subjectId: dto.subjectId,
      subjectType: FollowingSubjectType.fromWire(dto.subjectType),
      displayName: dto.displayName,
      avatarUrl: dto.avatarUrl,
      coverUrl: dto.coverUrl,
      subtitle: dto.subtitle,
      targetRouteId: dto.targetRouteId,
      targetObjectId: dto.targetObjectId.isNotEmpty
          ? dto.targetObjectId
          : dto.subjectId,
      followedAt: dto.followedAt,
      lastVisitedAt: dto.lastVisitedAt,
      latestChangedAt: dto.latestChangedAt,
      unreadChangeCount: dto.unreadChangeCount,
      hasUnreadChanges: dto.hasUnreadChanges,
      latestChangeReason: dto.latestChangeReason,
    );
  }

  factory FollowingSubjectItem.fromContract(FollowingSubjectResult result) {
    return FollowingSubjectItem(
      subjectId: result.subjectId,
      subjectType: FollowingSubjectType.fromWire(result.subjectType),
      displayName: result.displayName,
      avatarUrl: result.avatarUrl,
      coverUrl: result.coverUrl,
      subtitle: result.subtitle,
      targetRouteId: result.targetRouteId,
      targetObjectId: result.targetObjectId,
      followedAt: result.followedAt.toUtc().toIso8601String(),
      lastVisitedAt: result.lastVisitedAt?.toUtc().toIso8601String() ?? '',
      latestChangedAt: result.latestChangedAt?.toUtc().toIso8601String() ?? '',
      unreadChangeCount: result.unreadChangeCount,
      hasUnreadChanges: result.hasUnreadChanges,
      latestChangeReason: result.latestChangeReason,
    );
  }

  final String subjectId;
  final FollowingSubjectType subjectType;
  final String displayName;
  final String avatarUrl;
  final String coverUrl;
  final String subtitle;
  final String targetRouteId;
  final String targetObjectId;
  final String followedAt;
  final String lastVisitedAt;
  final String latestChangedAt;
  final int unreadChangeCount;
  final bool hasUnreadChanges;
  final String latestChangeReason;

  String get subjectTypeWire => subjectType.name;
  String get visualUrl => avatarUrl.isNotEmpty ? avatarUrl : coverUrl;

  FollowingSubjectItem copyWith({
    bool? hasUnreadChanges,
    int? unreadChangeCount,
    String? lastVisitedAt,
  }) {
    return FollowingSubjectItem(
      subjectId: subjectId,
      subjectType: subjectType,
      displayName: displayName,
      avatarUrl: avatarUrl,
      coverUrl: coverUrl,
      subtitle: subtitle,
      targetRouteId: targetRouteId,
      targetObjectId: targetObjectId,
      followedAt: followedAt,
      lastVisitedAt: lastVisitedAt ?? this.lastVisitedAt,
      latestChangedAt: latestChangedAt,
      unreadChangeCount: unreadChangeCount ?? this.unreadChangeCount,
      hasUnreadChanges: hasUnreadChanges ?? this.hasUnreadChanges,
      latestChangeReason: latestChangeReason,
    );
  }
}

class FollowingSubjectVisitResult {
  const FollowingSubjectVisitResult({
    required this.subjectId,
    required this.subjectType,
    required this.lastVisitedAt,
    required this.hasUnreadChanges,
  });

  factory FollowingSubjectVisitResult.fromDto(
    FollowingSubjectVisitResultDto dto,
  ) {
    return FollowingSubjectVisitResult(
      subjectId: dto.subjectId,
      subjectType: FollowingSubjectType.fromWire(dto.subjectType),
      lastVisitedAt: dto.lastVisitedAt,
      hasUnreadChanges: dto.hasUnreadChanges,
    );
  }

  factory FollowingSubjectVisitResult.fromContract(
    FollowedSubjectVisitResult result,
  ) {
    return FollowingSubjectVisitResult(
      subjectId: result.subjectId,
      subjectType: FollowingSubjectType.fromWire(result.subjectType),
      lastVisitedAt: result.lastVisitedAt.toUtc().toIso8601String(),
      hasUnreadChanges: result.hasUnreadChanges,
    );
  }

  final String subjectId;
  final FollowingSubjectType subjectType;
  final String lastVisitedAt;
  final bool hasUnreadChanges;
}

abstract class FollowingSubjectRepository {
  Future<List<FollowingSubjectItem>> listFollowingSubjects({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    FollowingSubjectType? subjectType,
  });

  Future<FollowingSubjectVisitResult> markFollowingSubjectVisited({
    required FollowingSubjectItem subject,
    DateTime? visitedAt,
    String? clientRequestId,
  });
}

class RemoteFollowingSubjectRepository implements FollowingSubjectRepository {
  const RemoteFollowingSubjectRepository({
    required this.query,
    required this.visitWriter,
  });

  final FollowingSubjectQuery query;
  final FollowedSubjectVisitCommandWriter visitWriter;

  @override
  Future<List<FollowingSubjectItem>> listFollowingSubjects({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    FollowingSubjectType? subjectType,
  }) async {
    final slice = await query.listFollowingSubjects(
      ListFollowingSubjectsQuery(
        cursor: cursor,
        limit: limit,
        subjectType: subjectType?.name,
      ),
    );
    return slice.items
        .map(FollowingSubjectItem.fromContract)
        .toList(growable: false);
  }

  @override
  Future<FollowingSubjectVisitResult> markFollowingSubjectVisited({
    required FollowingSubjectItem subject,
    DateTime? visitedAt,
    String? clientRequestId,
  }) async {
    final result = await visitWriter.markFollowedSubjectVisited(
      MarkFollowedSubjectVisitedCommand(
        subjectId: subject.subjectId,
        subjectType: subject.subjectTypeWire,
        visitedAt: visitedAt ?? DateTime.now().toUtc(),
        clientRequestId: clientRequestId,
      ),
    );
    return FollowingSubjectVisitResult.fromContract(result);
  }
}
