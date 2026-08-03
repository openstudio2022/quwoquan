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
	momenterrors "quwoquan_service/services/travel-service/generated/travel/trip_moment"
	triperrors "quwoquan_service/services/travel-service/generated/travel/trip_plan"
	membershipmodel "quwoquan_service/services/travel-service/internal/travel/trip_membership/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_moment/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/ports"
	tripports "quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/ports"
	revisionmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/model"
)

const (
	createOperation = "travel.trip_moment.CreateTripMoment"
	assignOperation = "travel.trip_moment.AssignTripMoment"
	deleteOperation = "travel.trip_moment.DeleteTripMoment"
	listOperation   = "travel.trip_moment.ListTripMoments"
)

type Handler struct {
	service *application.Service
}

func NewHandler(service *application.Service) *Handler {
	if service == nil {
		panic("TripMoment HTTP handler requires service")
	}
	return &Handler{service: service}
}

func (handler *Handler) RegisterRoutes(mux *stdhttp.ServeMux) {
	if mux == nil {
		panic("TripMoment HTTP handler requires ServeMux")
	}
	mux.HandleFunc(mustPattern(createOperation), handler.handleCreate)
	mux.HandleFunc(mustPattern(assignOperation), handler.handleAssign)
	mux.HandleFunc(mustPattern(deleteOperation), handler.handleDelete)
	mux.HandleFunc(mustPattern(listOperation), handler.handleList)
}

type objectRefBody struct {
	ObjectTypeRef string `json:"objectTypeRef"`
	ObjectID      string `json:"objectId"`
}

type createBody struct {
	RevisionNumber   *int64         `json:"revisionNumber"`
	DayIndex         *int           `json:"dayIndex"`
	ItemID           string         `json:"itemId"`
	Kind             string         `json:"kind"`
	ContentRef       *objectRefBody `json:"contentRef"`
	InlineText       string         `json:"inlineText"`
	CapturedAt       *time.Time     `json:"capturedAt"`
	CoarsePlaceRef   *objectRefBody `json:"coarsePlaceRef"`
	Visibility       string         `json:"visibility"`
	AssignmentStatus string         `json:"assignmentStatus"`
	SourceVersion    *int64         `json:"sourceVersion"`
}

type assignBody struct {
	ExpectedVersion *int64 `json:"expectedVersion"`
	RevisionNumber  *int64 `json:"revisionNumber"`
	DayIndex        *int   `json:"dayIndex"`
	ItemID          string `json:"itemId"`
	Visibility      string `json:"visibility"`
	SourceVersion   *int64 `json:"sourceVersion"`
}

type deleteBody struct {
	ExpectedVersion *int64 `json:"expectedVersion"`
	Reason          string `json:"reason"`
}

func (handler *Handler) handleCreate(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, key, err := commandAttribution(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	var body createBody
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil || body.RevisionNumber == nil ||
		body.CapturedAt == nil || body.SourceVersion == nil {
		writeError(writer, request, invalidArgument(err, "revisionNumber, capturedAt and sourceVersion are required"))
		return
	}
	result, err := handler.service.Create(request.Context(), application.CreateCommand{
		ActorPersonaID: actor, IdempotencyKey: key,
		TripID: strings.TrimSpace(request.PathValue("tripId")), RevisionNumber: *body.RevisionNumber,
		DayIndex: body.DayIndex, ItemID: body.ItemID, Kind: model.Kind(body.Kind),
		ContentRef: toObjectRef(body.ContentRef), InlineText: body.InlineText, CapturedAt: *body.CapturedAt,
		CoarsePlaceRef: toObjectRef(body.CoarsePlaceRef), Visibility: model.Visibility(body.Visibility),
		AssignmentStatus: model.AssignmentStatus(body.AssignmentStatus), SourceVersion: *body.SourceVersion,
	})
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusCreated, momentSlice(result.Moment), "travel_trip_moment")
}

func (handler *Handler) handleAssign(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, key, err := commandAttribution(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	var body assignBody
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil || body.ExpectedVersion == nil ||
		body.RevisionNumber == nil || body.DayIndex == nil || body.SourceVersion == nil {
		writeError(writer, request, invalidArgument(err, "assignment version and target are required"))
		return
	}
	result, err := handler.service.Assign(request.Context(), application.AssignCommand{
		ActorPersonaID: actor, IdempotencyKey: key,
		TripID:          strings.TrimSpace(request.PathValue("tripId")),
		MomentID:        strings.TrimSpace(request.PathValue("momentId")),
		ExpectedVersion: *body.ExpectedVersion, RevisionNumber: *body.RevisionNumber,
		DayIndex: *body.DayIndex, ItemID: body.ItemID, Visibility: model.Visibility(body.Visibility),
		SourceVersion: *body.SourceVersion,
	})
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, momentSlice(result.Moment), "travel_trip_moment")
}

