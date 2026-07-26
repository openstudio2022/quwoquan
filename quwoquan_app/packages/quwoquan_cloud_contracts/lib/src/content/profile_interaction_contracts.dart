import '../operation_request_payload.dart';

enum ContentProfileInteractionDirection {
  received('received'),
  sent('sent');

  const ContentProfileInteractionDirection(this.wireValue);
  final String wireValue;
}

enum ContentProfileInteractionType {
  like('like'),
  comment('comment'),
  share('share');

  const ContentProfileInteractionType(this.wireValue);
  final String wireValue;
}

enum ContentProfileInteractionReadState {
  seen('seen'),
  read('read');

  const ContentProfileInteractionReadState(this.wireValue);
  final String wireValue;
}

final class ContentProfileInteractionPageQuery {
  ContentProfileInteractionPageQuery({
    required String subAccountId,
    required this.type,
    this.cursor,
    this.limit = 20,
  }) : subAccountId = _requiredText(subAccountId, 'subAccountId') {
    if (limit <= 0 || limit > 50) {
      throw ArgumentError.value(limit, 'limit', 'must be between 1 and 50');
    }
  }

  final String subAccountId;
  final ContentProfileInteractionType type;
  final String? cursor;
  final int limit;
}

final class ContentProfileInteractionActivity {
  ContentProfileInteractionActivity({
    required this.activityId,
    required this.activityType,
    required this.direction,
    this.commentKind = 'none',
    this.commentId = '',
    this.parentCommentId = '',
    this.viewerReaction = 'none',
    required this.actorSubAccountId,
    required this.actorDisplayName,
    this.actorAvatarUrl = '',
    this.actorAvatarVersion = 0,
    this.counterpartSubAccountId = '',
    this.counterpartDisplayName = '',
    this.counterpartAvatarUrl = '',
    required this.targetSubAccountId,
    required this.targetContentId,
    required this.targetContentType,
    this.targetContentSummary = '',
    this.targetKind = 'record',
    this.targetAvailability = 'active',
    this.targetReplyCount = 0,
    required this.displaySubAccountId,
    required this.displayName,
    this.displayAvatarUrl = '',
    this.displayAvatarVersion = 0,
    this.displayUserRouteId = '',
    required this.primaryText,
    this.contextText = '',
    this.previewMediaKind = 'none',
    this.previewImageUrl = '',
    this.previewText = '',
    this.previewUnavailable = false,
    this.previewObjectId = '',
    this.previewRouteId = '',
    this.outboundShareEventId = '',
    this.shareText = '',
    this.impactPrimaryText = '',
    this.impactDeepLink = '',
    Iterable<String> filterKeys = const <String>[],
    required this.createdAt,
    required this.occurredAt,
    this.seenAt,
    this.readAt,
  }) : filterKeys = List<String>.unmodifiable(filterKeys);

  final String activityId;
  final String activityType;
  final String direction;
  final String commentKind;
  final String commentId;
  final String parentCommentId;
  final String viewerReaction;
  final String actorSubAccountId;
  final String actorDisplayName;
  final String actorAvatarUrl;
  final int actorAvatarVersion;
  final String counterpartSubAccountId;
  final String counterpartDisplayName;
  final String counterpartAvatarUrl;
  final String targetSubAccountId;
  final String targetContentId;
  final String targetContentType;
  final String targetContentSummary;
  final String targetKind;
  final String targetAvailability;
  final int targetReplyCount;
  final String displaySubAccountId;
  final String displayName;
  final String displayAvatarUrl;
  final int displayAvatarVersion;
  final String displayUserRouteId;
  final String primaryText;
  final String contextText;
  final String previewMediaKind;
  final String previewImageUrl;
  final String previewText;
  final bool previewUnavailable;
  final String previewObjectId;
  final String previewRouteId;
  final String outboundShareEventId;
  final String shareText;
  final String impactPrimaryText;
  final String impactDeepLink;
  final List<String> filterKeys;
  final DateTime createdAt;
  final DateTime occurredAt;
  final DateTime? seenAt;
  final DateTime? readAt;
}

final class ContentProfileInteractionPage {
  ContentProfileInteractionPage({
    required Iterable<ContentProfileInteractionActivity> items,
    this.nextCursor,
    this.hasMore = false,
  }) : items = List<ContentProfileInteractionActivity>.unmodifiable(items);

  final List<ContentProfileInteractionActivity> items;
  final String? nextCursor;
  final bool hasMore;
}

