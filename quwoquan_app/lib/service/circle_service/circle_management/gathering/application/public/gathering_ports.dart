import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';

abstract interface class GatheringCommandWriter {
  Future<GatheringCommandResult> createDraft(GatheringCreateDraftInput input);

  Future<GatheringCommandResult> publish(GatheringVersionCommandInput input);

  Future<GatheringCommandResult> update(GatheringUpdateInput input);

  Future<GatheringCommandResult> joinOpen(
    GatheringParticipationCommandInput input,
  );

  Future<GatheringCommandResult> apply(GatheringApplyInput input);

  Future<GatheringCommandResult> acceptInvitation(
    GatheringParticipationCommandInput input,
  );

  Future<GatheringCommandResult> watchAvailability(
    GatheringVersionCommandInput input,
  );

  Future<GatheringCommandResult> reviewApplication(
    GatheringReviewApplicationInput input,
  );

  Future<GatheringCommandResult> invite(GatheringInviteInput input);

  Future<GatheringCommandResult> removeParticipant(
    GatheringRemoveParticipantInput input,
  );

  Future<GatheringCommandResult> changeCapacity(
    GatheringChangeCapacityInput input,
  );

  Future<GatheringCommandResult> changeAdmission(
    GatheringChangeAdmissionInput input,
  );

  Future<GatheringCommandResult> cancel(GatheringReasonCommandInput input);

  Future<GatheringCommandResult> start(GatheringVersionCommandInput input);

  Future<GatheringCommandResult> recordOutcome(
    GatheringOutcomeCommandInput input,
  );
}

abstract interface class GatheringQueryReader {
  Future<GatheringDetailPresentationSlice?> getDetail(
    GatheringDetailQuery query,
  );
}
