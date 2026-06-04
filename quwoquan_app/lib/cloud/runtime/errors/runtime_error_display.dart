import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/core/auth/auth_continuation.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

String runtimeErrorDisplayMessage(Object error) {
  final failure = runtimeFailureFromError(error);
  if (error is CloudException) {
    final userMessage = error.userMessage?.trim() ?? '';
    if (userMessage.isNotEmpty) {
      return userMessage;
    }
  }
  if (failure != null) {
    return runtimeFailureDisplayMessage(failure);
  }
  return '操作失败，请稍后重试';
}

UiErrorSemantic runtimeErrorSemantic(
  BuildContext context, {
  required Object error,
  required UiErrorCategory category,
  required UiErrorScope scope,
  AuthGateReason? authGateReason,
  AuthContinuation? continuation,
  bool allowRetry = true,
  bool allowOpenSettings = false,
  UiErrorPresentation? presentation,
}) {
  return UiErrorSemanticResolver.resolve(
    context,
    error: error,
    category: category,
    scope: scope,
    authGateReason: authGateReason,
    continuation: continuation,
    allowRetry: allowRetry,
    allowOpenSettings: allowOpenSettings,
    presentation: presentation,
  );
}

RuntimeFailureBase? runtimeFailureFromError(Object error) {
  if (error is CloudException) return error.runtimeFailure;
  if (error is RuntimeFailureBase) return error;
  return null;
}

String runtimeFailureDisplayMessage(RuntimeFailureBase failure) {
  return switch (failure.kind) {
    RuntimeFailureKind.auth => '请先登录后再试',
    RuntimeFailureKind.permission => '暂无权限执行此操作',
    RuntimeFailureKind.notFound => '内容不存在或已被删除',
    RuntimeFailureKind.network || RuntimeFailureKind.timeout => '网络连接异常，请稍后重试',
    RuntimeFailureKind.rateLimited => '操作太频繁，请稍后重试',
    RuntimeFailureKind.validation => '请求内容有误，请检查后重试',
    RuntimeFailureKind.unavailable => '服务暂时不可用，稍后自动恢复后再试',
    _ => '操作失败，请稍后重试',
  };
}
