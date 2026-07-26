import '../operation_request_payload.dart';

abstract interface class GreetingRequestCommandWriter {
  Future<GreetingRequestRecord> sendGreeting(SendGreetingCommand command);

  Future<GreetingRequestRecord> replyGreeting(ReplyGreetingCommand command);

  Future<GreetingRequestRecord> ignoreGreeting(IgnoreGreetingCommand command);

  Future<GreetingRequestRecord> cancelGreeting(CancelGreetingCommand command);
}

abstract interface class GreetingRequestQuery {
  Future<GreetingRequestSlice> listGreetingInbox(
    ListGreetingRequestsQuery query,
  );

  Future<GreetingRequestSlice> listGreetingOutbox(
    ListGreetingRequestsQuery query,
  );
}

final class SendGreetingCommand {
  SendGreetingCommand({
    required String targetSubAccountId,
    this.requestMessage,
    this.source = 'profile',
  }) : targetSubAccountId = _required(targetSubAccountId, 'targetSubAccountId');

  final String targetSubAccountId;
  final String? requestMessage;
  final String source;
}

final class ReplyGreetingCommand {
  ReplyGreetingCommand({required String requestId})
    : requestId = _required(requestId, 'requestId');

  final String requestId;
}

final class IgnoreGreetingCommand {
  IgnoreGreetingCommand({required String requestId})
    : requestId = _required(requestId, 'requestId');

  final String requestId;
}

final class CancelGreetingCommand {
  CancelGreetingCommand({required String requestId})
    : requestId = _required(requestId, 'requestId');

  final String requestId;
}

final class ListGreetingRequestsQuery {
  const ListGreetingRequestsQuery({
    this.status = 'pending',
    this.cursor,
    this.limit = 20,
  });

  final String status;
  final String? cursor;
  final int limit;
}

final class GreetingRequestRecord {
  const GreetingRequestRecord({
    required this.id,
    required this.requesterSubAccountId,
    required this.targetSubAccountId,
    required this.status,
    required this.source,
    required this.createdAt,
    required this.updatedAt,
    this.requestMessage,
    this.promotedConversationId,
    this.expireAt,
    this.decisionAt,
  });

  final String id;
  final String requesterSubAccountId;
  final String targetSubAccountId;
  final String? requestMessage;
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

CloudOperationRequestPayload encodeSendGreetingCommand(
  SendGreetingCommand command,
) {
  final message = command.requestMessage?.trim();
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      'targetSubAccountId': command.targetSubAccountId,
      if (message != null && message.isNotEmpty) 'requestMessage': message,
      'source': command.source.trim().isEmpty
          ? 'profile'
          : command.source.trim(),
    },
  );
}

CloudOperationRequestPayload encodeReplyGreetingCommand(
  ReplyGreetingCommand command,
) => _requestIdPayload(command.requestId);

CloudOperationRequestPayload encodeIgnoreGreetingCommand(
  IgnoreGreetingCommand command,
) => _requestIdPayload(command.requestId);

CloudOperationRequestPayload encodeCancelGreetingCommand(
  CancelGreetingCommand command,
) => _requestIdPayload(command.requestId);

CloudOperationRequestPayload encodeListGreetingRequestsQuery(
  ListGreetingRequestsQuery query,
) {
  final status = query.status.trim();
  final cursor = query.cursor?.trim() ?? '';
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (status.isNotEmpty) 'status': status,
      if (cursor.isNotEmpty) 'cursor': cursor,
      'limit': '${query.limit.clamp(1, 100)}',
    },
  );
}

GreetingRequestRecord decodeGreetingRequestRecord(Object? response) {
  final root = _object(response, 'GreetingRequestRecord');
  return GreetingRequestRecord(
    id: _requiredField(root, 'id'),
    requesterSubAccountId: _requiredField(root, 'requesterSubAccountId'),
    targetSubAccountId: _requiredField(root, 'targetSubAccountId'),
    requestMessage: _optionalString(root['requestMessage']),
    status: _requiredField(root, 'status'),
    source: _requiredField(root, 'source'),
    promotedConversationId: _optionalString(root['promotedConversationId']),
    expireAt: _optionalTimestamp(root['expireAt']),
    decisionAt: _optionalTimestamp(root['decisionAt']),
    createdAt: _requiredTimestamp(root, 'createdAt'),
    updatedAt: _requiredTimestamp(root, 'updatedAt'),
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

CloudOperationRequestPayload _requestIdPayload(String requestId) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'requestId': requestId},
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

String _required(String value, String name) {
  final text = value.trim();
  if (text.isEmpty) {
    throw ArgumentError.value(value, name, 'must not be empty');
  }
  return text;
}
