import 'package:quwoquan_app/runtime/di/circle_creations_presentation_slots.dart';
import 'package:quwoquan_app/runtime/di/recommendation_presentation_slots.dart';
import 'package:quwoquan_app/runtime/di/rtc_call_entry_dependencies.dart';
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/circle_shell_participant_slots.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/presentation/circle_group_membership_panel.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/application/public/circle_membership_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/presentation/circle_membership_approval_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/presentation/section_members.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/object_intersection_section.dart';

CircleMembershipApprovalPageBuilder buildCircleMembershipApprovalPage({
  required PendingCircleMemberships pendingMemberships,
  required CircleMembershipModeration moderationWriter,
  required JourneyEventTracker journeyEventTracker,
}) =>
    (circleId) => CircleMembershipApprovalPage(
      circleId: circleId,
      pendingMemberships: pendingMemberships,
      moderationWriter: moderationWriter,
      journeyEventTracker: journeyEventTracker,
    );

CircleShellParticipantSlots buildCircleShellParticipantSlots({
  required CircleMembershipApprovalPageBuilder membershipApprovalPageBuilder,
}) => CircleShellParticipantSlots(
  buildMembershipApprovalPage: membershipApprovalPageBuilder,
  buildObjectIntersection:
      ({
        required key,
        required query,
        required title,
        required isDark,
        required emptyText,
        required emptyKey,
      }) => ObjectIntersectionSection(
        key: key,
        query: query,
        title: title,
        isDark: isDark,
        emptyText: emptyText,
        emptyKey: emptyKey,
      ),
  buildObjectImpact: buildCircleObjectImpactSlot,
  creations: circleCreationsParticipantSlots,
  buildMembersSection: ({required circleId, required isDark}) =>
      SectionMembers(circleId: circleId, isDark: isDark),
  buildGroupMembershipPanel:
      ({required circleId, required group, required access, required isDark}) =>
          CircleGroupMembershipPanel(
            circleId: circleId,
            group: group,
            access: access,
            isDark: isDark,
          ),
  startCall:
      ({
        required context,
        required ref,
        required intent,
        required sourceSurface,
      }) async {
        await ref
            .read(rtcCallEntryPresenterProvider)
            .start(
              context: context,
              ref: ref,
              intent: intent,
              sourceSurface: sourceSurface,
            );
      },
);
