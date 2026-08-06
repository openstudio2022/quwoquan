package gathering

import (
	"context"
	"errors"
	"sort"
	"strings"
	"time"

	circleerrors "quwoquan_service/services/circle-service/generated/circle_management/circle"
	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	gatheringclient "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/client"
	gatheringevent "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/event"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
)

type GatheringParticipationVersionCommand struct {
	GatheringID                  string
	ExpectedGatheringVersion     int64
	ExpectedParticipationVersion int64
}

type ApplyToGatheringCommand struct {
	GatheringParticipationVersionCommand
	Answers []model.GatheringApplicationAnswer
}

type ReviewGatheringApplicationCommand struct {
	GatheringID                  string
	ParticipantPersonaID         string
	Decision                     gatheringclient.GatheringApplicationReviewDecision
	ReasonRef                    string
	ExpectedGatheringVersion     int64
	ExpectedParticipationVersion int64
}

type InviteToGatheringCommand struct {
	GatheringID                  string
	ParticipantPersonaID         string
	SeatHoldUntil                time.Time
	ExpectedGatheringVersion     int64
	ExpectedParticipationVersion int64
}

type TargetGatheringParticipationCommand struct {
	GatheringID                  string
	ParticipantPersonaID         string
	ReasonRef                    string
	ExpectedGatheringVersion     int64
	ExpectedParticipationVersion int64
}

type ChangeGatheringAdmissionCommand struct {
	GatheringID                     string
	ReasonRef                       string
	ExpectedGatheringVersion        int64
	ExpectedAdmissionControlVersion int64
}

type ChangeGatheringCapacityCommand struct {
	GatheringID               string
	MaxParticipants           int64
	ExpectedGatheringVersion  int64
	AcknowledgementDeadlineAt time.Time
}

type GatheringAvailabilityWatchCommand struct {
	GatheringID              string
	ExpectedGatheringVersion int64
	ExpectedWatchVersion     int64
}

type ParticipationCommandResult = gatheringclient.GatheringCommandResult

func (facade *CommandFacade) JoinOpenGathering(
	ctx context.Context,
	command GatheringParticipationVersionCommand,
) (ParticipationCommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return ParticipationCommandResult{}, err
	}
	return facade.mutateParticipation(
		ctx,
		actorID,
		current.IdempotencyKey,
		"JoinOpenGathering",
		command,
		command.GatheringID,
		actorID,
		gatheringevent.GatheringParticipationChanged,
		func(existing *model.Gathering) (model.Gathering, error) {
			if existing == nil {
				return model.Gathering{}, gatheringerrors.ErrGatheringNotFound
			}
			return model.JoinOpen(*existing, model.ParticipationCommandInput{
				ActorPersonaID: actorID, ParticipantPersonaID: actorID,
				ExpectedGatheringVersion:     command.ExpectedGatheringVersion,
				ExpectedParticipationVersion: command.ExpectedParticipationVersion,
				OccurredAt:                   facade.now().UTC(),
			})
		},
	)
}

func (facade *CommandFacade) ApplyToGathering(
	ctx context.Context,
	command ApplyToGatheringCommand,
) (ParticipationCommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return ParticipationCommandResult{}, err
	}
	command.Answers = canonicalizeAnswersForCommandDigest(command.Answers)
	return facade.mutateParticipation(
		ctx,
		actorID,
		current.IdempotencyKey,
		"ApplyToGathering",
		command,
		command.GatheringID,
		actorID,
		gatheringevent.GatheringParticipationChanged,
		func(existing *model.Gathering) (model.Gathering, error) {
			if existing == nil {
				return model.Gathering{}, gatheringerrors.ErrGatheringNotFound
			}
			return model.Apply(*existing, model.ApplyParticipationInput{
				ParticipationCommandInput: model.ParticipationCommandInput{
					ActorPersonaID: actorID, ParticipantPersonaID: actorID,
					ExpectedGatheringVersion:     command.ExpectedGatheringVersion,
					ExpectedParticipationVersion: command.ExpectedParticipationVersion,
					OccurredAt:                   facade.now().UTC(),
				},
				Answers: command.Answers,
			})
		},
	)
}

