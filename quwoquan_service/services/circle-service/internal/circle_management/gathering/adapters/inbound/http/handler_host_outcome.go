package http

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	stdhttp "net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	gatheringclient "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/client"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	gatheringapp "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
)

type HostOutcomeHandler struct {
	facade *gatheringapp.HostOutcomeFacade
}

func NewHostOutcomeHandler(facade *gatheringapp.HostOutcomeFacade) *HostOutcomeHandler {
	if facade == nil {
		panic("Gathering HostOutcomeHandler requires HostOutcomeFacade")
	}
	return &HostOutcomeHandler{facade: facade}
}

// ResolveAction is consumed by the single shared /gatherings/{resource}
// dispatcher. net/http ServeMux cannot register a wildcard followed by a
// literal ":action" suffix, and registering another generic resource pattern
// would conflict with LifecycleHandler. The shared dispatcher must set the
// canonical gatheringId path value before invoking the returned handler.
func (handler *HostOutcomeHandler) ResolveAction(
	action string,
) (stdhttp.HandlerFunc, bool) {
	switch strings.TrimSpace(action) {
	case "assign-co-host":
		return handler.AssignCoHost, true
	case "revoke-co-host":
		return handler.RevokeCoHost, true
	case "transfer-organizer":
		return handler.TransferOrganizer, true
	case "acknowledge-revision":
		return handler.AcknowledgeRevision, true
	case "declare-arrival":
		return handler.DeclareArrival, true
	case "leave-early":
		return handler.DeclareLeaveEarly, true
	case "complete-self":
		return handler.CompleteSelf, true
	default:
		return nil, false
	}
}

func (handler *HostOutcomeHandler) AssignCoHost(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	var body struct {
		CoHostPersonaID          string `json:"coHostPersonaId"`
		AuthorityEvidenceRef     string `json:"authorityEvidenceRef"`
		AuthorityVersion         int64  `json:"authorityVersion"`
		ExpectedGatheringVersion int64  `json:"expectedGatheringVersion"`
	}
	if !decodeHostOutcomeCommand(writer, request, &body) {
		return
	}
	result, err := handler.facade.AssignCoHost(request.Context(), gatheringapp.AssignCoHostCommand{
		GatheringID:              request.PathValue("gatheringId"),
		CoHostPersonaID:          body.CoHostPersonaID,
		AuthorityEvidenceRef:     body.AuthorityEvidenceRef,
		AuthorityVersion:         body.AuthorityVersion,
		ExpectedGatheringVersion: body.ExpectedGatheringVersion,
	})
	respondHostOutcomeCommand(writer, request, result, err)
}

func (handler *HostOutcomeHandler) RevokeCoHost(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	var body struct {
		ParticipantPersonaID         string `json:"participantPersonaId"`
		ReasonRef                    string `json:"reasonRef"`
		ExpectedGatheringVersion     int64  `json:"expectedGatheringVersion"`
		ExpectedParticipationVersion int64  `json:"expectedParticipationVersion"`
	}
	if !decodeHostOutcomeCommand(writer, request, &body) {
		return
	}
	result, err := handler.facade.RevokeCoHost(request.Context(), gatheringapp.RevokeCoHostCommand{
		GatheringID:                  request.PathValue("gatheringId"),
		CoHostPersonaID:              body.ParticipantPersonaID,
		ReasonRef:                    body.ReasonRef,
		ExpectedGatheringVersion:     body.ExpectedGatheringVersion,
		ExpectedParticipationVersion: body.ExpectedParticipationVersion,
	})
	respondHostOutcomeCommand(writer, request, result, err)
}

func (handler *HostOutcomeHandler) TransferOrganizer(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	var body struct {
		NewPrimaryOrganizerPersonaID string `json:"newPrimaryOrganizerPersonaId"`
		AuthorityEvidenceRef         string `json:"authorityEvidenceRef"`
		AuthorityVersion             int64  `json:"authorityVersion"`
		ExpectedGatheringVersion     int64  `json:"expectedGatheringVersion"`
	}
	if !decodeHostOutcomeCommand(writer, request, &body) {
		return
	}
	result, err := handler.facade.TransferOrganizer(request.Context(), gatheringapp.TransferOrganizerCommand{
		GatheringID:                  request.PathValue("gatheringId"),
		NewPrimaryOrganizerPersonaID: body.NewPrimaryOrganizerPersonaID,
		AuthorityEvidenceRef:         body.AuthorityEvidenceRef,
		AuthorityVersion:             body.AuthorityVersion,
		ExpectedGatheringVersion:     body.ExpectedGatheringVersion,
	})
	respondHostOutcomeCommand(writer, request, result, err)
}

