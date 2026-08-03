package http

import (
	"errors"
	stdhttp "net/http"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/generated/operationsecurity"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/httpcodec"
	"quwoquan_service/runtime/operation"
	triperrors "quwoquan_service/services/travel-service/generated/travel/trip_plan"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/ports"
	revisionmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/model"
)

const (
	createOperation             = "travel.trip_plan.CreateTripPlan"
	createFromTemplateOperation = "travel.trip_plan.CreateTripPlanFromTemplate"
	getOperation                = "travel.trip_plan.GetTripPlan"
	listOperation               = "travel.trip_plan.ListTripPlans"
	reviseOperation             = "travel.trip_plan.ReviseTripPlan"
	transitionOperation         = "travel.trip_plan.TransitionTripPlan"
)

type Handler struct {
	service *application.Service
}

func NewHandler(service *application.Service) *Handler {
	if service == nil {
		panic("TripPlan HTTP handler requires service")
	}
	return &Handler{service: service}
}

func (handler *Handler) RegisterRoutes(mux *stdhttp.ServeMux) {
	if mux == nil {
		panic("TripPlan HTTP handler requires ServeMux")
	}
	mux.HandleFunc(mustPattern(createOperation), handler.handleCreate)
	mux.HandleFunc(mustPattern(createFromTemplateOperation), handler.handleCreateFromTemplate)
	mux.HandleFunc(mustPattern(getOperation), handler.handleGet)
	mux.HandleFunc(mustPattern(listOperation), handler.handleList)
	mux.HandleFunc(mustPattern(reviseOperation), handler.handleRevise)
	mux.HandleFunc(mustPattern(transitionOperation), handler.handleTransition)
}

type placeRefBody struct {
	ObjectTypeRef string `json:"objectTypeRef"`
	ObjectID      string `json:"objectId"`
}

type itemBody struct {
	ItemID     string        `json:"itemId"`
	DayIndex   int           `json:"dayIndex"`
	OrderInDay int           `json:"orderInDay"`
	Kind       string        `json:"kind"`
	Title      string        `json:"title"`
	StartAt    *time.Time    `json:"startAt"`
	EndAt      *time.Time    `json:"endAt"`
	PlaceRef   *placeRefBody `json:"placeRef"`
	Note       string        `json:"note"`
}

type createBody struct {
	Title   string     `json:"title"`
	StartAt *time.Time `json:"startAt"`
	EndAt   *time.Time `json:"endAt"`
	Items   []itemBody `json:"items"`
}

type createFromTemplateBody struct {
	Title   string     `json:"title"`
	StartAt *time.Time `json:"startAt"`
	EndAt   *time.Time `json:"endAt"`
}

type reviseBody struct {
	ExpectedRevisionNumber *int64     `json:"expectedRevisionNumber"`
	ChangeReason           string     `json:"changeReason"`
	Severity               string     `json:"severity"`
	Items                  []itemBody `json:"items"`
}

type transitionBody struct {
	ExpectedRevisionNumber *int64 `json:"expectedRevisionNumber"`
	TargetStatus           string `json:"targetStatus"`
}

func (handler *Handler) handleCreate(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, idempotencyKey, err := commandAttribution(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	var body createBody
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil || body.Items == nil {
		writeError(writer, request, invalidArgument(err, "items is required"))
		return
	}
	result, err := handler.service.Create(request.Context(), application.CreateCommand{
		ActorPersonaID: actor,
		IdempotencyKey: idempotencyKey,
		Title:          body.Title,
		StartAt:        body.StartAt,
		EndAt:          body.EndAt,
		Items:          toItemInputs(body.Items),
	})
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusCreated, commandResult(result), "travel_trip_plan")
}

func (handler *Handler) handleCreateFromTemplate(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, idempotencyKey, err := commandAttribution(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	var body createFromTemplateBody
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil {
		writeError(writer, request, invalidArgument(err, "template trip request is invalid"))
		return
	}
	result, err := handler.service.CreateFromTemplate(request.Context(), application.CreateFromTemplateCommand{
		ActorPersonaID: actor,
		IdempotencyKey: idempotencyKey,
		TemplateID:     strings.TrimSpace(request.PathValue("templateId")),
		Title:          body.Title,
		StartAt:        body.StartAt,
		EndAt:          body.EndAt,
	})
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusCreated, commandResult(result), "travel_trip_plan")
}