func (facade *CommandFacade) WithdrawGatheringApplication(
	ctx context.Context,
	command GatheringParticipationVersionCommand,
) (ParticipationCommandResult, error) {
	return facade.mutateSelfParticipation(
		ctx,
		"WithdrawGatheringApplication",
		gatheringevent.GatheringParticipationChanged,
		command,
		model.WithdrawApplication,
	)
}

func (facade *CommandFacade) ReviewGatheringApplication(
	ctx context.Context,
	command ReviewGatheringApplicationCommand,
) (ParticipationCommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return ParticipationCommandResult{}, err
	}
	participantID := strings.TrimSpace(command.ParticipantPersonaID)
	return facade.mutateParticipation(
		ctx,
		actorID,
		current.IdempotencyKey,
		"ReviewGatheringApplication",
		command,
		command.GatheringID,
		participantID,
		gatheringevent.GatheringParticipationChanged,
		func(existing *model.Gathering) (model.Gathering, error) {
			if existing == nil {
				return model.Gathering{}, gatheringerrors.ErrGatheringNotFound
			}
			return model.ReviewApplication(*existing, model.ReviewParticipationInput{
				ParticipationCommandInput: model.ParticipationCommandInput{
					ActorPersonaID: actorID, ParticipantPersonaID: participantID,
					ExpectedGatheringVersion:     command.ExpectedGatheringVersion,
					ExpectedParticipationVersion: command.ExpectedParticipationVersion,
					OccurredAt:                   facade.now().UTC(),
				},
				Decision: command.Decision, ReasonRef: command.ReasonRef,
			})
		},
	)
}

func (facade *CommandFacade) InviteToGathering(
	ctx context.Context,
	command InviteToGatheringCommand,
) (ParticipationCommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return ParticipationCommandResult{}, err
	}
	participantID := strings.TrimSpace(command.ParticipantPersonaID)
	return facade.mutateParticipation(
		ctx,
		actorID,
		current.IdempotencyKey,
		"InviteToGathering",
		command,
		command.GatheringID,
		participantID,
		gatheringevent.GatheringParticipationChanged,
		func(existing *model.Gathering) (model.Gathering, error) {
			if existing == nil {
				return model.Gathering{}, gatheringerrors.ErrGatheringNotFound
			}
			return model.Invite(*existing, model.InviteParticipationInput{
				ParticipationCommandInput: model.ParticipationCommandInput{
					ActorPersonaID: actorID, ParticipantPersonaID: participantID,
					ExpectedGatheringVersion:     command.ExpectedGatheringVersion,
					ExpectedParticipationVersion: command.ExpectedParticipationVersion,
					OccurredAt:                   facade.now().UTC(),
				},
				SeatHoldUntil: command.SeatHoldUntil,
			})
		},
	)
}

func (facade *CommandFacade) AcceptGatheringInvitation(
	ctx context.Context,
	command GatheringParticipationVersionCommand,
) (ParticipationCommandResult, error) {
	return facade.mutateSelfParticipation(
		ctx,
		"AcceptGatheringInvitation",
		gatheringevent.GatheringParticipationChanged,
		command,
		model.AcceptInvitation,
	)
}

func (facade *CommandFacade) DeclineGatheringInvitation(
	ctx context.Context,
	command GatheringParticipationVersionCommand,
) (ParticipationCommandResult, error) {
	return facade.mutateSelfParticipation(
		ctx,
		"DeclineGatheringInvitation",
		gatheringevent.GatheringParticipationChanged,
		command,
		model.DeclineInvitation,
	)
}

func (facade *CommandFacade) RevokeGatheringInvitation(
	ctx context.Context,
	command TargetGatheringParticipationCommand,
) (ParticipationCommandResult, error) {
	return facade.mutateTargetParticipation(
		ctx,
		"RevokeGatheringInvitation",
		command,
		model.RevokeInvitation,
	)
}

func (facade *CommandFacade) LeaveGathering(
	ctx context.Context,
	command GatheringParticipationVersionCommand,
) (ParticipationCommandResult, error) {
	return facade.mutateSelfParticipation(
		ctx,
		"LeaveGathering",
		gatheringevent.GatheringParticipationChanged,
		command,
		model.LeaveParticipation,
	)
}

func (facade *CommandFacade) RemoveGatheringParticipant(
	ctx context.Context,
	command TargetGatheringParticipationCommand,
) (ParticipationCommandResult, error) {
	return facade.mutateTargetParticipation(
		ctx,
		"RemoveGatheringParticipant",
		command,
		model.RemoveParticipation,
	)
}

