// Code generated from contracts/metadata/rtc/call_session/errors.yaml — DO NOT EDIT.
// ignore_for_file: constant_identifier_names

enum RtcErrorCode {
  callNotFound('RTC.USER.call_not_found', '通话不存在', 404),
  unauthorized('RTC.USER.unauthorized', '请先登录', 401),
  alreadyInCall('RTC.USER.already_in_call', '你正在通话中，请先结束当前通话', 409),
  callFull('RTC.USER.call_full', '通话人数已达上限', 409),
  callEnded('RTC.USER.call_ended', '通话已结束', 410),
  notParticipant('RTC.USER.not_participant', '你不是该通话的参与者', 403),
  cannotAnswer('RTC.USER.cannot_answer', '无法接听，通话状态异常', 409),
  screenShareConflict(
      'RTC.USER.screen_share_conflict', '已有参与者正在共享屏幕', 409),
  recordingNotAllowed('RTC.USER.recording_not_allowed', '你没有录制权限', 403),
  rateLimited('RTC.USER.rate_limited', '操作太频繁，请稍后重试', 429),
  livekitUnavailable(
      'RTC.SYSTEM.livekit_unavailable', '通话服务暂时不可用，请稍后重试', 503),
  internalError('RTC.SYSTEM.internal_error', '通话服务异常，请稍后重试', 500),
  tokenGenerationFailed(
      'RTC.SYSTEM.token_generation_failed', '连接通话服务失败，请重试', 500);

  final String code;
  final String defaultMessage;
  final int httpStatus;

  const RtcErrorCode(this.code, this.defaultMessage, this.httpStatus);

  static RtcErrorCode? fromCode(String code) {
    for (final v in values) {
      if (v.code == code) return v;
    }
    return null;
  }

  bool get isUserError => code.startsWith('RTC.USER.');

  bool get isSystemError => code.startsWith('RTC.SYSTEM.');
}
