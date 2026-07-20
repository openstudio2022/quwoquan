import '../operation_request_payload.dart';

abstract interface class FollowingSubjectQuery {
  Future<FollowingSubjectSlice> listFollowingSubjects(
    ListFollowingSubjectsQuery query,
  );
}

abstract interface class FollowedSubjectVisitCommandWriter {
  Future<FollowedSubjectVisitResult> markFollowedSubjectVisited(
    MarkFollowedSubjectVisitedCommand command,
  );
}

final class ListFollowingSubjectsQuery {
  const ListFollowingSubjectsQuery({
    this.cursor,
    this.limit = 20,
    this.subjectType,
  });

  final String? cursor;
  final int limit;
  final String? subjectType;
}

final class MarkFollowedSubjectVisitedCommand {
  MarkFollowedSubjectVisitedCommand({
    required String subjectId,
    required String subjectType,
    required this.visitedAt,
    this.clientRequestId,
  }) : subjectId = _required(subjectId, 'subjectId'),
       subjectType = _required(subjectType, 'subjectType');

  final String subjectId;
  final String subjectType;
  final DateTime visitedAt;
  final String? clientRequestId;
}

final class FollowingSubjectResult {
  const FollowingSubjectResult({
    required this.subjectId,
    required this.subjectType,
    required this.displayName,
    required this.targetRouteId,
    required this.targetObjectId,
    required this.followedAt,
    required this.unreadChangeCount,
    required this.hasUnreadChanges,
    this.avatarUrl = '',
    this.coverUrl = '',
    this.subtitle = '',
    this.lastVisitedAt,
    this.latestChangedAt,
    this.latestChangeReason = '',
  });

  final String subjectId;
  final String subjectType;
  final String displayName;
  final String avatarUrl;
  final String coverUrl;
  final String subtitle;
  final String targetRouteId;
  final String targetObjectId;
  final DateTime followedAt;
  final DateTime? lastVisitedAt;
  final DateTime? latestChangedAt;
  final int unreadChangeCount;
  final bool hasUnreadChanges;
  final String latestChangeReason;
}

final class FollowingSubjectSlice {
  const FollowingSubjectSlice({required this.items, this.nextCursor});

  final List<FollowingSubjectResult> items;
  final String? nextCursor;
}

final class FollowedSubjectVisitResult {
  const FollowedSubjectVisitResult({
    required this.subjectId,
    required this.subjectType,
    required this.lastVisitedAt,
    required this.hasUnreadChanges,
  });

  final String subjectId;
  final String subjectType;
  final DateTime lastVisitedAt;
  final bool hasUnreadChanges;
}

CloudOperationRequestPayload encodeListFollowingSubjectsQuery(
  ListFollowingSubjectsQuery query,
) {
  final cursor = query.cursor?.trim() ?? '';
  final subjectType = query.subjectType?.trim() ?? '';
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (cursor.isNotEmpty) 'cursor': cursor,
      'limit': '${query.limit.clamp(1, 100)}',
      if (subjectType.isNotEmpty) 'subjectType': subjectType,
    },
  );
}

CloudOperationRequestPayload encodeMarkFollowedSubjectVisitedCommand(
  MarkFollowedSubjectVisitedCommand command,
) {
  final requestId = command.clientRequestId?.trim() ?? '';
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      'subjectType': command.subjectType,
      'subjectId': command.subjectId,
    },
    body: <String, Object?>{
      'subjectId': command.subjectId,
      'subjectType': command.subjectType,
      'visitedAt': command.visitedAt.toUtc().toIso8601String(),
      if (requestId.isNotEmpty) 'clientRequestId': requestId,
    },
  );
}

FollowingSubjectSlice decodeFollowingSubjectSlice(Object? response) {
  final root = _object(response, 'FollowingSubjectSlice');
  final rawItems = root['items'];
  if (rawItems is! List<Object?>) {
    throw const FormatException(
      'FollowingSubjectSlice.items must be a JSON array',
    );
  }
  return FollowingSubjectSlice(
    items: rawItems
        .map<FollowingSubjectResult>((raw) {
          final item = _object(raw, 'FollowingSubjectResult');
          return FollowingSubjectResult(
            subjectId: _requiredField(item, 'subjectId'),
            subjectType: _requiredField(item, 'subjectType'),
            displayName: _requiredField(item, 'displayName'),
            avatarUrl: _optionalString(item['avatarUrl']) ?? '',
            coverUrl: _optionalString(item['coverUrl']) ?? '',
            subtitle: _optionalString(item['subtitle']) ?? '',
            targetRouteId: _requiredField(item, 'targetRouteId'),
            targetObjectId: _requiredField(item, 'targetObjectId'),
            followedAt: _requiredTimestamp(item, 'followedAt'),
            lastVisitedAt: _optionalTimestamp(item['lastVisitedAt']),
            latestChangedAt: _optionalTimestamp(item['latestChangedAt']),
            unreadChangeCount: _integer(item['unreadChangeCount']),
            hasUnreadChanges: item['hasUnreadChanges'] == true,
            latestChangeReason:
                _optionalString(item['latestChangeReason']) ?? '',
          );
        })
        .toList(growable: false),
    nextCursor:
        _optionalString(root['nextCursor']) ?? _optionalString(root['cursor']),
  );
}

FollowedSubjectVisitResult decodeFollowedSubjectVisitResult(Object? response) {
  final root = _object(response, 'FollowedSubjectVisitResult');
  return FollowedSubjectVisitResult(
    subjectId: _requiredField(root, 'subjectId'),
    subjectType: _requiredField(root, 'subjectType'),
    lastVisitedAt: _requiredTimestamp(root, 'lastVisitedAt'),
    hasUnreadChanges: root['hasUnreadChanges'] == true,
  );
}

Map<Object?, Object?> _object(Object? value, String name) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$name must be a JSON object');
  }
  return value;
}

String _requiredField(Map<Object?, Object?> root, String key) {
  final value = _optionalString(root[key]);
  if (value == null) {
    throw FormatException('missing required field "$key"');
  }
  return value;
}

String? _optionalString(Object? value) {
  final text = value is String ? value.trim() : '';
  return text.isEmpty ? null : text;
}

int _integer(Object? value) => value is num ? value.toInt() : 0;

DateTime _requiredTimestamp(Map<Object?, Object?> root, String key) {
  final value = _requiredField(root, key);
  return DateTime.parse(value).toUtc();
}

DateTime? _optionalTimestamp(Object? value) {
  final text = _optionalString(value);
  return text == null ? null : DateTime.parse(text).toUtc();
}

String _required(String value, String name) {
  final text = value.trim();
  if (text.isEmpty) {
    throw ArgumentError.value(value, name, 'must not be empty');
  }
  return text;
}
