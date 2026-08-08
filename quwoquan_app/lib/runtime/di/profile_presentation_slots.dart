import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/app_providers_circle_facets.dart'
    show userProfileCircleMembershipQueryProvider;
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show journeyEventTrackerProvider;
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart'
    show profileEditProposalCommandWriterProvider;
import 'package:quwoquan_app/runtime/di/content_behavior_dependencies.dart'
    show contentBehaviorTrackerProvider;
import 'package:quwoquan_app/runtime/shell/share/forward_share_models.dart';
import 'package:quwoquan_app/runtime/shell/share/forward_share_sheet.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/presentation/profile_circles_tab.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/profile_interaction_selection.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/presentation/profile_interaction_tab.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/profile_footprint_tab.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_edit_models.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_mode.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/presentation/my_qr_card.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/edit_profile_participant_slots.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/profile_participant_slots.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/profile_state_provider.dart';
import 'package:quwoquan_app/service/user_service/persona_management/profile_update_proposal/presentation/profile_update_proposal_review_sheet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide InteractionDirection;

Widget _buildProfileFootprint({
  required bool isDark,
  required GestureDragEndCallback? onSecondaryHorizontalDragEnd,
}) => Consumer(
  builder: (context, ref, _) => ProfileFootprintTab(
    isDark: isDark,
    trackPostClick: (postId) => ref
        .read(contentBehaviorTrackerProvider)
        .trackClick(postId, referralSource: ReferralSource.authorProfile),
    onSecondaryHorizontalDragEnd: onSecondaryHorizontalDragEnd,
  ),
);

Widget _buildProfileInteraction({
  required ProfileMode mode,
  required String userId,
  required bool isDark,
  required bool inlineScroll,
  required GlobalKey? secondaryTabBarKey,
  required GestureDragEndCallback? onSecondaryHorizontalDragEnd,
  required ValueChanged<InteractionDirection>? onDirectionSelected,
  required ProfileShareInteractionSlotBuilder shareInteractionBuilder,
}) => Consumer(
  builder: (context, ref, _) {
    final state = ref.watch(profileNotifierProvider(userId));
    final notifier = ref.read(profileNotifierProvider(userId).notifier);
    return KeyedSubtree(
      key: const ValueKey<String>('profile-interaction-composition'),
      child: ProfileInteractionTab(
        mode: mode,
        userId: userId,
        isDark: isDark,
        inlineScroll: inlineScroll,
        secondaryTabBarKey: secondaryTabBarKey,
        onSecondaryHorizontalDragEnd: onSecondaryHorizontalDragEnd,
        selectedSubTab: state.interactionSubTab,
        selectedDirection: state.interactionDirection,
        onSubTabSelected: notifier.setInteractionSubTab,
        onDirectionSelected:
            onDirectionSelected ?? notifier.setInteractionDirection,
        shareInteractionBuilder: shareInteractionBuilder,
      ),
    );
  },
);

Widget _buildProfileCircles({
  required ProfileMode mode,
  required String userId,
  required bool isDark,
  required bool inlineScroll,
}) => Consumer(
  builder: (context, ref, _) => ProfileCirclesTab(
    mode: mode,
    userId: userId,
    isDark: isDark,
    membershipQuery: ref.watch(userProfileCircleMembershipQueryProvider),
    inlineScroll: inlineScroll,
  ),
);

Widget _buildEditProfileQrCard({
  required ProfileQrCardData card,
  required VoidCallback? onScanPressed,
}) => MyQrCardView(
  card: card,
  sharePresenter: profileQrSharePresenter,
  onScanPressed: onScanPressed,
);

Widget _buildEditProfileProposalReview({
  required ProfileUpdateProposalView proposal,
}) => Consumer(
  builder: (context, ref, _) => ProfileUpdateProposalReviewSheet(
    proposal: proposal,
    commandWriter: ref.watch(profileEditProposalCommandWriterProvider),
    trackAction:
        ({required action, required proposalId, result, failReasonCode}) => ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'profile_update_proposal',
              action: action,
              pageName: 'ProfileUpdateProposalReviewSheet',
              targetType: 'profile_update_proposal',
              targetKey: proposalId,
              payload: <String, dynamic>{
                'result': ?result,
                'failReasonCode': ?failReasonCode,
              },
            ),
  ),
);

Future<void> profileQrSharePresenter(
  BuildContext context,
  ProfileQrShareRequest request,
) {
  final card = request.card;
  return ForwardShareSheet.show(
    context,
    payload: AppForwardPayload(
      kind: AppForwardSubjectKind.profileQr,
      title: request.title,
      subtitle: card.region,
      thumbnailUrl: card.avatarUrl,
      deeplink: card.qrPayload,
      landingUrl: card.publicProfileUrl,
      shareText: request.shareMessage,
      previewBuilder: request.previewBuilder,
      extra: <String, Object?>{
        'qrPayload': card.qrPayload,
        'qrTokenId': card.qrTokenId,
        'displayName': card.displayName,
        'region': card.region,
      },
    ),
  );
}

const ProfileParticipantSlots profileParticipantSlots = ProfileParticipantSlots(
  buildInteraction: _buildProfileInteraction,
  buildFootprint: _buildProfileFootprint,
  buildCircles: _buildProfileCircles,
);

const EditProfileParticipantSlots editProfileParticipantSlots =
    EditProfileParticipantSlots(
      buildQrCard: _buildEditProfileQrCard,
      buildProposalReview: _buildEditProfileProposalReview,
    );
