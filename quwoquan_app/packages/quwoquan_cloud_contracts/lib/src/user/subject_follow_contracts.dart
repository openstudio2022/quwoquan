import '../operation_request_payload.dart';
import '../generated/user_contract_enums.g.dart';
part '../generated/requests/user/subject_follow_contracts.requests.g.dart';

// SubjectFollow 对象 pure contracts：关注非 persona 主体（homepage/circle/location）。
// set/unset 由服务端内部 CAS 与幂等 receipt 保证重放安全；命令体不携带版本。

abstract interface class SubjectFollowCommandWriter {
  Future<SubjectFollowCommandResult> follow(FollowSubjectCommand command);

  Future<SubjectFollowCommandResult> unfollow(UnfollowSubjectCommand command);
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
  final FollowSubjectKind subjectType;
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
    subjectType: FollowSubjectKind.fromWire(response['subjectType']),
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
