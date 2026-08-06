import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';

import '../../../../../support/service/circle_service/circle_management/gathering/gathering_test_support.dart';

void main() {
  test(
    'primary action covers public/invite/full/in-progress/completed states',
    () {
      final scenarios = <(GatheringPublicDetailSlice, GatheringPrimaryAction)>[
        (publicGatheringDetail(), GatheringPrimaryAction.join),
        (
          publicGatheringDetail(admission: GatheringAdmissionPolicy.approval),
          GatheringPrimaryAction.apply,
        ),
        (
          publicGatheringDetail(
            participationState: GatheringParticipationState.invitedPending,
            participationSource: GatheringAdmissionSource.invitation,
          ),
          GatheringPrimaryAction.acceptInvitation,
        ),
        (
          publicGatheringDetail(
            maxParticipants: 1,
            occupiedSeats: 1,
            full: true,
            admissionState: GatheringAdmissionState.full,
          ),
          GatheringPrimaryAction.watchAvailability,
        ),
        (
          publicGatheringDetail(
            temporal: GatheringTemporalPhase.inProgress,
            admissionState: GatheringAdmissionState.closed,
            participationState: GatheringParticipationState.active,
            conversationId: 'conversation-1',
          ),
          GatheringPrimaryAction.enterChat,
        ),
        (
          publicGatheringDetail(
            temporal: GatheringTemporalPhase.inProgress,
            admissionState: GatheringAdmissionState.closed,
          ),
          GatheringPrimaryAction.readOnly,
        ),
        (
          publicGatheringDetail(
            lifecycle: GatheringLifecycleStatus.completed,
            temporal: GatheringTemporalPhase.ended,
          ),
          GatheringPrimaryAction.readOnly,
        ),
        (
          publicGatheringDetail(
            admission: GatheringAdmissionPolicy.inviteOnly,
            audience: GatheringAudiencePolicy.inviteOnly,
          ),
          GatheringPrimaryAction.noAction,
        ),
      ];

      for (final scenario in scenarios) {
        expect(scenario.$1.primaryAction, scenario.$2);
      }
    },
  );

  test('private exact place is exposed only through authority capability', () {
    final public = publicGatheringDetail();
    final redacted = GatheringDetailPresentationSlice(
      publicDetail: public,
      privateDetail: privateGatheringDetail(
        authority: GatheringViewerAuthoritySlice.none,
        exactMeetingPoint: 'SECRET_PLACE',
      ),
    );
    const activeAuthority = GatheringViewerAuthoritySlice(
      isOrganizer: false,
      isActiveParticipant: true,
      canReviewApplications: false,
      canInvite: false,
      canRemoveParticipants: false,
      canChangeCapacity: false,
      canChangeAdmission: false,
      canUpdateMaterialDetails: false,
      canCancel: false,
      canStart: false,
      canRecordOutcome: false,
    );
    final active = GatheringDetailPresentationSlice(
      publicDetail: public,
      privateDetail: privateGatheringDetail(
        authority: activeAuthority,
        exactMeetingPoint: 'SECRET_PLACE',
      ),
    );

    expect(redacted.visibleExactMeetingPoint, isNull);
    expect(active.visibleExactMeetingPoint, 'SECRET_PLACE');
  });
}