func (facade *CommandFacade) ReinstateGatheringParticipant(
	ctx context.Context,
	command TargetGatheringParticipationCommand,
) (ParticipationCommandResult, error) {
	return facade.mutateTargetParticipation(
		ctx,
		"ReinstateGatheringParticipant",
		command,
		model.ReinstateParticipation,
	)
}

func (facade *CommandFacade) PauseGatheringAdmission(
	ctx context.Context,
	command ChangeGatheringAdmissionCommand,
) (ParticipationCommandResult, error) {
	return facade.changeAdmission(ctx, "PauseGatheringAdmission", command, model.PauseAdmission)
}

func (facade *CommandFacade) ResumeGatheringAdmission(
	ctx context.Context,
	command ChangeGatheringAdmissionCommand,
) (ParticipationCommandResult, error) {
	return facade.changeAdmission(ctx, "ResumeGatheringAdmission", command, model.ResumeAdmission)
}

func (facade *CommandFacade) ChangeGatheringCapacity(
	ctx context.Context,
	command ChangeGatheringCapacityCommand,
) (ParticipationCommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return ParticipationCommandResult{}, err
	}
	return facade.mutateParticipation(
		ctx,
		actorID,
		current.IdempotencyKey,
		"ChangeGatheringCapacity",
		command,
		command.GatheringID,
		"",
		gatheringevent.GatheringRevisionAppended,
		func(existing *model.Gathering) (model.Gathering, error) {
			if existing == nil {
				return model.Gathering{}, gatheringerrors.ErrGatheringNotFound
			}
			return model.ChangeCapacity(*existing, model.ChangeCapacityInput{
				ActorPersonaID:            actorID,
				ExpectedGatheringVersion:  command.ExpectedGatheringVersion,
				MaxParticipants:           command.MaxParticipants,
				AcknowledgementDeadlineAt: command.AcknowledgementDeadlineAt,
				OccurredAt:                facade.now().UTC(),
			})
		},
	)
}

func (facade *CommandFacade) WatchGatheringAvailability(
	ctx context.Context,
	command GatheringAvailabilityWatchCommand,
) (ParticipationCommandResult, error) {
	return facade.changeAvailabilityWatch(
		ctx,
		"WatchGatheringAvailability",
		command,
		model.WatchAvailability,
	)
}

func (facade *CommandFacade) UnwatchGatheringAvailability(
	ctx context.Context,
	command GatheringAvailabilityWatchCommand,
) (ParticipationCommandResult, error) {
	return facade.changeAvailabilityWatch(
		ctx,
		"UnwatchGatheringAvailability",
		command,
		model.UnwatchAvailability,
	)
}

func (facade *CommandFacade) mutateSelfParticipation(
	ctx context.Context,
	operationName string,
	eventType string,
	command GatheringParticipationVersionCommand,
	apply func(model.Gathering, model.ParticipationCommandInput) (model.Gathering, error),
) (ParticipationCommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return ParticipationCommandResult{}, err
	}
	return facade.mutateParticipation(
		ctx,
		actorID,
		current.IdempotencyKey,
		operationName,
		command,
		command.GatheringID,
		actorID,
		eventType,
		func(existing *model.Gathering) (model.Gathering, error) {
			if existing == nil {
				return model.Gathering{}, gatheringerrors.ErrGatheringNotFound
			}
			return apply(*existing, model.ParticipationCommandInput{
				ActorPersonaID: actorID, ParticipantPersonaID: actorID,
				ExpectedGatheringVersion:     command.ExpectedGatheringVersion,
				ExpectedParticipationVersion: command.ExpectedParticipationVersion,
				OccurredAt:                   facade.now().UTC(),
			})
		},
	)
}

