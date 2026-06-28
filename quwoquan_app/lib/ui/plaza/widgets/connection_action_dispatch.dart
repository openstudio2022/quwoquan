import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/cloud/runtime/recommendation/intersection_action_keys.dart';
import 'package:quwoquan_app/cloud/services/connection/connection_models.dart';
import 'package:quwoquan_app/core/constants/plaza_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';

/// 同频/广场行动阶梯统一分发：把连接卡 CTA 落到既有子系统，**不另起一套**。
///
/// 路由分发遵循 [IntersectionActionKeys] 闭集语义（端只读 actionKey 分发，不按 kind 猜）：
/// - 建群类（话题房 / 同行群 / 局群 / 实时房）→ 复用 [AppRoutePaths.startGroupChat] 建群页。
/// - 破冰类（打招呼 / 心动 / 附近）→ 复用 GreetingRequest 状态机 `sendGreeting`，
///   进入对方「请求箱」，遵守 contact-and-session-governance 的非好友破冰契约。
/// - 兜底：无明确目标时给出即时反馈，方向确认后逐 key 升级真实落点。
Future<void> dispatchConnectionAction(
  BuildContext context,
  WidgetRef ref,
  ConnectionActionHint action, {
  String? targetSubAccountId,
  required String source,
}) async {
  final key = action.actionKey.trim();

  if (_isGroupForming(key)) {
    // 复用建群页：同行群 / 局群 / 话题房共用一套成员选择与创建流程。
    context.push(AppRoutePaths.startGroupChat);
    return;
  }

  // 破冰：复用打招呼请求（非好友先进请求箱，对方同意后才可继续）。
  final hasTarget = (targetSubAccountId ?? '').trim().isNotEmpty;
  if (hasTarget) {
    try {
      await ref
          .read(greetingRepositoryProvider)
          .sendGreeting(targetSubAccountId: targetSubAccountId!.trim(), source: source);
      if (context.mounted) {
        AppToast.show(
          context,
          PlazaTextConstants.actionSentMessage(action.label),
        );
      }
    } catch (error) {
      if (context.mounted) {
        AppToast.show(context, runtimeErrorDisplayMessage(error));
      }
    }
    return;
  }

  // 兜底反馈（原型）：无人际目标且非建群的 key，先给即时反馈。
  if (context.mounted) {
    AppToast.show(context, PlazaTextConstants.actionSentMessage(action.label));
  }
}

/// 建群 / 进群 / 报名类：落到建群页（成员选择 → 创建会话）。
bool _isGroupForming(String key) {
  return key == IntersectionActionKeys.joinTopicRoom ||
      key == IntersectionActionKeys.startCompanion ||
      key == IntersectionActionKeys.joinTrip ||
      key == IntersectionActionKeys.joinMeetup ||
      key == IntersectionActionKeys.startVoiceRoom;
}