func (handler *Handler) handleGet(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, err := queryActor(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	plan, revision, err := handler.service.Get(
		request.Context(), actor, strings.TrimSpace(request.PathValue("tripId")),
	)
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, tripPlanSlice(plan, revision), "travel_trip_plan")
}

func (handler *Handler) handleList(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, err := queryActor(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	limit, err := optionalListLimit(request.URL.Query().Get("limit"))
	if err != nil {
		writeError(writer, request, invalidArgument(err, "limit is invalid"))
		return
	}
	page, err := handler.service.List(request.Context(), application.ListQuery{
		ActorPersonaID: actor,
		Status:         model.Status(strings.TrimSpace(request.URL.Query().Get("status"))),
		Cursor:         strings.TrimSpace(request.URL.Query().Get("cursor")),
		Limit:          limit,
	})
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	plans := make([]map[string]any, 0, len(page.Plans))
	for _, plan := range page.Plans {
		plans = append(plans, tripPlanSummarySlice(plan))
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, map[string]any{
		"plans": plans, "nextCursor": nullableString(page.NextCursor),
	}, "travel_trip_plan_list")
}

func (handler *Handler) handleRevise(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, idempotencyKey, err := commandAttribution(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	var body reviseBody
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil ||
		body.ExpectedRevisionNumber == nil || body.Items == nil {
		writeError(writer, request, invalidArgument(err, "expectedRevisionNumber and items are required"))
		return
	}
	result, err := handler.service.Revise(request.Context(), application.ReviseCommand{
		ActorPersonaID:         actor,
		IdempotencyKey:         idempotencyKey,
		TripID:                 strings.TrimSpace(request.PathValue("tripId")),
		ExpectedRevisionNumber: *body.ExpectedRevisionNumber,
		ChangeReason:           body.ChangeReason,
		Severity:               revisionmodel.Severity(body.Severity),
		Items:                  toItemInputs(body.Items),
	})
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, commandResult(result), "travel_trip_plan")
}

func (handler *Handler) handleTransition(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, idempotencyKey, err := commandAttribution(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	var body transitionBody
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil || body.ExpectedRevisionNumber == nil {
		writeError(writer, request, invalidArgument(err, "expectedRevisionNumber is required"))
		return
	}
	result, err := handler.service.Transition(request.Context(), application.TransitionCommand{
		ActorPersonaID:         actor,
		IdempotencyKey:         idempotencyKey,
		TripID:                 strings.TrimSpace(request.PathValue("tripId")),
		ExpectedRevisionNumber: *body.ExpectedRevisionNumber,
		TargetStatus:           model.Status(body.TargetStatus),
	})
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, commandResult(result), "travel_trip_plan")
}

func commandAttribution(request *stdhttp.Request) (string, string, error) {
	current, ok := operation.FromContext(request.Context())
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return "", "", triperrors.AppErrorFromTripPermissionDenied(
			"TripPlan command requires a verified persona operation context",
		)
	}
	idempotencyKey := strings.TrimSpace(current.IdempotencyKey)
	if idempotencyKey == "" {
		return "", "", triperrors.AppErrorFromInvalidArgument("idempotency key is required")
	}
	return strings.TrimSpace(current.Actor.PersonaID), idempotencyKey, nil
}

func queryActor(request *stdhttp.Request) (string, error) {
	current, ok := operation.FromContext(request.Context())
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return "", triperrors.AppErrorFromTripPermissionDenied(
			"TripPlan query requires a verified persona operation context",
		)
	}
	return strings.TrimSpace(current.Actor.PersonaID), nil
}

func toItemInputs(items []itemBody) []application.ItemInput {
	result := make([]application.ItemInput, 0, len(items))
	for _, item := range items {
		var place *model.PlaceRef
		if item.PlaceRef != nil {
			place = &model.PlaceRef{
				ObjectTypeRef: item.PlaceRef.ObjectTypeRef,
				ObjectID:      item.PlaceRef.ObjectID,
			}
		}
		result = append(result, application.ItemInput{
			ItemID: item.ItemID, DayIndex: item.DayIndex, OrderInDay: item.OrderInDay,
			Kind: model.ItemKind(item.Kind), Title: item.Title, StartAt: item.StartAt,
			EndAt: item.EndAt, PlaceRef: place, Note: item.Note,
		})
	}
	return result
}

func commandResult(result ports.CommandResult) map[string]any {
	return map[string]any{
		"tripId": result.TripID, "version": result.Version,
		"currentRevisionId":     result.CurrentRevisionID,
		"currentRevisionNumber": result.CurrentRevisionNumber,
		"status":                result.Status, "idempotentReplay": result.IdempotentReplay,
	}
}