final class AppendContentProfileInteractionReadFactCommand {
  AppendContentProfileInteractionReadFactCommand({
    required String subAccountId,
    required String activityId,
    required this.state,
  }) : subAccountId = _requiredText(subAccountId, 'subAccountId'),
       activityId = _requiredText(activityId, 'activityId');

  final String subAccountId;
  final String activityId;
  final ContentProfileInteractionReadState state;
}

final class ContentProfileInteractionReadFactAck {
  const ContentProfileInteractionReadFactAck({
    required this.factId,
    required this.activityId,
    required this.state,
    required this.occurredAt,
    required this.replayed,
  });

  final String factId;
  final String activityId;
  final String state;
  final DateTime occurredAt;
  final bool replayed;
}

abstract interface class ContentProfileInteractionQueryFacet {
  Future<ContentProfileInteractionPage> listActivities(
    ContentProfileInteractionPageQuery query, {
    required ContentProfileInteractionDirection direction,
  });
}

abstract interface class ContentProfileInteractionReadFactAppendFacet {
  Future<ContentProfileInteractionReadFactAck> appendReadFact(
    AppendContentProfileInteractionReadFactCommand command,
  );
}

CloudOperationRequestPayload encodeContentProfileInteractionPageQuery(
  ContentProfileInteractionPageQuery query,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'subAccountId': query.subAccountId},
  queryParameters: <String, String>{
    'type': query.type.wireValue,
    if (_optionalText(query.cursor) case final cursor?) 'cursor': cursor,
    'limit': '${query.limit}',
  },
);

CloudOperationRequestPayload encodeAppendContentProfileInteractionReadFactCommand(
  AppendContentProfileInteractionReadFactCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{
    'subAccountId': command.subAccountId,
    'interactionId': command.activityId,
  },
  body: <String, Object?>{'state': command.state.wireValue},
);

ContentProfileInteractionPage decodeContentProfileInteractionPage(Object? value) {
  final root = _object(value, 'ContentProfileInteractionPage');
  return ContentProfileInteractionPage(
    items: _list(root['items'], 'ContentProfileInteractionPage.items').map(
      decodeContentProfileInteractionActivity,
    ),
    nextCursor: _optionalText(root['nextCursor']),
    hasMore: _optionalBool(root['hasMore']) ?? false,
  );
}

ContentProfileInteractionReadFactAck decodeContentProfileInteractionReadFactAck(
  Object? value,
) {
  final root = _object(value, 'ContentProfileInteractionReadFactAck');
  return ContentProfileInteractionReadFactAck(
    factId: _requiredText(root['factId'], 'factId'),
    activityId: _requiredText(root['activityId'], 'activityId'),
    state: _requiredText(root['state'], 'state'),
    occurredAt: _requiredDateTime(root['occurredAt'], 'occurredAt'),
    replayed: _requiredBool(root['replayed'], 'replayed'),
  );
}

