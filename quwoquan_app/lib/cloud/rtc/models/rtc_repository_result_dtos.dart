import 'package:quwoquan_app/cloud/rtc/models/call_session_dto.dart';

Map<String, dynamic>? _sessionNestedFromMap(Map<String, dynamic> map) {
  final s = map['session'];
  if (s is Map<String, dynamic>) return s;
  if (s is Map) return Map<String, dynamic>.from(s);
  return null;
}

/// [RtcRepository.initiateCall] 的归一化结果（会话 + 可选 LiveKit token）。
class RtcInitiateCallResultDto {
  const RtcInitiateCallResultDto({
    required this.session,
    this.token = '',
  });

  final CallSessionDto session;
  final String token;

  /// rtc-service：`{ session, token }`。Mock：扁平 CallSession map（无 `session` 键）。
  factory RtcInitiateCallResultDto.fromMap(Map<String, dynamic> map) {
    final token = map['token'] as String? ?? '';
    final sessionMap = _sessionNestedFromMap(map) ?? map;
    return RtcInitiateCallResultDto(
      token: token,
      session: CallSessionDto.fromMap(sessionMap),
    );
  }
}

/// [RtcRepository.answerCall]：rtc-service 为 `{ session, token, roomId }`；兼容扁平遗留。
class RtcAnswerCallResultDto {
  const RtcAnswerCallResultDto({
    this.token,
    this.roomId,
    this.session,
  });

  final String? token;
  final String? roomId;
  final CallSessionDto? session;

  factory RtcAnswerCallResultDto.fromMap(Map<String, dynamic> map) {
    final nested = _sessionNestedFromMap(map);
    if (nested != null) {
      return RtcAnswerCallResultDto(
        token: map['token'] as String?,
        roomId: map['roomId'] as String?,
        session: CallSessionDto.fromMap(nested),
      );
    }
    final id = map['id'] ?? map['_id'] ?? map['callId'];
    final hasSessionId = id != null && id.toString().isNotEmpty;
    return RtcAnswerCallResultDto(
      token: map['token'] as String?,
      roomId: map['roomId'] as String?,
      session: hasSessionId ? CallSessionDto.fromMap(map) : null,
    );
  }
}

/// [RtcRepository.joinRtcToken]（JoinCall）签发的凭证。
class RtcJoinCredentialsDto {
  const RtcJoinCredentialsDto({
    required this.token,
    required this.roomId,
    this.callId,
  });

  final String token;
  final String roomId;
  final String? callId;

  factory RtcJoinCredentialsDto.fromMap(Map<String, dynamic> map) {
    final token = map['token'] as String? ?? '';
    final nested = _sessionNestedFromMap(map);
    if (nested != null) {
      final roomId =
          map['roomId'] as String? ?? nested['roomId'] as String? ?? '';
      final callId = nested['callId'] as String? ??
          nested['_id'] as String? ??
          nested['id'] as String?;
      return RtcJoinCredentialsDto(
        token: token,
        roomId: roomId,
        callId: callId,
      );
    }
    return RtcJoinCredentialsDto(
      token: token,
      roomId: map['roomId'] as String? ?? '',
      callId: map['callId'] as String?,
    );
  }
}
