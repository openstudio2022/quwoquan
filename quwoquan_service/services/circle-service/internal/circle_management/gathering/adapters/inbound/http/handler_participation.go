package http

import (
	stdhttp "net/http"
	"time"

	rterr "quwoquan_service/runtime/errors"
	gatheringclient "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/client"
	app "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
)

type participationVersionBody struct {
	ExpectedGatheringVersion     int64 `json:"expectedGatheringVersion"`
	ExpectedParticipationVersion int64 `json:"expectedParticipationVersion"`
}

type applyParticipationBody struct {
	participationVersionBody
	Answers []model.GatheringApplicationAnswer `json:"answers"`
}

type reviewApplicationBody struct {
	ParticipantPersonaID         string                                             `json:"participantPersonaId"`
	Decision                     gatheringclient.GatheringApplicationReviewDecision `json:"decision"`
	ReasonRef                    string                                             `json:"reasonRef"`
	ExpectedGatheringVersion     int64                                              `json:"expectedGatheringVersion"`
	ExpectedParticipationVersion int64                                              `json:"expectedParticipationVersion"`
}

type inviteParticipationBody struct {
	ParticipantPersonaID         string    `json:"participantPersonaId"`
	SeatHoldUntil                time.Time `json:"seatHoldUntil"`
	ExpectedGatheringVersion     int64     `json:"expectedGatheringVersion"`
	ExpectedParticipationVersion int64     `json:"expectedParticipationVersion"`
}

type targetParticipationBody struct {
	ParticipantPersonaID         string `json:"participantPersonaId"`
	ReasonRef                    string `json:"reasonRef"`
	ExpectedGatheringVersion     int64  `json:"expectedGatheringVersion"`
	ExpectedParticipationVersion int64  `json:"expectedParticipationVersion"`
}

type changeAdmissionBody struct {
	ReasonRef                       string `json:"reasonRef"`
	ExpectedGatheringVersion        int64  `json:"expectedGatheringVersion"`
	ExpectedAdmissionControlVersion int64  `json:"expectedAdmissionControlVersion"`
}

type changeCapacityBody struct {
	MaxParticipants           int64     `json:"maxParticipants"`
	ExpectedGatheringVersion  int64     `json:"expectedGatheringVersion"`
	AcknowledgementDeadlineAt time.Time `json:"acknowledgementDeadlineAt"`
}

type availabilityWatchBody struct {
	ExpectedGatheringVersion int64 `json:"expectedGatheringVersion"`
	ExpectedWatchVersion     int64 `json:"expectedWatchVersion"`
}

type ParticipationHandler struct {
	commands *app.CommandFacade
}

func NewParticipationHandler(commands *app.CommandFacade) *ParticipationHandler {
	if commands == nil {
		panic("Gathering ParticipationHandler requires CommandFacade")
	}
	return &ParticipationHandler{commands: commands}
}

