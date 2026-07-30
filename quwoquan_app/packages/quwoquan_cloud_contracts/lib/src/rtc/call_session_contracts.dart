import '../operation_request_payload.dart';
import 'call_session_dtos.g.dart';

export 'call_session_dtos.g.dart';
part '../generated/requests/rtc/call_session_contracts.requests.g.dart';

/// RTC CallSession 对象的 pure Dart contracts。
///
/// 真相源：quwoquan_service/services/rtc-service/contracts/rtc/call_session/{fields,service}.yaml。
/// 命令不携带 aggregate version；服务端以内部 CAS、命令回执与 outbox
/// 保证并发安全和幂等。

abstract interface class CallLifecycleCommandWriter {
  Future<RtcInitiateCallResultDto> initiateCall(RtcInitiateCallCommand command);

  Future<RtcAnswerCallResultDto> answerCall(RtcCallIdCommand command);

  Future<CallSessionDto> rejectCall(RtcCallIdCommand command);

  Future<CallSessionDto> cancelCall(RtcCallIdCommand command);

  Future<CallSessionDto> hangupCall(RtcCallIdCommand command);
}

abstract interface class CallParticipantCommandWriter {
  Future<RtcJoinCredentialsDto> joinCall(RtcCallIdCommand command);

  Future<CallSessionDto> leaveCall(RtcCallIdCommand command);

  Future<CallSessionDto> inviteToCall(RtcInviteToCallCommand command);

  /// 端侧首帧媒体连通后上报；≥2 人 connected 时会话进入 in_call。
  Future<CallSessionDto> reportMediaConnected(RtcCallIdCommand command);
}

abstract interface class CallMediaControlWriter {
  Future<CallSessionDto> toggleMute(RtcToggleMuteCommand command);

  Future<CallSessionDto> toggleCamera(RtcToggleCameraCommand command);
}

abstract interface class CallScreenShareWriter {
  Future<CallSessionDto> startScreenShare(RtcCallIdCommand command);

  Future<CallSessionDto> stopScreenShare(RtcCallIdCommand command);
}

abstract interface class CallQuery {
  Future<CallSessionDto> getCall(RtcGetCallQuery query);

  Future<RtcCallHistoryPage> listCalls(RtcListCallsQuery query);
}

final class RtcMediaSessionAccessDto {
  const RtcMediaSessionAccessDto({required this.accessToken});

  final String accessToken;

  factory RtcMediaSessionAccessDto.fromMap(Map<Object?, Object?> map) {
    final accessToken = _stringField(map, 'accessToken');
    if (accessToken == null) {
      throw const FormatException('mediaAccess must contain accessToken');
    }
    return RtcMediaSessionAccessDto(accessToken: accessToken);
  }
}

final class RtcInitiateCallResultDto {
  const RtcInitiateCallResultDto({
    required this.session,
    required this.mediaAccess,
  });

  final CallSessionDto session;
  final RtcMediaSessionAccessDto mediaAccess;
}

final class RtcAnswerCallResultDto {
  const RtcAnswerCallResultDto({
    required this.session,
    required this.mediaAccess,
  });

  final CallSessionDto session;
  final RtcMediaSessionAccessDto mediaAccess;
}

final class RtcJoinCredentialsDto {
  const RtcJoinCredentialsDto({
    required this.session,
    required this.mediaAccess,
  });

  final CallSessionDto session;
  final RtcMediaSessionAccessDto mediaAccess;

  String get roomId => session.roomId;
  String get callId => session.callId;
}

final class RtcCallHistoryPage {
  const RtcCallHistoryPage({required this.items, this.nextCursor});

  final List<CallSessionDto> items;
  final String? nextCursor;
}

CallSessionDto decodeRtcCallSession(Object? response) =>
    CallSessionDto.fromMap(_object(response, 'CallSession'));

RtcInitiateCallResultDto decodeRtcInitiateCallResult(Object? response) {
  final root = _object(response, 'InitiateCall result');
  return RtcInitiateCallResultDto(
    session: CallSessionDto.fromMap(
      _nestedObject(root, 'session', 'InitiateCall result'),
    ),
    mediaAccess: RtcMediaSessionAccessDto.fromMap(
      _nestedObject(root, 'mediaAccess', 'InitiateCall result'),
    ),
  );
}

RtcAnswerCallResultDto decodeRtcAnswerCallResult(Object? response) {
  final root = _object(response, 'AnswerCall result');
  final session = CallSessionDto.fromMap(
    _nestedObject(root, 'session', 'AnswerCall result'),
  );
  return RtcAnswerCallResultDto(
    session: session,
    mediaAccess: RtcMediaSessionAccessDto.fromMap(
      _nestedObject(root, 'mediaAccess', 'AnswerCall result'),
    ),
  );
}

RtcJoinCredentialsDto decodeRtcJoinCallResult(Object? response) {
  final root = _object(response, 'JoinCall result');
  return RtcJoinCredentialsDto(
    session: CallSessionDto.fromMap(
      _nestedObject(root, 'session', 'JoinCall result'),
    ),
    mediaAccess: RtcMediaSessionAccessDto.fromMap(
      _nestedObject(root, 'mediaAccess', 'JoinCall result'),
    ),
  );
}

RtcCallHistoryPage decodeRtcCallHistoryPage(Object? response) {
  final root = _object(response, 'CallHistory page');
  final rawItems = root['items'];
  if (rawItems is! List<Object?>) {
    throw const FormatException('CallHistory page items must be a JSON list');
  }
  final items = <CallSessionDto>[];
  for (final raw in rawItems) {
    if (raw is! Map<Object?, Object?>) {
      throw const FormatException('CallHistory item must be a JSON object');
    }
    items.add(CallSessionDto.fromMap(raw));
  }
  return RtcCallHistoryPage(
    items: List<CallSessionDto>.unmodifiable(items),
    nextCursor: _stringField(root, 'nextCursor'),
  );
}

Map<Object?, Object?> _object(Object? value, String name) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$name must be a JSON object');
  }
  return value;
}

Map<Object?, Object?> _nestedObject(
  Map<Object?, Object?> root,
  String key,
  String name,
) {
  final value = root[key];
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$name missing object "$key"');
  }
  return value;
}

String? _stringField(Map<Object?, Object?> root, String key) {
  final value = root[key];
  if (value == null) return null;
  if (value is! String) {
    throw FormatException('field "$key" must be a string');
  }
  final text = value.trim();
  return text.isEmpty ? null : text;
}
