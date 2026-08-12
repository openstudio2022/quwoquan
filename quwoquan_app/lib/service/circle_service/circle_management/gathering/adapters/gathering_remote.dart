import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/transport/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/adapters/gathering_wire_codec.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/gathering_board_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as cloud;
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

typedef GatheringInvocationContextFactory =
    cloud.CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
    });

/// Production Gathering command/query adapter backed by generated operations.
final class RemoteGatheringFacet
    implements
        GatheringCommandWriter,
        GatheringQueryReader,
        GatheringBoardCircleReader {
  const RemoteGatheringFacet({
    required this.client,
    required this.invocationContext,
  });

  final cloud.GeneratedCloudOperationClient client;
  final GatheringInvocationContextFactory invocationContext;

  Future<GatheringCommandResult> _mapCommand(
    Future<cloud.GatheringCommandResult> wire,
  ) async {
    return gatheringCommandResultFromWire(await wire);
  }

  cloud.CloudOperationInvocationContext _commandContext(
    String clientPageId,
    String idempotencyKey,
  ) => invocationContext(clientPageId, idempotencyKey: idempotencyKey);

  List<cloud.CanonicalObjectRef> _evidenceRefs(
    List<GatheringCanonicalObjectRef> refs,
  ) {
    return refs
        .map(
          (ref) => cloud.CanonicalObjectRef(
            objectTypeRef: ref.objectTypeRef,
            objectId: ref.objectId,
          ),
        )
        .toList(growable: false);
  }

  @override
  Future<GatheringCommandResult> createDraft(GatheringCreateDraftInput input) {
    return _mapCommand(
      client.circleGatheringCreateGatheringDraft(
        createDraftCommandToWire(input),
        context: _commandContext(
          CircleRequestPageIds.createGatheringDraft,
          input.idempotencyKey,
        ),
      ),
    );
  }

  @override
  Future<GatheringCommandResult> publish(GatheringVersionCommandInput input) {
    return _mapCommand(
      client.circleGatheringPublishGathering(
        versionCommandToWire(input),
        context: _commandContext(
          CircleRequestPageIds.publishGathering,
          input.idempotencyKey,
        ),
      ),
    );
  }

  @override
  Future<GatheringCommandResult> update(GatheringUpdateInput input) {
    return _mapCommand(
      client.circleGatheringUpdateGathering(
        updateGatheringCommandToWire(input),
        context: _commandContext(
          CircleRequestPageIds.updateGathering,
          input.idempotencyKey,
        ),
      ),
    );
  }

  @override
  Future<GatheringCommandResult> joinOpen(
    GatheringParticipationCommandInput input,
  ) {
    return _mapCommand(
      client.circleGatheringJoinOpenGathering(
        participationCommandToWire(input),
        context: _commandContext(
          CircleRequestPageIds.joinOpenGathering,
          input.idempotencyKey,
        ),
      ),
    );
  }

  @override
  Future<GatheringCommandResult> apply(GatheringApplyInput input) {
    return _mapCommand(
      client.circleGatheringApplyToGathering(
        applyCommandToWire(input),
        context: _commandContext(
          CircleRequestPageIds.applyToGathering,
          input.idempotencyKey,
        ),
      ),
    );
  }

  @override
  Future<GatheringCommandResult> acceptInvitation(
    GatheringParticipationCommandInput input,
  ) {
    return _mapCommand(
      client.circleGatheringAcceptGatheringInvitation(
        participationCommandToWire(input),
        context: _commandContext(
          CircleRequestPageIds.acceptGatheringInvitation,
          input.idempotencyKey,
        ),
      ),
    );
  }

  @override
  Future<GatheringCommandResult> watchAvailability(
    GatheringAvailabilityWatchCommandInput input,
  ) {
    return _mapCommand(
      client.circleGatheringWatchGatheringAvailability(
        watchAvailabilityCommandToWire(input),
        context: _commandContext(
          CircleRequestPageIds.watchGatheringAvailability,
          input.idempotencyKey,
        ),
      ),
    );
  }

  @override
  Future<GatheringCommandResult> reviewApplication(
    GatheringReviewApplicationInput input,
  ) {
    return _mapCommand(
      client.circleGatheringReviewGatheringApplication(
        reviewApplicationCommandToWire(input),
        context: _commandContext(
          CircleRequestPageIds.reviewGatheringApplication,
          input.idempotencyKey,
        ),
      ),
    );
  }

  @override
  Future<GatheringCommandResult> invite(GatheringInviteInput input) {
    return _mapCommand(
      client.circleGatheringInviteToGathering(
        inviteCommandToWire(input),
        context: _commandContext(
          CircleRequestPageIds.inviteToGathering,
          input.idempotencyKey,
        ),
      ),
    );
  }

  @override
  Future<GatheringCommandResult> removeParticipant(
    GatheringRemoveParticipantInput input,
  ) {
    return _mapCommand(
      client.circleGatheringRemoveGatheringParticipant(
        removeParticipantCommandToWire(input),
        context: _commandContext(
          CircleRequestPageIds.removeGatheringParticipant,
          input.idempotencyKey,
        ),
      ),
    );
  }

  @override
  Future<GatheringCommandResult> changeCapacity(
    GatheringChangeCapacityInput input,
  ) {
    return _mapCommand(
      client.circleGatheringChangeGatheringCapacity(
        changeCapacityCommandToWire(input),
        context: _commandContext(
          CircleRequestPageIds.changeGatheringCapacity,
          input.idempotencyKey,
        ),
      ),
    );
  }

  @override
  Future<GatheringCommandResult> changeAdmission(
    GatheringChangeAdmissionInput input,
  ) {
    final command = admissionControlCommandToWire(input);
    final pageId = input.action == GatheringAdmissionControlAction.pause
        ? CircleRequestPageIds.pauseGatheringAdmission
        : CircleRequestPageIds.resumeGatheringAdmission;
    final wire = input.action == GatheringAdmissionControlAction.pause
        ? client.circleGatheringPauseGatheringAdmission(
            command,
            context: _commandContext(pageId, input.idempotencyKey),
          )
        : client.circleGatheringResumeGatheringAdmission(
            command,
            context: _commandContext(pageId, input.idempotencyKey),
          );
    return _mapCommand(wire);
  }

  @override
  Future<GatheringCommandResult> cancel(GatheringReasonCommandInput input) {
    return _mapCommand(
      client.circleGatheringCancelGathering(
        reasonCommandToWire(input),
        context: _commandContext(
          CircleRequestPageIds.cancelGathering,
          input.idempotencyKey,
        ),
      ),
    );
  }

  @override
  Future<GatheringCommandResult> start(GatheringVersionCommandInput input) {
    throw RuntimeFailure(
      code: RuntimeFailureCodes.appSystemUnknownError,
      semanticReason: 'gathering_start_operation_unavailable',
      origin: RuntimeFailureOrigin.environment,
      kind: RuntimeFailureKind.unavailable,
      nature: RuntimeFailureNature.permanent,
      location: const RuntimeFailureLocation(
        businessObject: 'circle.gathering',
        functionModule: 'gathering_remote',
      ),
      context: RuntimeFailureContext(
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(key: 'gatheringId', value: input.gatheringId),
        ],
      ),
      recovery: const RuntimeRecoveryDirective(
        action: 'surface',
        disruptionLevel: 'fullPage',
      ),
    );
  }

  @override
  Future<GatheringCommandResult> recordOutcome(
    GatheringOutcomeCommandInput input,
  ) {
    final versionCommand = versionCommandToWire(
      GatheringVersionCommandInput(
        idempotencyKey: input.idempotencyKey,
        gatheringId: input.gatheringId,
        expectedGatheringVersion: input.expectedGatheringVersion,
      ),
    );
    final reasonCommand = reasonCommandToWire(
      GatheringReasonCommandInput(
        idempotencyKey: input.idempotencyKey,
        gatheringId: input.gatheringId,
        reasonRef: input.evidenceRefs.isEmpty
            ? input.status.name
            : input.evidenceRefs.first.objectId,
        expectedGatheringVersion: input.expectedGatheringVersion,
        evidenceRefs: input.evidenceRefs,
      ),
    );
    final wire = switch (input.status) {
      GatheringOutcomeStatus.occurred ||
      GatheringOutcomeStatus.didNotHappen ||
      GatheringOutcomeStatus.disputed ||
      GatheringOutcomeStatus.unverified =>
        client.circleGatheringCompleteGathering(
          versionCommand,
          context: _commandContext(
            CircleRequestPageIds.completeGathering,
            input.idempotencyKey,
          ),
        ),
      GatheringOutcomeStatus.endedEarly =>
        client.circleGatheringEndGatheringEarly(
          reasonCommand,
          context: _commandContext(
            CircleRequestPageIds.endGatheringEarly,
            input.idempotencyKey,
          ),
        ),
      GatheringOutcomeStatus.safetyTerminated =>
        client.circleGatheringSafetyTerminateGathering(
          reasonCommand,
          context: _commandContext(
            CircleRequestPageIds.safetyTerminateGathering,
            input.idempotencyKey,
          ),
        ),
    };
    return _mapCommand(wire);
  }

  Future<GatheringCommandResult> completeGatheringSelf({
    required String idempotencyKey,
    required String gatheringId,
    required int expectedGatheringVersion,
    required int expectedParticipationVersion,
    List<GatheringCanonicalObjectRef> evidenceRefs =
        const <GatheringCanonicalObjectRef>[],
  }) {
    return _mapCommand(
      client.circleGatheringCompleteGatheringSelf(
        cloud.DeclareGatheringAttendanceCommand(
          gatheringId: gatheringId,
          evidenceRefs: _evidenceRefs(evidenceRefs),
          expectedGatheringVersion: expectedGatheringVersion,
          expectedParticipationVersion: expectedParticipationVersion,
        ),
        context: _commandContext(
          CircleRequestPageIds.completeGatheringSelf,
          idempotencyKey,
        ),
      ),
    );
  }

  Future<cloud.GatheringPrivateDetailSlice?> _loadPrivateDetailWire(
    String gatheringId, {
    required bool allowPublicFallback,
  }) {
    return client
        .circleGatheringGetGathering(
          cloud.GatheringIDQuery(gatheringId: gatheringId),
          context: invocationContext(CircleRequestPageIds.getGathering),
        )
        .then<cloud.GatheringPrivateDetailSlice?>(
          (wire) => wire,
          onError: (Object error, StackTrace stackTrace) {
            if (allowPublicFallback &&
                error is CloudException &&
                (error.type == CloudErrorType.notFound ||
                    error.type == CloudErrorType.forbidden)) {
              return null;
            }
            return Future<cloud.GatheringPrivateDetailSlice?>.error(
              error,
              stackTrace,
            );
          },
        );
  }

  @override
  Future<GatheringBoardCircleSlice> loadCircle(String gatheringId) async {
    final normalized = gatheringId.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(
        gatheringId,
        'gatheringId',
        'must not be blank',
      );
    }
    final wire = await _loadPrivateDetailWire(
      normalized,
      allowPublicFallback: false,
    );
    if (wire == null) {
      throw StateError('gathering board circle detail unavailable');
    }
    return gatheringBoardCircleFromPrivateWire(wire);
  }

  @override
  Future<GatheringDetailPresentationSlice?> getDetail(
    GatheringDetailQuery query,
  ) async {
    final gatheringId = query.gatheringId.trim();
    if (gatheringId.isEmpty) {
      return null;
    }
    final publicWire = await client.circleGatheringGetPublicGathering(
      cloud.GatheringIDQuery(gatheringId: gatheringId),
      context: invocationContext(CircleRequestPageIds.getPublicGathering),
    );
    final publicSlice = presentationFromPublicWire(publicWire);
    if (publicSlice == null) {
      return null;
    }
    final privateWire = await _loadPrivateDetailWire(
      gatheringId,
      allowPublicFallback: true,
    );
    if (privateWire == null) {
      return publicSlice;
    }
    return GatheringDetailPresentationSlice(
      publicDetail: publicSlice.publicDetail,
      privateDetail: privatePresentationFromWire(privateWire),
    );
  }
}
