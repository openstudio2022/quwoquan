class RtcTokenDto {
  final String token;
  final String roomId;
  final String callId;

  const RtcTokenDto({
    required this.token,
    required this.roomId,
    required this.callId,
  });

  factory RtcTokenDto.fromMap(Map<String, dynamic> map) {
    return RtcTokenDto(
      token: map['token'] as String? ?? '',
      roomId: map['roomId'] as String? ?? '',
      callId: map['callId'] as String? ?? '',
    );
  }

  Map<String, dynamic> toMap() {
    return {
      'token': token,
      'roomId': roomId,
      'callId': callId,
    };
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RtcTokenDto &&
          runtimeType == other.runtimeType &&
          token == other.token &&
          roomId == other.roomId &&
          callId == other.callId;

  @override
  int get hashCode => Object.hash(token, roomId, callId);
}