func (facade *CommandFacade) mutateTargetParticipation(
	ctx context.Context,
	operationName string,
	command TargetGatheringParticipationCommand,
	apply func(model.Gathering, model.CloseParticipationInput) (model.Gathering, error),
) (ParticipationCommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return ParticipationCommandResult{}, err
	}
	participantID := strings.TrimSpace(command.ParticipantPersonaID)
	return facade.mutateParticipation(
		ctx,
		actorID,
		current.IdempotencyKey,
		operationName,
		command,
		command.GatheringID,
		participantID,
		gatheringevent.GatheringParticipationChanged,
		func(existing *model.Gathering) (model.Gathering, error) {
			if existing == nil {
				return model.Gathering{}, gatheringerrors.ErrGatheringNotFound
			}
			return apply(*existing, model.CloseParticipationInput{
				ParticipationCommandInput: model.ParticipationCommandInput{
					ActorPersonaID: actorID, ParticipantPersonaID: participantID,
					ExpectedGatheringVersion:     command.ExpectedGatheringVersion,
					ExpectedParticipationVersion: command.ExpectedParticipationVersion,
					OccurredAt:                   facade.now().UTC(),
				},
				ReasonRef: command.ReasonRef,
			})
		},
	)
}

func (facade *CommandFacade) changeAdmission(
	ctx context.Context,
	operationName string,
	command ChangeGatheringAdmissionCommand,
	apply func(model.Gathering, model.ChangeAdmissionInput) (model.Gathering, error),
) (ParticipationCommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return ParticipationCommandResult{}, err
	}
	return facade.mutateParticipation(
		ctx,
		actorID,
		current.IdempotencyKey,
		operationName,
		command,
		command.GatheringID,
		"",
		gatheringevent.GatheringAdmissionControlChanged,
		func(existing *model.Gathering) (model.Gathering, error) {
			if existing == nil {
				return model.Gathering{}, gatheringerrors.ErrGatheringNotFound
			}
			return apply(*existing, model.ChangeAdmissionInput{
				ActorPersonaID: actorID, ReasonRef: command.ReasonRef,
				ExpectedGatheringVersion:        command.ExpectedGatheringVersion,
				ExpectedAdmissionControlVersion: command.ExpectedAdmissionControlVersion,
				OccurredAt:                      facade.now().UTC(),
			})
		},
	)
}

func (facade *CommandFacade) changeAvailabilityWatch(
	ctx context.Context,
	operationName string,
	command GatheringAvailabilityWatchCommand,
	apply func(model.Gathering, model.AvailabilityWatchInput) (model.Gathering, error),
) (ParticipationCommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return ParticipationCommandResult{}, err
	}
	return facade.mutateParticipation(
		ctx,
		actorID,
		current.IdempotencyKey,
		operationName,
		command,
		command.GatheringID,
		"",
		gatheringevent.GatheringAvailabilityWatchChanged,
		func(existing *model.Gathering) (model.Gathering, error) {
			if existing == nil {
				return model.Gathering{}, gatheringerrors.ErrGatheringNotFound
			}
			return apply(*existing, model.AvailabilityWatchInput{
				ActorPersonaID:           actorID,
				ExpectedGatheringVersion: command.ExpectedGatheringVersion,
				ExpectedWatchVersion:     command.ExpectedWatchVersion,
				OccurredAt:               facade.now().UTC(),
			})
		},
	)
}

