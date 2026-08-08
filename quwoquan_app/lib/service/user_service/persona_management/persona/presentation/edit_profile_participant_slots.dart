import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_edit_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef EditProfileQrCardSlotBuilder =
    Widget Function({
      required ProfileQrCardData card,
      required VoidCallback? onScanPressed,
    });

typedef EditProfileProposalReviewSlotBuilder =
    Widget Function({required ProfileUpdateProposalView proposal});

/// Persona 编辑页 source owner 对 UserAccount/ProfileUpdateProposal UI 的插槽。
///
/// runtime/di 负责把两个参与对象的 production presentation 绑定进来；编辑页本身
/// 只持有必填 builder，不直接依赖兄弟对象 private presentation。
final class EditProfileParticipantSlots {
  const EditProfileParticipantSlots({
    required this.buildQrCard,
    required this.buildProposalReview,
  });

  final EditProfileQrCardSlotBuilder buildQrCard;
  final EditProfileProposalReviewSlotBuilder buildProposalReview;
}
