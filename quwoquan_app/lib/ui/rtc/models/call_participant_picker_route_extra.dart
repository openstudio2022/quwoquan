/// `AppRoutePaths.rtcPickParticipants` 的强类型 `extra`（兼容历史 `Map`）。
class CallParticipantPickerRouteExtra {
  const CallParticipantPickerRouteExtra({
    this.callId,
    this.maxParticipants = 32,
    this.conversationId,
    this.defaultSelectAll = false,
  });

  final String? callId;
  final int maxParticipants;
  final String? conversationId;
  final bool defaultSelectAll;

  static CallParticipantPickerRouteExtra fromRouter(Object? raw) {
    if (raw is CallParticipantPickerRouteExtra) {
      return raw;
    }
    if (raw is Map<String, dynamic>) {
      return CallParticipantPickerRouteExtra(
        callId: raw['callId'] as String?,
        maxParticipants: (raw['maxParticipants'] as num?)?.toInt() ?? 32,
        conversationId: raw['conversationId'] as String?,
        defaultSelectAll: raw['defaultSelectAll'] as bool? ?? false,
      );
    }
    return const CallParticipantPickerRouteExtra();
  }
}
