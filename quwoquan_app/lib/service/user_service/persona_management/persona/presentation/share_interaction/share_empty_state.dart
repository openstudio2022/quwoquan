import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/feedback/app_empty_state.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_models.dart';

/// 分享互动 tab 的空态：按方向注入业务文案，视觉统一走 [AppEmptyState]。
///
/// 只做 direction → 文案 的业务映射，不引入第二套空态视觉。
AppEmptyState shareInteractionEmptyState({
  Key? key,
  required ShareInteractionDirection direction,
  required VoidCallback onAction,
}) {
  final isReceived = direction == ShareInteractionDirection.received;
  return AppEmptyState(
    key: key,
    icon: CupertinoIcons.arrowshape_turn_up_right,
    title: isReceived
        ? ProfileText.profileShareReceivedEmptyTitle
        : ProfileText.profileShareInitiatedEmptyTitle,
    subtitle: isReceived
        ? ProfileText.profileShareReceivedEmptyDescription
        : ProfileText.profileShareInitiatedEmptyDescription,
    actionLabel: isReceived
        ? ProfileText.profileShareReceivedEmptyAction
        : ProfileText.profileShareInitiatedEmptyAction,
    onAction: onAction,
  );
}
