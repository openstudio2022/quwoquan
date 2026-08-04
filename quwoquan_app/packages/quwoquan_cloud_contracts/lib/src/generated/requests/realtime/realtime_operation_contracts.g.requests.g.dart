// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 93359367b8614f01bb5e1c51e37af383332b01f117cc1c6cf39e4fdf838e49d2

part of '../../../realtime/realtime_operation_contracts.g.dart';


void _generatedRequestRejectUnknownFields(
  Map<String, Object?> map,
  Set<String> allowed,
  String path,
) {
  for (final key in map.keys) {
    if (!allowed.contains(key)) {
      throw FormatException('$path contains unknown field $key');
    }
  }
}


String _generatedRequestString(Object? value, String path) {
  if (value is String) return value;
  throw FormatException('$path must be a string');
}


int _generatedRequestInt(Object? value, String path) {
  if (value is int) return value;
  throw FormatException('$path must be an integer');
}

final class IssueConnectionTicketRequest {
  const IssueConnectionTicketRequest();
}

final class LongPollRequest {
  const LongPollRequest({
    int? timeout,
    String? cursor,
  }) : timeout = timeout,
       cursor = cursor;

  final int? timeout;
  final String? cursor;

  factory LongPollRequest.fromWire(Map<String, Object?> map, [String path = "LongPollRequest"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"timeout", "cursor"}, path);
    return LongPollRequest(
      timeout: map["timeout"] == null ? null : _generatedRequestInt(map["timeout"], '$path.timeout'),
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.timeout != null) "timeout": this.timeout!,
    if (this.cursor != null) "cursor": this.cursor!,
  };
}

CloudOperationRequestPayload encodeRealtimeConnectionIssueConnectionTicketGeneratedRequest(IssueConnectionTicketRequest request) {
  return CloudOperationRequestPayload(
  );
}

CloudOperationRequestPayload encodeRealtimeConnectionLongPollGeneratedRequest(LongPollRequest request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.timeout != null) "timeout": (request.timeout!).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
}

