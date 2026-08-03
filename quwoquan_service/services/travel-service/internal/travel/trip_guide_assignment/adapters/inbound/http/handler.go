package http

import (
	"errors"
	stdhttp "net/http"
	"strings"
	"time"

	"quwoquan_service/generated/operationsecurity"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/httpcodec"
	"quwoquan_service/runtime/operation"
	guideerrors "quwoquan_service/services/travel-service/generated/travel/trip_guide_assignment"
	"quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/domain/ports"
)

const (
	putOperation        = "travel.trip_guide_assignment.PutTripGuideAssignment"
	transitionOperation = "travel.trip_guide_assignment.TransitionTripGuideAssignment"
	listOperation       = "travel.trip_guide_assignment.ListTripGuideAssignments"
)

type Handler struct{ service *application.Service }

func NewHandler(service *application.Service) *Handler {
	if service == nil {
		panic("TripGuideAssignment HTTP handler requires service")
	}
	return &Handler{service: service}
}
func (handler *Handler) RegisterRoutes(mux *stdhttp.ServeMux) {
	if mux == nil {
		panic("TripGuideAssignment HTTP handler requires ServeMux")
	}
	mux.HandleFunc(mustPattern(putOperation), handler.handlePut)
	mux.HandleFunc(mustPattern(transitionOperation), handler.handleTransition)
	mux.HandleFunc(mustPattern(listOperation), handler.handleList)
}

type putBody struct {
	ExpectedVersion              int64                 `json:"expectedVersion"`
	TaskKey                      string                `json:"taskKey"`
	AssigneePersonaID            string                `json:"assigneePersonaId"`
	Role                         model.Role            `json:"role"`
	TaskKind                     model.TaskKind        `json:"taskKind"`
	Title                        string                `json:"title"`
	DueAt                        *time.Time            `json:"dueAt"`
	SourceRevisionNumber         int64                 `json:"sourceRevisionNumber"`
	AttributionKind              model.AttributionKind `json:"attributionKind"`
	AttributionPersonaID         string                `json:"attributionPersonaId"`
	PublicQualificationPersonaID string                `json:"publicQualificationPersonaId"`
}
type transitionBody struct {
	ExpectedVersion int64        `json:"expectedVersion"`
	TargetStatus    model.Status `json:"targetStatus"`
}

func (handler *Handler) handlePut(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, key, err := commandActor(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	var body putBody
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil {
		writeError(writer, request, guideerrors.AppErrorFromTripGuideAssignmentInvalidArgument(err.Error()))
		return
	}
	taskKey := strings.TrimSpace(request.PathValue("taskKey"))
	if taskKey != strings.TrimSpace(body.TaskKey) {
		writeError(writer, request, guideerrors.AppErrorFromTripGuideAssignmentInvalidArgument("taskKey path/body mismatch"))
		return
	}
	result, err := handler.service.Put(request.Context(), application.PutCommand{ActorPersonaID: actor, IdempotencyKey: key, TripID: request.PathValue("tripId"), TaskKey: taskKey, ExpectedVersion: body.ExpectedVersion, Input: model.PutInput{AssigneePersonaID: body.AssigneePersonaID, Role: body.Role, TaskKind: body.TaskKind, Title: body.Title, DueAt: body.DueAt, SourceRevisionNumber: body.SourceRevisionNumber, AttributionKind: body.AttributionKind, AttributionPersonaID: body.AttributionPersonaID, PublicQualificationPersonaID: body.PublicQualificationPersonaID}})
	if err != nil {
		writeError(writer, request, mapError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, result.Assignment, "travel_trip_guide_assignment")
}
func (handler *Handler) handleTransition(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, key, err := commandActor(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	var body transitionBody
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil {
		writeError(writer, request, guideerrors.AppErrorFromTripGuideAssignmentInvalidArgument(err.Error()))
		return
	}
	result, err := handler.service.Transition(request.Context(), application.TransitionCommand{ActorPersonaID: actor, IdempotencyKey: key, TripID: request.PathValue("tripId"), TaskKey: request.PathValue("taskKey"), ExpectedVersion: body.ExpectedVersion, TargetStatus: body.TargetStatus})
	if err != nil {
		writeError(writer, request, mapError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, result.Assignment, "travel_trip_guide_assignment")
}
func (handler *Handler) handleList(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, _, err := actorContext(request, false)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	tripID := strings.TrimSpace(request.PathValue("tripId"))
	values, err := handler.service.List(request.Context(), actor, tripID)
	if err != nil {
		writeError(writer, request, mapError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, map[string]any{"tripId": tripID, "assignments": values}, "travel_trip_guide_assignment_list")
}
func actorContext(request *stdhttp.Request, command bool) (string, string, error) {
	current, ok := operation.FromContext(request.Context())
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return "", "", guideerrors.AppErrorFromTripGuideAssignmentPermissionDenied("verified persona context required")
	}
	if !command {
		return strings.TrimSpace(current.Actor.PersonaID), "", nil
	}
	key := strings.TrimSpace(current.IdempotencyKey)
	if key == "" {
		return "", "", guideerrors.AppErrorFromTripGuideAssignmentInvalidArgument("idempotency key is required")
	}
	return strings.TrimSpace(current.Actor.PersonaID), key, nil
}
func commandActor(request *stdhttp.Request) (string, string, error) {
	return actorContext(request, true)
}
func mapError(err error) error {
	switch {
	case errors.Is(err, model.ErrInvalidArgument):
		return guideerrors.AppErrorFromTripGuideAssignmentInvalidArgument(err.Error())
	case errors.Is(err, model.ErrPermissionDenied):
		return guideerrors.AppErrorFromTripGuideAssignmentPermissionDenied(err.Error())
	case errors.Is(err, model.ErrRevisionConflict):
		return guideerrors.AppErrorFromTripGuideAssignmentRevisionConflict(err.Error())
	case errors.Is(err, model.ErrStateInvalid):
		return guideerrors.AppErrorFromTripGuideAssignmentStateInvalid(err.Error())
	case errors.Is(err, ports.ErrNotFound):
		return guideerrors.AppErrorFromTripGuideAssignmentNotFound(err.Error())
	case errors.Is(err, ports.ErrIdempotencyConflict):
		return guideerrors.AppErrorFromTripGuideAssignmentIdempotencyConflict(err.Error())
	case errors.Is(err, ports.ErrReferenceUnavailable):
		return guideerrors.AppErrorFromTripGuideAssignmentReferenceUnavailable(err.Error())
	default:
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return err
		}
		return guideerrors.AppErrorFromTripGuideAssignmentStorageFailed(err.Error())
	}
}
func mustPattern(operationID string) string {
	for _, descriptor := range operationsecurity.ForDomain("travel") {
		if descriptor.CanonicalOperationID == operationID {
			return descriptor.Method + " " + descriptor.PathTemplate
		}
	}
	panic("missing generated TripGuideAssignment operation descriptor: " + operationID)
}
func writeError(writer stdhttp.ResponseWriter, request *stdhttp.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
