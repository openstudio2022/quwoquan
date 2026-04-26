import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

String runtimeErrorDisplayMessage(Object error) {
  final failure = runtimeFailureFromError(error);
  if (failure != null) {
    return runtimeFailureDisplayMessage(failure);
  }
  return '操作失败，请稍后重试';
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
    RuntimeFailureKind.unavailable => '服务暂时不可用，请稍后重试',
    _ => '操作失败，请稍后重试',
  };
}