func (handler *ParticipationHandler) handleParticipationAction(
	writer stdhttp.ResponseWriter,
	request *stdhttp.Request,
	gatheringID string,
	action string,
) bool {
	var (
		result app.ParticipationCommandResult
		err    error
	)
	switch action {
	case "join-open":
		var body participationVersionBody
		if !decodeParticipationBody(writer, request, &body) {
			return true
		}
		result, err = handler.commands.JoinOpenGathering(
			request.Context(),
			participationVersionCommand(gatheringID, body),
		)
	case "apply":
		var body applyParticipationBody
		if !decodeParticipationBody(writer, request, &body) {
			return true
		}
		result, err = handler.commands.ApplyToGathering(
			request.Context(),
			app.ApplyToGatheringCommand{
				GatheringParticipationVersionCommand: participationVersionCommand(
					gatheringID,
					body.participationVersionBody,
				),
				Answers: body.Answers,
			},
		)
	case "withdraw-application":
		var body participationVersionBody
		if !decodeParticipationBody(writer, request, &body) {
			return true
		}
		result, err = handler.commands.WithdrawGatheringApplication(
			request.Context(),
			participationVersionCommand(gatheringID, body),
		)
	case "review-application":
		var body reviewApplicationBody
		if !decodeParticipationBody(writer, request, &body) {
			return true
		}
		result, err = handler.commands.ReviewGatheringApplication(
			request.Context(),
			app.ReviewGatheringApplicationCommand{
				GatheringID:                  gatheringID,
				ParticipantPersonaID:         body.ParticipantPersonaID,
				Decision:                     body.Decision,
				ReasonRef:                    body.ReasonRef,
				ExpectedGatheringVersion:     body.ExpectedGatheringVersion,
				ExpectedParticipationVersion: body.ExpectedParticipationVersion,
			},
		)
	case "invite":
		var body inviteParticipationBody
		if !decodeParticipationBody(writer, request, &body) {
			return true
		}
		result, err = handler.commands.InviteToGathering(
			request.Context(),
			app.InviteToGatheringCommand{
				GatheringID:                  gatheringID,
				ParticipantPersonaID:         body.ParticipantPersonaID,
				SeatHoldUntil:                body.SeatHoldUntil,
				ExpectedGatheringVersion:     body.ExpectedGatheringVersion,
				ExpectedParticipationVersion: body.ExpectedParticipationVersion,
			},
		)
	case "accept-invitation":
		var body participationVersionBody
		if !decodeParticipationBody(writer, request, &body) {
			return true
		}
		result, err = handler.commands.AcceptGatheringInvitation(
			request.Context(),
			participationVersionCommand(gatheringID, body),
		)
	case "decline-invitation":
		var body participationVersionBody
		if !decodeParticipationBody(writer, request, &body) {
			return true
		}
		result, err = handler.commands.DeclineGatheringInvitation(
			request.Context(),
			participationVersionCommand(gatheringID, body),
		)
	case "revoke-invitation":
		var body targetParticipationBody
		if !decodeParticipationBody(writer, request, &body) {
			return true
		}
		result, err = handler.commands.RevokeGatheringInvitation(
			request.Context(),
			targetParticipationCommand(gatheringID, body),
		)
	case "leave":
		var body participationVersionBody
		if !decodeParticipationBody(writer, request, &body) {
			return true
		}
		result, err = handler.commands.LeaveGathering(
			request.Context(),
			participationVersionCommand(gatheringID, body),
		)
	case "remove":
		var body targetParticipationBody
		if !decodeParticipationBody(writer, request, &body) {
			return true
		}
		result, err = handler.commands.RemoveGatheringParticipant(
			request.Context(),
			targetParticipationCommand(gatheringID, body),
		)
	case "reinstate":
		var body targetParticipationBody
		if !decodeParticipationBody(writer, request, &body) {
			return true
		}
		result, err = handler.commands.ReinstateGatheringParticipant(
			request.Context(),
			targetParticipationCommand(gatheringID, body),
		)
	case "pause-admission":
		var body changeAdmissionBody
		if !decodeParticipationBody(writer, request, &body) {
			return true
		}
		result, err = handler.commands.PauseGatheringAdmission(
			request.Context(),
			changeAdmissionCommand(gatheringID, body),
		)
	case "resume-admission":
		var body changeAdmissionBody
		if !decodeParticipationBody(writer, request, &body) {
			return true
		}
		result, err = handler.commands.ResumeGatheringAdmission(
			request.Context(),
			changeAdmissionCommand(gatheringID, body),
		)
	case "change-capacity":
		var body changeCapacityBody
		if !decodeParticipationBody(writer, request, &body) {
			return true
		}
		result, err = handler.commands.ChangeGatheringCapacity(
			request.Context(),
			app.ChangeGatheringCapacityCommand{
				GatheringID:               gatheringID,
				MaxParticipants:           body.MaxParticipants,
				ExpectedGatheringVersion:  body.ExpectedGatheringVersion,
				AcknowledgementDeadlineAt: body.AcknowledgementDeadlineAt,
			},
		)
	case "watch-availability":
		var body availabilityWatchBody
		if !decodeParticipationBody(writer, request, &body) {
			return true
		}
		result, err = handler.commands.WatchGatheringAvailability(
			request.Context(),
			app.GatheringAvailabilityWatchCommand{
				GatheringID:              gatheringID,
				ExpectedGatheringVersion: body.ExpectedGatheringVersion,
				ExpectedWatchVersion:     body.ExpectedWatchVersion,
			},
		)
	case "unwatch-availability":
		var body availabilityWatchBody
		if !decodeParticipationBody(writer, request, &body) {
			return true
		}
		result, err = handler.commands.UnwatchGatheringAvailability(
			request.Context(),
			app.GatheringAvailabilityWatchCommand{
				GatheringID:              gatheringID,
				ExpectedGatheringVersion: body.ExpectedGatheringVersion,
				ExpectedWatchVersion:     body.ExpectedWatchVersion,
			},
		)
	}
	if err != nil {
		writeError(writer, request, err)
		return true
	}
	writeJSON(writer, stdhttp.StatusOK, result)
	return true
}

var participationActions = map[string]struct{}{
	"join-open": {}, "apply": {}, "withdraw-application": {},
	"review-application": {}, "invite": {}, "accept-invitation": {},
	"decline-invitation": {}, "revoke-invitation": {}, "leave": {},
	"remove": {}, "reinstate": {}, "pause-admission": {},
	"resume-admission": {}, "change-capacity": {},
	"watch-availability": {}, "unwatch-availability": {},
}

// IsParticipationAction reports whether the shared Gathering dispatcher routes
// the action to the participation command facade.
func IsParticipationAction(action string) bool {
	_, exists := participationActions[action]
	return exists
}

func decodeParticipationBody(
	writer stdhttp.ResponseWriter,
	request *stdhttp.Request,
	target any,
) bool {
	if err := readStrictJSON(request, target); err != nil {
		writeError(
			writer,
			request,
			rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()),
		)
		return false
	}
	return true
}

func participationVersionCommand(
	gatheringID string,
	body participationVersionBody,
) app.GatheringParticipationVersionCommand {
	return app.GatheringParticipationVersionCommand{
		GatheringID:                  gatheringID,
		ExpectedGatheringVersion:     body.ExpectedGatheringVersion,
		ExpectedParticipationVersion: body.ExpectedParticipationVersion,
	}
}

func targetParticipationCommand(
	gatheringID string,
	body targetParticipationBody,
) app.TargetGatheringParticipationCommand {
	return app.TargetGatheringParticipationCommand{
		GatheringID:                  gatheringID,
		ParticipantPersonaID:         body.ParticipantPersonaID,
		ReasonRef:                    body.ReasonRef,
		ExpectedGatheringVersion:     body.ExpectedGatheringVersion,
		ExpectedParticipationVersion: body.ExpectedParticipationVersion,
	}
}

func changeAdmissionCommand(
	gatheringID string,
	body changeAdmissionBody,
) app.ChangeGatheringAdmissionCommand {
	return app.ChangeGatheringAdmissionCommand{
		GatheringID:                     gatheringID,
		ReasonRef:                       body.ReasonRef,
		ExpectedGatheringVersion:        body.ExpectedGatheringVersion,
		ExpectedAdmissionControlVersion: body.ExpectedAdmissionControlVersion,
	}
}