func (facade *CommandFacade) mutateParticipation(
	ctx context.Context,
	actorID string,
	key string,
	operationName string,
	payload any,
	gatheringID string,
	participantPersonaID string,
	eventType string,
	mutation ports.Mutation,
) (ParticipationCommandResult, error) {
	digest, err := commandDigest(actorID, operationName, payload)
	if err != nil {
		return ParticipationCommandResult{}, gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
	receipt, err := facade.store.Commit(ctx, ports.CommitRequest{
		GatheringID:          strings.TrimSpace(gatheringID),
		ReceiptKey:           receiptKey(actorID, key),
		CommandDigest:        digest,
		ReceiptExpiresAt:     facade.now().UTC().Add(receiptRetention),
		EventType:            eventType,
		AdditionalEventTypes: invitationProjectionEventTypes(operationName),
		Mutate:               mutation,
	})
	if err != nil {
		return ParticipationCommandResult{}, mapParticipationError(err)
	}
	return participationResultFrom(
		receipt.Gathering,
		participantPersonaID,
		receipt.Replayed,
	), nil
}

func invitationProjectionEventTypes(operationName string) []string {
	switch operationName {
	case "InviteToGathering",
		"RevokeGatheringInvitation",
		"AcceptGatheringInvitation",
		"DeclineGatheringInvitation":
		return []string{gatheringevent.GatheringInvitationChanged}
	default:
		return nil
	}
}

func participationResultFrom(
	value model.Gathering,
	participantPersonaID string,
	replayed bool,
) ParticipationCommandResult {
	result := ParticipationCommandResult{
		GatheringID:      value.ID,
		AggregateVersion: value.Version,
		LifecycleStatus: gatheringclient.GatheringLifecycleStatus(
			value.LifecycleStatus,
		),
		CurrentGatheringRevisionID:     value.CurrentGatheringRevisionID,
		CurrentGatheringRevisionNumber: value.CurrentGatheringRevisionNumber,
		ConversationID:                 value.ConversationID,
		RoomBindingStatus: gatheringclient.GatheringRoomBindingStatus(
			value.RoomBindingStatus,
		),
		IdempotentReplay: replayed,
	}
	if participation, found := model.FindParticipation(value, participantPersonaID); found {
		result.ParticipationState = gatheringclient.GatheringParticipationState(
			participation.State,
		)
		result.ParticipationVersion = participation.Version
	}
	if value.Outcome.Status != contract.GatheringOutcomeStatus("") {
		result.OutcomeStatus = gatheringclient.GatheringOutcomeStatus(
			value.Outcome.Status,
		)
	}
	return result
}

func canonicalizeAnswersForCommandDigest(
	answers []model.GatheringApplicationAnswer,
) []model.GatheringApplicationAnswer {
	result := append([]model.GatheringApplicationAnswer(nil), answers...)
	for index := range result {
		result[index].QuestionID = strings.TrimSpace(result[index].QuestionID)
		result[index].AnswerText = strings.TrimSpace(result[index].AnswerText)
		result[index].SelectedOptionIds = append([]string(nil), result[index].SelectedOptionIds...)
		for optionIndex := range result[index].SelectedOptionIds {
			result[index].SelectedOptionIds[optionIndex] =
				strings.TrimSpace(result[index].SelectedOptionIds[optionIndex])
		}
		sort.Strings(result[index].SelectedOptionIds)
	}
	sort.Slice(result, func(left, right int) bool {
		return result[left].QuestionID < result[right].QuestionID
	})
	return result
}

func mapParticipationError(err error) error {
	switch {
	case errors.Is(err, gatheringerrors.ErrGatheringNotFound):
		return gatheringerrors.AppErrorFromGatheringNotFound(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringPermissionDenied):
		return gatheringerrors.AppErrorFromGatheringPermissionDenied(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringAdmissionClosed):
		return gatheringerrors.AppErrorFromGatheringAdmissionClosed(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringAdmissionPaused):
		return gatheringerrors.AppErrorFromGatheringAdmissionPaused(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringCapacityFull):
		return gatheringerrors.AppErrorFromGatheringCapacityFull(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringCapacityBelowOccupiedSeats):
		return gatheringerrors.AppErrorFromGatheringCapacityBelowOccupiedSeats(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringParticipationConflict):
		return gatheringerrors.AppErrorFromGatheringParticipationConflict(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringAlreadyActive):
		return gatheringerrors.AppErrorFromGatheringAlreadyActive(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringInvitationExpired):
		return gatheringerrors.AppErrorFromGatheringInvitationExpired(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringInvitationRecipientMismatch):
		return gatheringerrors.AppErrorFromGatheringInvitationRecipientMismatch(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringInvitationInactive):
		return gatheringerrors.AppErrorFromGatheringInvitationInactive(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringSeatHoldExpired):
		return gatheringerrors.AppErrorFromGatheringSeatHoldExpired(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringOrganizerTransferRequired):
		return gatheringerrors.AppErrorFromGatheringOrganizerTransferRequired(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringOperationNotAllowedInProgress):
		return gatheringerrors.AppErrorFromGatheringOperationNotAllowedInProgress(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringTransitionForbidden):
		return gatheringerrors.AppErrorFromGatheringTransitionForbidden(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringVersionConflict),
		errors.Is(err, ports.ErrVersionConflict):
		return gatheringerrors.AppErrorFromGatheringVersionConflict(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringIdempotencyConflict):
		return gatheringerrors.AppErrorFromGatheringIdempotencyConflict(err.Error())
	case errors.Is(err, model.ErrInvalidArgument):
		return circleerrors.AppErrorFromInvalidArgument(err.Error())
	default:
		return gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
}
