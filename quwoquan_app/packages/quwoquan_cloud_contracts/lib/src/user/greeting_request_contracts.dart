import '../operation_request_payload.dart';
part '../generated/requests/user/greeting_request_contracts.requests.g.dart';

abstract interface class GreetingRequestCommandWriter {
  Future<GreetingRequestRecord> sendGreeting(SendGreetingCommand command);

  Future<GreetingRequestRecord> replyGreeting(ReplyGreetingCommand command);

  Future<GreetingRequestRecord> ignoreGreeting(IgnoreGreetingCommand command);

  Future<GreetingRequestRecord> cancelGreeting(CancelGreetingCommand command);
}

/// 发起打招呼时可提交的最小交集意图引用。
///
/// 不携带任何展示文案、URL 或标签；user-service 必须按当前双方重新解析，
/// 解析失效时仍发送普通问候。
final class GreetingIntersectionRef {
  const GreetingIntersectionRef({
    required this.intersectionId,
    required this.evidenceId,
    required this.sourceRef,
    required this.objectTypeRef,
    required this.objectId,
  });

  final String intersectionId;
  final String evidenceId;
  final String sourceRef;
  final String objectTypeRef;
  final String objectId;

  bool get isComplete =>
      intersectionId.trim().isNotEmpty &&
      evidenceId.trim().isNotEmpty &&
      sourceRef.trim().isNotEmpty &&
      objectTypeRef.trim().isNotEmpty &&
      objectId.trim().isNotEmpty;
  bool get isNotEmpty => isComplete;

  Map<String, Object?> toWire() => <String, Object?>{
    'intersectionId': intersectionId.trim(),
    'evidenceId': evidenceId.trim(),
    'sourceRef': sourceRef.trim(),
    'objectTypeRef': objectTypeRef.trim(),
    'objectId': objectId.trim(),
  };
}

final class GreetingIntersectionSnapshot {
  const GreetingIntersectionSnapshot({
    required this.intersectionId,
    required this.evidenceId,
    required this.sourceRef,
    required this.objectTypeRef,
    required this.objectId,
    required this.primaryText,
    required this.resolvedAt,
    this.dimension,
  });

  final String intersectionId;
  final String evidenceId;
  final String sourceRef;
  final String objectTypeRef;
  final String objectId;
  final String primaryText;
  final String? dimension;
  final DateTime resolvedAt;
}

abstract interface class GreetingRequestQuery {
  Future<GreetingRequestSlice> listGreetingInbox(
    ListGreetingRequestsQuery query,
  );

  Future<GreetingRequestSlice> listGreetingOutbox(
    ListGreetingRequestsQuery query,
  );
}

final class GreetingRequestRecord {
  const GreetingRequestRecord({
    required this.id,
    required this.requesterPersonaId,
    required this.targetPersonaId,
    required this.status,
    required this.source,
    required this.createdAt,
    required this.updatedAt,
    this.requestMessage,
    this.intersectionRef,
    this.intersectionSnapshot,
    this.promotedConversationId,
    this.expireAt,
    this.decisionAt,
  });

  final String id;
  final String requesterPersonaId;
  final String targetPersonaId;
  final String? requestMessage;
  final GreetingIntersectionRef? intersectionRef;
  final GreetingIntersectionSnapshot? intersectionSnapshot;
  final String status;
  final String source;
  final String? promotedConversationId;
  final DateTime? expireAt;
  final DateTime? decisionAt;
  final DateTime createdAt;
  final DateTime updatedAt;
}

final class GreetingRequestSlice {
  const GreetingRequestSlice({required this.items, this.nextCursor});

  final List<GreetingRequestRecord> items;
  final String? nextCursor;
}

GreetingRequestRecord decodeGreetingRequestRecord(Object? response) {
  final root = _object(response, 'GreetingRequestRecord');
  return GreetingRequestRecord(
    id: _requiredField(root, 'id'),
    requesterPersonaId: _requiredField(root, 'requesterPersonaId'),
    targetPersonaId: _requiredField(root, 'targetPersonaId'),
    requestMessage: _optionalString(root['requestMessage']),
    intersectionRef: _decodeIntersectionRef(root['intersectionRef']),
    intersectionSnapshot: _decodeIntersectionSnapshot(
      root['intersectionSnapshot'],
    ),
    status: _requiredField(root, 'status'),
    source: _requiredField(root, 'source'),
    promotedConversationId: _optionalString(root['promotedConversationId']),
    expireAt: _optionalTimestamp(root['expireAt']),
    decisionAt: _optionalTimestamp(root['decisionAt']),
    createdAt: _requiredTimestamp(root, 'createdAt'),
    updatedAt: _requiredTimestamp(root, 'updatedAt'),
  );
}

GreetingIntersectionRef? _decodeIntersectionRef(Object? value) {
  if (value == null) return null;
  final root = _object(value, 'GreetingIntersectionRef');
  return GreetingIntersectionRef(
    intersectionId: _requiredField(root, 'intersectionId'),
    evidenceId: _requiredField(root, 'evidenceId'),
    sourceRef: _requiredField(root, 'sourceRef'),
    objectTypeRef: _requiredField(root, 'objectTypeRef'),
    objectId: _requiredField(root, 'objectId'),
  );
}

GreetingIntersectionSnapshot? _decodeIntersectionSnapshot(Object? value) {
  if (value == null) return null;
  final root = _object(value, 'GreetingIntersectionSnapshot');
  return GreetingIntersectionSnapshot(
    intersectionId: _requiredField(root, 'intersectionId'),
    evidenceId: _requiredField(root, 'evidenceId'),
    sourceRef: _requiredField(root, 'sourceRef'),
    objectTypeRef: _requiredField(root, 'objectTypeRef'),
    objectId: _requiredField(root, 'objectId'),
    primaryText: _requiredField(root, 'primaryText'),
    dimension: _optionalString(root['dimension']),
    resolvedAt: _requiredTimestamp(root, 'resolvedAt'),
  );
}

GreetingRequestSlice decodeGreetingRequestSlice(Object? response) {
  final root = _object(response, 'GreetingRequestSlice');
  final rawItems = root['items'];
  if (rawItems is! List<Object?>) {
    throw const FormatException(
      'GreetingRequestSlice.items must be a JSON array',
    );
  }
  final cursor =
      _optionalString(root['nextCursor']) ?? _optionalString(root['cursor']);
  return GreetingRequestSlice(
    items: rawItems
        .map<GreetingRequestRecord>(decodeGreetingRequestRecord)
        .toList(growable: false),
    nextCursor: cursor,
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
  if (value == null || value.isEmpty) {
    throw FormatException('missing required field "$key"');
  }
  return value;
}

String? _optionalString(Object? value) {
  final text = value is String ? value.trim() : '';
  return text.isEmpty ? null : text;
}

DateTime _requiredTimestamp(Map<Object?, Object?> root, String key) {
  final value = _requiredField(root, key);
  return DateTime.parse(value).toUtc();
}

DateTime? _optionalTimestamp(Object? value) {
  final text = _optionalString(value);
  return text == null ? null : DateTime.parse(text).toUtc();
}
