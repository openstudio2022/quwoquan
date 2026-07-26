import '../operation_request_payload.dart';

// SubjectFollow 对象 pure contracts：关注非 persona 主体（homepage/circle/location）。
// set/unset 由服务端内部 CAS 与幂等 receipt 保证重放安全；命令体不携带版本。

abstract interface class SubjectFollowCommandWriter {
  Future<SubjectFollowCommandResult> follow(FollowSubjectCommand command);

  Future<SubjectFollowCommandResult> unfollow(UnfollowSubjectCommand command);
}

enum SubjectFollowSubjectType {
  homepage,
  circle,
  location;

  String get wire => name;
}

final class FollowSubjectCommand {
  FollowSubjectCommand({
    required this.subjectType,
    required String subjectId,
    String? source,
  }) : subjectId = _required(subjectId, 'subjectId'),
       source = _optional(source);

  final SubjectFollowSubjectType subjectType;
  final String subjectId;
  final String? source;
}

CloudOperationRequestPayload encodeFollowSubjectCommand(
  FollowSubjectCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      'subjectType': command.subjectType.wire,
      'subjectId': command.subjectId,
    },
    body: <String, Object?>{
      if (command.source case final source?) 'source': source,
    },
  );
}

final class UnfollowSubjectCommand {
  UnfollowSubjectCommand({
    required this.subjectType,
    required String subjectId,
  }) : subjectId = _required(subjectId, 'subjectId');

  final SubjectFollowSubjectType subjectType;
  final String subjectId;
}

CloudOperationRequestPayload encodeUnfollowSubjectCommand(
  UnfollowSubjectCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      'subjectType': command.subjectType.wire,
      'subjectId': command.subjectId,
    },
  );
}

final class SubjectFollowCommandResult {
  const SubjectFollowCommandResult({
    required this.personaId,
    required this.subjectType,
    required this.subjectId,
    required this.state,
    required this.idempotentReplay,
    this.updatedAt,
  });

  final String personaId;
  final String subjectType;
  final String subjectId;
  final String state;
  final bool idempotentReplay;
  final DateTime? updatedAt;

  bool get following => state == 'following';
}

SubjectFollowCommandResult decodeSubjectFollowCommandResult(Object? response) {
  if (response is! Map<Object?, Object?>) {
    throw const FormatException(
      'SubjectFollow command result must be a JSON object',
    );
  }
  final replay = response['idempotentReplay'];
  return SubjectFollowCommandResult(
    personaId: _requiredField(response, 'personaId'),
    subjectType: _requiredField(response, 'subjectType'),
    subjectId: _requiredField(response, 'subjectId'),
    state: _requiredField(response, 'state'),
    idempotentReplay: replay is bool && replay,
    updatedAt: _optionalTimestamp(response['updatedAt']),
  );
}

String _requiredField(Map<Object?, Object?> root, String key) {
  final value = root[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('missing required field "$key"');
  }
  return value.trim();
}

DateTime? _optionalTimestamp(Object? value) {
  if (value == null) return null;
  if (value is! String || value.trim().isEmpty) {
    throw const FormatException('timestamp must be an ISO-8601 string');
  }
  return DateTime.parse(value.trim()).toUtc();
}

String _required(String value, String name) {
  final text = value.trim();
  if (text.isEmpty) {
    throw ArgumentError.value(value, name, 'must not be empty');
  }
  return text;
}

String? _optional(String? value) {
  final text = value?.trim();
  if (text == null || text.isEmpty) return null;
  return text;
}