func tripPlanSlice(plan model.Plan, revision revisionmodel.Revision) map[string]any {
	return map[string]any{
		"tripId": plan.TripID, "version": plan.Version,
		"organizerPersonaId": plan.OrganizerPersonaID, "title": plan.Title,
		"status": plan.Status, "startAt": plan.StartAt, "endAt": plan.EndAt,
		"sourceTemplateId": nullableSourceTemplateID(plan), "sourceTemplateVersion": nullableSourceTemplateVersion(plan),
		"sourceAttributions":    plan.SourceAttributions,
		"currentRevisionId":     plan.CurrentRevisionID,
		"currentRevisionNumber": plan.CurrentRevisionNumber,
		"items":                 revision.Items, "createdAt": plan.CreatedAt, "updatedAt": plan.UpdatedAt,
	}
}

func tripPlanSummarySlice(plan model.Plan) map[string]any {
	return map[string]any{
		"tripId": plan.TripID, "title": plan.Title, "status": plan.Status,
		"startAt": plan.StartAt, "endAt": plan.EndAt,
		"currentRevisionId":     plan.CurrentRevisionID,
		"currentRevisionNumber": plan.CurrentRevisionNumber,
		"itemCount":             plan.CurrentItemCount, "updatedAt": plan.UpdatedAt,
	}
}

func nullableString(value string) any {
	if strings.TrimSpace(value) == "" {
		return nil
	}
	return value
}

func optionalListLimit(value string) (int, error) {
	raw := strings.TrimSpace(value)
	if raw == "" {
		return 0, nil
	}
	limit, err := strconv.Atoi(raw)
	if err != nil || limit < 1 || limit > 50 {
		return 0, model.ErrInvalidInput
	}
	return limit, nil
}

func nullableSourceTemplateID(plan model.Plan) any {
	if strings.TrimSpace(plan.SourceTemplateID) == "" {
		return nil
	}
	return plan.SourceTemplateID
}

func nullableSourceTemplateVersion(plan model.Plan) any {
	if plan.SourceTemplateVersion == 0 {
		return nil
	}
	return plan.SourceTemplateVersion
}

func invalidArgument(decodeErr error, fallback string) error {
	if decodeErr != nil {
		return triperrors.AppErrorFromInvalidArgument(decodeErr.Error())
	}
	return triperrors.AppErrorFromInvalidArgument(fallback)
}

func mapApplicationError(err error) error {
	switch {
	case errors.Is(err, model.ErrInvalidInput):
		return triperrors.AppErrorFromInvalidArgument(err.Error())
	case errors.Is(err, ports.ErrNotFound):
		return triperrors.AppErrorFromTripNotFound(err.Error())
	case errors.Is(err, application.ErrTemplateNotFound):
		return triperrors.AppErrorFromTripTemplateNotFound(err.Error())
	case errors.Is(err, application.ErrTemplatePermissionDenied):
		return triperrors.AppErrorFromTripTemplatePermissionDenied(err.Error())
	case errors.Is(err, application.ErrTemplateUnavailable):
		return triperrors.AppErrorFromTripTemplateUnavailable(err.Error())
	case errors.Is(err, model.ErrPermissionDenied):
		return triperrors.AppErrorFromTripPermissionDenied(err.Error())
	case errors.Is(err, model.ErrRevisionConflict), errors.Is(err, ports.ErrCommitConflict):
		return triperrors.AppErrorFromTripRevisionConflict(err.Error())
	case errors.Is(err, model.ErrInvalidTransition):
		return triperrors.AppErrorFromTripStateInvalid(err.Error())
	case errors.Is(err, ports.ErrIdempotencyConflict):
		return triperrors.AppErrorFromTripIdempotencyConflict(err.Error())
	default:
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return err
		}
		return triperrors.AppErrorFromTripStorageFailed(err.Error())
	}
}

func mustPattern(canonicalOperationID string) string {
	for _, descriptor := range operationsecurity.ForDomain("travel") {
		if descriptor.CanonicalOperationID == canonicalOperationID {
			return descriptor.Method + " " + descriptor.PathTemplate
		}
	}
	panic("missing generated TripPlan operation descriptor: " + canonicalOperationID)
}

func writeError(writer stdhttp.ResponseWriter, request *stdhttp.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
