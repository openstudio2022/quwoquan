import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_session_provider.dart';

/// PiP 挂断的唯一装配顺序：等待云端 HangupCall 结构化回执，成功后才清理
/// shell 的 active-call 展示状态；失败保留浮窗，供用户重试。
Future<CallSessionActionResult> runPipHangupFlow({
  required Future<CallSessionActionResult> Function() hangup,
  required VoidCallback clearActiveCall,
}) async {
  final result = await hangup();
  if (result.succeeded) {
    clearActiveCall();
  }
  return result;
}
