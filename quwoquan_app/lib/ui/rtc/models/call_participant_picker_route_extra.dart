/// `AppRoutePaths.rtcPickParticipants` 的强类型 `extra`。
class CallParticipantPickerRouteExtra {
  const CallParticipantPickerRouteExtra.initialCall({
    required this.conversationId,
    this.maxParticipants = 32,
    this.defaultSelectAll = false,
  }) : callId = null,
       currentParticipantCount = 1;

  const CallParticipantPickerRouteExtra.existingCallInvite({
    required this.callId,
    required this.currentParticipantCount,
    this.maxParticipants = 32,
    this.conversationId,
  }) : defaultSelectAll = false;

  /// 非空时表示已有 CallSession 的 InviteToCall；为空时表示 InitiateCall。
  final String? callId;

  /// CallSession 总人数上限，包含发起人和已在通话中的参与者。
  final int maxParticipants;

  /// 初始多人通话必须携带 canonical Conversation，且只能从其成员中选择。
  final String? conversationId;

  /// 已有通话当前总人数；初始通话固定为发起人 1 人。
  final int currentParticipantCount;

  final bool defaultSelectAll;

  bool get isExistingCallInvite => (callId?.trim().isNotEmpty ?? false);

  /// 只有已有通话邀请才可按服务端 InviteToCall 授权策略切换来源。
  bool get allowsCrossContextSources => isExistingCallInvite;

  /// 当前动作还能选择的新增参与者数量。
  int get selectionLimit {
    final totalLimit = maxParticipants < 0 ? 0 : maxParticipants;
    final occupied = isExistingCallInvite ? currentParticipantCount : 1;
    final remaining = totalLimit - (occupied < 0 ? 0 : occupied);
    return remaining < 0 ? 0 : remaining;
  }

  /// [raw] 来自 `go_router` 的 [GoRouterState.extra]（框架 API 为 [Object?]，此处为唯一收口点）。
  static CallParticipantPickerRouteExtra fromRouter(Object? raw) {
    if (raw is CallParticipantPickerRouteExtra) {
      return raw;
    }
    return const CallParticipantPickerRouteExtra.initialCall(
      conversationId: null,
    );
  }
}
