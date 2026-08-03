package http

import (
	"errors"
	stdhttp "net/http"
	"strings"

	"quwoquan_service/generated/operationsecurity"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/httpcodec"
	"quwoquan_service/runtime/operation"
	templateerrors "quwoquan_service/services/travel-service/generated/travel/trip_plan_template"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/ports"
)

const (
	createOperation = "travel.trip_plan_template.CreateTripPlanTemplate"
	reviseOperation = "travel.trip_plan_template.ReviseTripPlanTemplate"
	getOperation    = "travel.trip_plan_template.GetTripPlanTemplate"
	listOperation   = "travel.trip_plan_template.ListTripPlanTemplates"
)

type Handler struct{ service *application.Service }

func NewHandler(service *application.Service) *Handler {
	if service == nil {
		panic("TripPlanTemplate HTTP handler requires service")
	}
	return &Handler{service: service}
}
func (handler *Handler) RegisterRoutes(mux *stdhttp.ServeMux) {
	if mux == nil {
		panic("TripPlanTemplate HTTP handler requires ServeMux")
	}
	mux.HandleFunc(mustPattern(createOperation), handler.handleCreate)
	mux.HandleFunc(mustPattern(reviseOperation), handler.handleRevise)
	mux.HandleFunc(mustPattern(getOperation), handler.handleGet)
	mux.HandleFunc(mustPattern(listOperation), handler.handleList)
}

type createBody struct {
	Title        string              `json:"title"`
	Summary      string              `json:"summary"`
	DayCount     int                 `json:"dayCount"`
	Items        []model.Item        `json:"items"`
	Attributions []model.Attribution `json:"attributions"`
}

func (body createBody) input() model.PutInput {
	return model.PutInput{Title: body.Title, Summary: body.Summary, DayCount: body.DayCount, Items: body.Items, Attributions: body.Attributions}
}

type reviseBody struct {
	ExpectedVersion int64               `json:"expectedVersion"`
	Title           string              `json:"title"`
	Summary         string              `json:"summary"`
	DayCount        int                 `json:"dayCount"`
	Items           []model.Item        `json:"items"`
	Attributions    []model.Attribution `json:"attributions"`
}

func (body reviseBody) input() model.PutInput {
	return model.PutInput{Title: body.Title, Summary: body.Summary, DayCount: body.DayCount, Items: body.Items, Attributions: body.Attributions}
}

func (handler *Handler) handleCreate(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, key, err := commandActor(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	var body createBody
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil || body.Items == nil || body.Attributions == nil {
		writeError(writer, request, templateerrors.AppErrorFromTripPlanTemplateInvalidArgument(errorText(err, "items and attributions are required")))
		return
	}
	result, err := handler.service.Create(request.Context(), application.PutCommand{ActorPersonaID: actor, IdempotencyKey: key, Input: body.input()})
	if err != nil {
		writeError(writer, request, mapError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusCreated, result.Template, "travel_trip_plan_template")
}
func (handler *Handler) handleRevise(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, key, err := commandActor(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	var body reviseBody
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil || body.Items == nil || body.Attributions == nil {
		writeError(writer, request, templateerrors.AppErrorFromTripPlanTemplateInvalidArgument(errorText(err, "items and attributions are required")))
		return
	}
	result, err := handler.service.Revise(request.Context(), application.PutCommand{ActorPersonaID: actor, IdempotencyKey: key, TemplateID: request.PathValue("templateId"), ExpectedVersion: body.ExpectedVersion, Input: body.input()})
	if err != nil {
		writeError(writer, request, mapError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, result.Template, "travel_trip_plan_template")
}
func (handler *Handler) handleGet(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, err := queryActor(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	value, err := handler.service.Get(request.Context(), actor, request.PathValue("templateId"))
	if err != nil {
		writeError(writer, request, mapError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, value, "travel_trip_plan_template")
}
func (handler *Handler) handleList(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, err := queryActor(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	values, err := handler.service.List(request.Context(), actor)
	if err != nil {
		writeError(writer, request, mapError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, map[string]any{"templates": values}, "travel_trip_plan_template_list")
}

func queryActor(request *stdhttp.Request) (string, error) {
	current, ok := operation.FromContext(request.Context())
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return "", templateerrors.AppErrorFromTripPlanTemplatePermissionDenied("verified persona context required")
	}
	return strings.TrimSpace(current.Actor.PersonaID), nil
}
func commandActor(request *stdhttp.Request) (string, string, error) {
	current, ok := operation.FromContext(request.Context())
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return "", "", templateerrors.AppErrorFromTripPlanTemplatePermissionDenied("verified persona context required")
	}
	actor := strings.TrimSpace(current.Actor.PersonaID)
	key := strings.TrimSpace(current.IdempotencyKey)
	if key == "" {
		return "", "", templateerrors.AppErrorFromTripPlanTemplateInvalidArgument("idempotency key is required")
	}
	return actor, key, nil
}
func mapError(err error) error {
	switch {
	case errors.Is(err, model.ErrInvalidArgument):
		return templateerrors.AppErrorFromTripPlanTemplateInvalidArgument(err.Error())
	case errors.Is(err, model.ErrPermissionDenied):
		return templateerrors.AppErrorFromTripPlanTemplatePermissionDenied(err.Error())
	case errors.Is(err, model.ErrRevisionConflict):
		return templateerrors.AppErrorFromTripPlanTemplateRevisionConflict(err.Error())
	case errors.Is(err, ports.ErrNotFound):
		return templateerrors.AppErrorFromTripPlanTemplateNotFound(err.Error())
	case errors.Is(err, ports.ErrIdempotencyConflict):
		return templateerrors.AppErrorFromTripPlanTemplateIdempotencyConflict(err.Error())
	case errors.Is(err, ports.ErrReferenceUnavailable):
		return templateerrors.AppErrorFromTripPlanTemplateReferenceUnavailable(err.Error())
	default:
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return err
		}
		return templateerrors.AppErrorFromTripPlanTemplateStorageFailed(err.Error())
	}
}
func mustPattern(operationID string) string {
	for _, descriptor := range operationsecurity.ForDomain("travel") {
		if descriptor.CanonicalOperationID == operationID {
			return descriptor.Method + " " + descriptor.PathTemplate
		}
	}
	panic("missing generated TripPlanTemplate operation descriptor: " + operationID)
}
func errorText(err error, fallback string) string {
	if err != nil {
		return err.Error()
	}
	return fallback
}
func writeError(writer stdhttp.ResponseWriter, request *stdhttp.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