func (handler *Handler) handleDelete(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, key, err := commandAttribution(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	var body deleteBody
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil || body.ExpectedVersion == nil {
		writeError(writer, request, invalidArgument(err, "expectedVersion is required"))
		return
	}
	result, err := handler.service.Delete(request.Context(), application.DeleteCommand{
		ActorPersonaID: actor, IdempotencyKey: key,
		TripID:          strings.TrimSpace(request.PathValue("tripId")),
		MomentID:        strings.TrimSpace(request.PathValue("momentId")),
		ExpectedVersion: *body.ExpectedVersion, Reason: body.Reason,
	})
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, momentSlice(result.Moment), "travel_trip_moment")
}

func (handler *Handler) handleList(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, err := queryActor(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	tripID := strings.TrimSpace(request.PathValue("tripId"))
	moments, err := handler.service.List(request.Context(), actor, tripID)
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	items := make([]map[string]any, 0, len(moments))
	for _, moment := range moments {
		items = append(items, momentSlice(moment))
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, map[string]any{
		"tripId": tripID, "moments": items,
	}, "travel_trip_moment")
}

func toObjectRef(body *objectRefBody) *model.ObjectRef {
	if body == nil {
		return nil
	}
	return &model.ObjectRef{ObjectTypeRef: body.ObjectTypeRef, ObjectID: body.ObjectID}
}

func momentSlice(moment model.Moment) map[string]any {
	return map[string]any{
		"momentId": moment.MomentID, "version": moment.Version, "tripId": moment.TripID,
		"revisionNumber": moment.RevisionNumber, "dayIndex": moment.DayIndex, "itemId": moment.ItemID,
		"kind": moment.Kind, "contentRef": moment.ContentRef, "inlineText": moment.InlineText,
		"capturedAt": moment.CapturedAt, "coarsePlaceRef": moment.CoarsePlaceRef,
		"visibility": moment.Visibility, "assignmentStatus": moment.AssignmentStatus,
		"attributionPersonaId": moment.AttributionPersonaID, "sourceVersion": moment.SourceVersion,
		"status": moment.Status, "createdAt": moment.CreatedAt, "updatedAt": moment.UpdatedAt,
	}
}

func commandAttribution(request *stdhttp.Request) (string, string, error) {
	current, ok := operation.FromContext(request.Context())
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return "", "", triperrors.AppErrorFromTripPermissionDenied(
			"TripMoment command requires a verified persona operation context",
		)
	}
	key := strings.TrimSpace(current.IdempotencyKey)
	if key == "" {
		return "", "", momenterrors.AppErrorFromTripMomentInvalidArgument("idempotency key is required")
	}
	return strings.TrimSpace(current.Actor.PersonaID), key, nil
}

func queryActor(request *stdhttp.Request) (string, error) {
	current, ok := operation.FromContext(request.Context())
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return "", triperrors.AppErrorFromTripPermissionDenied(
			"TripMoment query requires a verified persona operation context",
		)
	}
	return strings.TrimSpace(current.Actor.PersonaID), nil
}

func invalidArgument(decodeErr error, fallback string) error {
	if decodeErr != nil {
		return momenterrors.AppErrorFromTripMomentInvalidArgument(decodeErr.Error())
	}
	return momenterrors.AppErrorFromTripMomentInvalidArgument(fallback)
}

func mapApplicationError(err error) error {
	switch {
	case errors.Is(err, model.ErrInvalidArgument), errors.Is(err, revisionmodel.ErrInvalidRevision):
		return momenterrors.AppErrorFromTripMomentInvalidArgument(err.Error())
	case errors.Is(err, ports.ErrNotFound):
		return momenterrors.AppErrorFromTripMomentNotFound(err.Error())
	case errors.Is(err, tripports.ErrNotFound):
		return triperrors.AppErrorFromTripNotFound(err.Error())
	case errors.Is(err, model.ErrPermissionDenied), errors.Is(err, membershipmodel.ErrPermissionDenied):
		return triperrors.AppErrorFromTripPermissionDenied(err.Error())
	case errors.Is(err, model.ErrRevisionConflict), errors.Is(err, ports.ErrCommitConflict):
		return momenterrors.AppErrorFromTripMomentRevisionConflict(err.Error())
	case errors.Is(err, ports.ErrIdempotencyConflict):
		return momenterrors.AppErrorFromTripMomentIdempotencyConflict(err.Error())
	case errors.Is(err, ports.ErrReferenceUnavailable):
		return momenterrors.AppErrorFromTripMomentReferenceUnavailable(err.Error())
	default:
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return err
		}
		return momenterrors.AppErrorFromTripMomentStorageFailed(err.Error())
	}
}

func mustPattern(operationID string) string {
	for _, descriptor := range operationsecurity.ForDomain("travel") {
		if descriptor.CanonicalOperationID == operationID {
			return descriptor.Method + " " + descriptor.PathTemplate
		}
	}
	panic("missing generated TripMoment operation descriptor: " + operationID)
}

func writeError(writer stdhttp.ResponseWriter, request *stdhttp.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