ContentProfileInteractionActivity decodeContentProfileInteractionActivity(
  Object? value,
) {
  final row = _object(value, 'ContentProfileInteractionActivity');
  return ContentProfileInteractionActivity(
    activityId: _requiredText(row['activityId'], 'activityId'),
    activityType: _requiredText(row['activityType'], 'activityType'),
    direction: _requiredText(row['direction'], 'direction'),
    commentKind: _optionalText(row['commentKind']) ?? 'none',
    commentId: _optionalText(row['commentId']) ?? '',
    parentCommentId: _optionalText(row['parentCommentId']) ?? '',
    viewerReaction: _optionalText(row['viewerReaction']) ?? 'none',
    actorSubAccountId: _requiredText(
      row['actorSubAccountId'],
      'actorSubAccountId',
    ),
    actorDisplayName: _requiredText(
      row['actorDisplayName'],
      'actorDisplayName',
    ),
    actorAvatarUrl: _optionalText(row['actorAvatarUrl']) ?? '',
    actorAvatarVersion: _optionalInt(row['actorAvatarVersion']) ?? 0,
    counterpartSubAccountId:
        _optionalText(row['counterpartSubAccountId']) ?? '',
    counterpartDisplayName:
        _optionalText(row['counterpartDisplayName']) ?? '',
    counterpartAvatarUrl: _optionalText(row['counterpartAvatarUrl']) ?? '',
    targetSubAccountId: _requiredText(
      row['targetSubAccountId'],
      'targetSubAccountId',
    ),
    targetContentId: _requiredText(row['targetContentId'], 'targetContentId'),
    targetContentType: _requiredText(
      row['targetContentType'],
      'targetContentType',
    ),
    targetContentSummary: _optionalText(row['targetContentSummary']) ?? '',
    targetKind: _optionalText(row['targetKind']) ?? 'record',
    targetAvailability:
        _optionalText(row['targetAvailability']) ?? 'active',
    targetReplyCount: _optionalInt(row['targetReplyCount']) ?? 0,
    displaySubAccountId: _requiredText(
      row['displaySubAccountId'],
      'displaySubAccountId',
    ),
    displayName: _requiredText(row['displayName'], 'displayName'),
    displayAvatarUrl: _optionalText(row['displayAvatarUrl']) ?? '',
    displayAvatarVersion: _optionalInt(row['displayAvatarVersion']) ?? 0,
    displayUserRouteId: _optionalText(row['displayUserRouteId']) ?? '',
    primaryText: _requiredText(row['primaryText'], 'primaryText'),
    contextText: _optionalText(row['contextText']) ?? '',
    previewMediaKind: _optionalText(row['previewMediaKind']) ?? 'none',
    previewImageUrl: _optionalText(row['previewImageUrl']) ?? '',
    previewText: _optionalText(row['previewText']) ?? '',
    previewUnavailable: _optionalBool(row['previewUnavailable']) ?? false,
    previewObjectId: _optionalText(row['previewObjectId']) ?? '',
    previewRouteId: _optionalText(row['previewRouteId']) ?? '',
    outboundShareEventId: _optionalText(row['outboundShareEventId']) ?? '',
    shareText: _optionalText(row['shareText']) ?? '',
    impactPrimaryText: _optionalText(row['impactPrimaryText']) ?? '',
    impactDeepLink: _optionalText(row['impactDeepLink']) ?? '',
    filterKeys: _stringList(row['filterKeys'], 'filterKeys'),
    createdAt: _requiredDateTime(row['createdAt'], 'createdAt'),
    occurredAt: _requiredDateTime(row['occurredAt'], 'occurredAt'),
    seenAt: _optionalDateTime(row['seenAt'], 'seenAt'),
    readAt: _optionalDateTime(row['readAt'], 'readAt'),
  );
}

Map<String, Object?> _object(Object? value, String context) {
  if (value is! Map) {
    throw FormatException('$context must be an object');
  }
  return value.map((key, item) => MapEntry(key.toString(), item));
}

List<Object?> _list(Object? value, String context) {
  if (value is! List) {
    throw FormatException('$context must be a list');
  }
  return value.cast<Object?>();
}

List<String> _stringList(Object? value, String context) {
  if (value == null) {
    return const <String>[];
  }
  return _list(value, context)
      .map((item) {
        if (item is! String) {
          throw FormatException('$context must contain strings');
        }
        return item.trim();
      })
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

String _requiredText(Object? value, String name) {
  final text = _optionalText(value);
  if (text == null) {
    throw FormatException('$name must be a non-empty string');
  }
  return text;
}

String? _optionalText(Object? value) {
  if (value == null) {
    return null;
  }
  if (value is! String) {
    throw const FormatException('Expected a string value');
  }
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
}

int? _optionalInt(Object? value) {
  if (value == null) {
    return null;
  }
  if (value is num) {
    return value.toInt();
  }
  if (value is String) {
    return int.tryParse(value.trim());
  }
  throw const FormatException('Expected an integer value');
}

bool _requiredBool(Object? value, String name) {
  final parsed = _optionalBool(value);
  if (parsed == null) {
    throw FormatException('$name must be a boolean');
  }
  return parsed;
}

bool? _optionalBool(Object? value) {
  if (value == null) {
    return null;
  }
  if (value is bool) {
    return value;
  }
  throw const FormatException('Expected a boolean value');
}

DateTime _requiredDateTime(Object? value, String name) {
  final parsed = _optionalDateTime(value, name);
  if (parsed == null) {
    throw FormatException('$name must be an ISO-8601 timestamp');
  }
  return parsed;
}

DateTime? _optionalDateTime(Object? value, String name) {
  if (value == null) {
    return null;
  }
  if (value is! String) {
    throw FormatException('$name must be an ISO-8601 timestamp');
  }
  final parsed = DateTime.tryParse(value.trim());
  if (parsed == null) {
    throw FormatException('$name must be an ISO-8601 timestamp');
  }
  return parsed.toUtc();
}
