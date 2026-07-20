import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/auth/auth_continuation.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';

/// 实体主页写页面统一登录闸口。
///
/// [LoginDismissPolicy.safeFallback] 是当前登录契约中
/// `allowGuestDismissPop: false` 的强入口表达：关闭只能去公开安全页。
Future<bool> requireHomepageWriteAccess(
  WidgetRef ref,
  BuildContext context, {
  required HomepageWriteContinuationAction action,
  required String dismissFallback,
  String homepageId = '',
  bool submitAfterLogin = false,
}) async {
  if (AuthGate.isAuthenticated(ref)) {
    return true;
  }
  final accepted = ref
      .read(authContinuationProvider.notifier)
      .set(
        HomepageWriteContinuation(
          action: action,
          homepageId: homepageId,
          submitAfterLogin: submitAfterLogin,
        ),
        ownerToken: 'entity-homepage:${action.name}:$homepageId',
      );
  if (!accepted || !context.mounted) {
    return false;
  }
  await requireLogin(
    ref,
    context,
    AuthGateReason.homepageWrite,
    dismissFallback: dismissFallback,
    dismissPolicy: LoginDismissPolicy.safeFallback,
  );
  return false;
}

HomepageWriteContinuation? takeHomepageWriteContinuation(
  WidgetRef ref, {
  required HomepageWriteContinuationAction action,
  String homepageId = '',
}) {
  final controller = ref.read(authContinuationProvider.notifier);
  final pending = controller.take<HomepageWriteContinuation>();
  if (pending == null) {
    return null;
  }
  if (pending.action == action && pending.homepageId == homepageId) {
    return pending;
  }
  controller.set(pending);
  return null;
}
