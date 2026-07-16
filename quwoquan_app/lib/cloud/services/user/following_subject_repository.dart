import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/contract_fixture_runtime_loader.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/following_subject_item_view_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/following_subject_visit_result_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/mark_following_subject_visited_request_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

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

class MockFollowingSubjectRepository implements FollowingSubjectRepository {
  MockFollowingSubjectRepository()
    : _items = _loadContractSeedItems().toList(growable: true);

  final List<FollowingSubjectItem> _items;

  static Iterable<FollowingSubjectItem> _loadContractSeedItems() {
    final fixture = ContractFixtureRuntimeLoader.followingSubjectSeedSet();
    final rawItems = fixture?['items'];
    if (rawItems is! List) {
      return const <FollowingSubjectItem>[];
    }
    return rawItems.whereType<Map>().map((item) {
      return FollowingSubjectItem.fromDto(
        FollowingSubjectItemViewDto.fromMap(item.cast<String, dynamic>()),
      );
    });
  }

  @override
  Future<List<FollowingSubjectItem>> listFollowingSubjects({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    FollowingSubjectType? subjectType,
  }) async {
    return _items
        .where((item) => subjectType == null || item.subjectType == subjectType)
        .take(limit)
        .toList(growable: false);
  }

  @override
  Future<FollowingSubjectVisitResult> markFollowingSubjectVisited({
    required FollowingSubjectItem subject,
    DateTime? visitedAt,
    String? clientRequestId,
  }) async {
    final visitedIso = (visitedAt ?? DateTime.now().toUtc()).toIso8601String();
    final index = _items.indexWhere(
      (item) =>
          item.subjectId == subject.subjectId &&
          item.subjectType == subject.subjectType,
    );
    if (index >= 0) {
      _items[index] = _items[index].copyWith(
        hasUnreadChanges: false,
        unreadChangeCount: 0,
        lastVisitedAt: visitedIso,
      );
    }
    return FollowingSubjectVisitResult(
      subjectId: subject.subjectId,
      subjectType: subject.subjectType,
      lastVisitedAt: visitedIso,
      hasUnreadChanges: false,
    );
  }
}

class RemoteFollowingSubjectRepository implements FollowingSubjectRepository {
  RemoteFollowingSubjectRepository({
    CloudHttpClient? httpClient,
    String? baseUrl,
  }) : _httpClient = httpClient ?? CloudHttpClient(),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  Uri _uri(String path, {Map<String, String>? queryParameters}) {
    return Uri.parse(
      '$_baseUrl$path',
    ).replace(queryParameters: queryParameters);
  }

  @override
  Future<List<FollowingSubjectItem>> listFollowingSubjects({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    FollowingSubjectType? subjectType,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (cursor != null && cursor.isNotEmpty) {
      query['cursor'] = cursor;
    }
    if (subjectType != null) {
      query['subjectType'] = subjectType.name;
    }
    final response = await _httpClient.getJson(
      _uri(UserApiMetadata.listFollowingSubjectsPath, queryParameters: query),
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.listFollowingSubjects,
      ),
    );
    final page = CloudResponseDecoder.asCursorPage(
      response,
      context: UserApiMetadata.listFollowingSubjectsPath,
    );
    return page.items
        .map(FollowingSubjectItemViewDto.fromMap)
        .map(FollowingSubjectItem.fromDto)
        .toList(growable: false);
  }

  @override
  Future<FollowingSubjectVisitResult> markFollowingSubjectVisited({
    required FollowingSubjectItem subject,
    DateTime? visitedAt,
    String? clientRequestId,
  }) async {
    final visitedIso = (visitedAt ?? DateTime.now().toUtc()).toIso8601String();
    final request = MarkFollowingSubjectVisitedRequestDto(
      subjectId: subject.subjectId,
      subjectType: subject.subjectTypeWire,
      visitedAt: visitedIso,
      clientRequestId: clientRequestId ?? '',
    );
    final response = await _httpClient.postJson(
      _uri(
        UserApiMetadata.markFollowedSubjectVisitedPath(
          subjectType: subject.subjectTypeWire,
          subjectId: subject.subjectId,
        ),
      ),
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.markFollowedSubjectVisited,
      ),
      body: request.toMap(),
    );
    final obj = CloudResponseDecoder.asObject(
      response,
      context: UserApiMetadata.markFollowedSubjectVisitedPath(
        subjectType: subject.subjectTypeWire,
        subjectId: subject.subjectId,
      ),
    );
    return FollowingSubjectVisitResult.fromDto(
      FollowingSubjectVisitResultDto.fromMap(obj),
    );
  }
}
