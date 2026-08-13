import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_invitation_inbox_card.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show AppMessage, AppMessageGatheringInvitation;

/// 通知收件箱的 Circle participant 插槽绑定：Gathering 邀请专卡。
///
/// 与 [homepage_circle_presentation_slots] 同范式：跨域 participant Widget 只在
/// runtime/di 组合根绑定，chat presentation 不直接依赖 circle presentation。
Widget buildChatInboxGatheringInvitationSlot({
  required AppMessage message,
  required AppMessageGatheringInvitation invitation,
  required Future<void> Function() onResolved,
  required Color fgPrimary,
  required Color fgSecondary,
  required Color backgroundColor,
}) => GatheringInvitationInboxCard(
  message: message,
  invitation: invitation,
  onResolved: onResolved,
  fgPrimary: fgPrimary,
  fgSecondary: fgSecondary,
  backgroundColor: backgroundColor,
);