func (handler *HostOutcomeHandler) AcknowledgeRevision(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	var body struct {
		RevisionID                   string                                                   `json:"revisionId"`
		RevisionDigest               string                                                   `json:"revisionDigest"`
		Decision                     gatheringclient.GatheringRevisionAcknowledgementDecision `json:"decision"`
		ExpectedGatheringVersion     int64                                                    `json:"expectedGatheringVersion"`
		ExpectedParticipationVersion int64                                                    `json:"expectedParticipationVersion"`
	}
	if !decodeHostOutcomeCommand(writer, request, &body) {
		return
	}
	result, err := handler.facade.AcknowledgeRevision(request.Context(), gatheringapp.AcknowledgeRevisionCommand{
		GatheringID:                  request.PathValue("gatheringId"),
		RevisionID:                   body.RevisionID,
		RevisionDigest:               body.RevisionDigest,
		Decision:                     body.Decision,
		ExpectedGatheringVersion:     body.ExpectedGatheringVersion,
		ExpectedParticipationVersion: body.ExpectedParticipationVersion,
	})
	respondHostOutcomeCommand(writer, request, result, err)
}

func (handler *HostOutcomeHandler) DeclareArrival(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	handler.attendance(writer, request, handler.facade.DeclareArrival)
}

func (handler *HostOutcomeHandler) DeclareLeaveEarly(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	handler.attendance(writer, request, handler.facade.DeclareLeaveEarly)
}

func (handler *HostOutcomeHandler) CompleteSelf(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	handler.attendance(writer, request, handler.facade.CompleteSelf)
}

type attendanceCommandHandler func(
	context.Context,
	gatheringapp.AttendanceCommand,
) (gatheringapp.HostOutcomeCommandResult, error)

func (handler *HostOutcomeHandler) attendance(
	writer stdhttp.ResponseWriter,
	request *stdhttp.Request,
	apply attendanceCommandHandler,
) {
	var body struct {
		EvidenceRefs                 []contract.CanonicalObjectRef `json:"evidenceRefs"`
		ExpectedGatheringVersion     int64                         `json:"expectedGatheringVersion"`
		ExpectedParticipationVersion int64                         `json:"expectedParticipationVersion"`
	}
	if !decodeHostOutcomeCommand(writer, request, &body) {
		return
	}
	result, err := apply(request.Context(), gatheringapp.AttendanceCommand{
		GatheringID:                  request.PathValue("gatheringId"),
		EvidenceRefs:                 body.EvidenceRefs,
		ExpectedGatheringVersion:     body.ExpectedGatheringVersion,
		ExpectedParticipationVersion: body.ExpectedParticipationVersion,
	})
	respondHostOutcomeCommand(writer, request, result, err)
}

func decodeHostOutcomeCommand(
	writer stdhttp.ResponseWriter,
	request *stdhttp.Request,
	target any,
) bool {
	if strings.TrimSpace(request.PathValue("gatheringId")) == "" {
		writeHostOutcomeError(
			writer,
			request,
			rterr.NewInvalidArgument(
				rterr.ModuleCircle,
				"无效路径",
				"Gathering id is required",
			),
		)
		return false
	}
	decoder := json.NewDecoder(io.LimitReader(request.Body, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		writeHostOutcomeError(
			writer,
			request,
			rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()),
		)
		return false
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		if err == nil {
			err = fmt.Errorf("request body must contain exactly one JSON object")
		}
		writeHostOutcomeError(
			writer,
			request,
			rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()),
		)
		return false
	}
	return true
}

func respondHostOutcomeCommand(
	writer stdhttp.ResponseWriter,
	request *stdhttp.Request,
	result gatheringapp.HostOutcomeCommandResult,
	err error,
) {
	if err == nil && result.AuditFact.Operation != "" {
		fact := result.AuditFact
		slog.InfoContext(
			request.Context(),
			"Gathering Host/Outcome command committed",
			"operation", fact.Operation,
			"gatheringId", result.GatheringID,
			"aggregateVersion", result.AggregateVersion,
			"actorPersonaId", fact.ActorPersonaID,
			"participantPersonaId", fact.ParticipantPersonaID,
			"hostSubjectKind", fact.HostSubjectKind,
			"hostSubjectId", fact.HostSubjectID,
			"authorityEvidenceRef", fact.AuthorityEvidenceRef,
			"authorityVersion", fact.AuthorityVersion,
			"revisionId", fact.RevisionID,
			"revisionNumber", fact.RevisionNumber,
			"outcomeStatus", fact.OutcomeStatus,
			"occurredAt", fact.OccurredAt,
			"idempotentReplay", result.IdempotentReplay,
		)
	}
	if err != nil {
		writeHostOutcomeError(writer, request, err)
		return
	}
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(stdhttp.StatusOK)
	if encodeErr := json.NewEncoder(writer).Encode(result); encodeErr != nil {
		slog.WarnContext(
			request.Context(),
			"Gathering Host/Outcome response encode failed",
			"error",
			encodeErr,
		)
	}
}

func writeHostOutcomeError(
	writer stdhttp.ResponseWriter,
	request *stdhttp.Request,
	err error,
) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
