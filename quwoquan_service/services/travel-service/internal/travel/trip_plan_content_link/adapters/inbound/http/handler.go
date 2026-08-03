package http

import (
	"errors"
	stdhttp "net/http"
	"strings"

	"quwoquan_service/generated/operationsecurity"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/httpcodec"
	"quwoquan_service/runtime/operation"
	triperrors "quwoquan_service/services/travel-service/generated/travel/trip_plan"
	linkerrors "quwoquan_service/services/travel-service/generated/travel/trip_plan_content_link"
	membershipmodel "quwoquan_service/services/travel-service/internal/travel/trip_membership/domain/model"
	tripports "quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/ports"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/domain/ports"
	revisionmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/model"
)

const (
	putOperation    = "travel.trip_plan_content_link.PutTripPlanContentLink"
	removeOperation = "travel.trip_plan_content_link.RemoveTripPlanContentLink"
	listOperation   = "travel.trip_plan_content_link.ListTripPlanContentLinks"
)

type Handler struct {
	service *application.Service
}

func NewHandler(service *application.Service) *Handler {
	if service == nil {
		panic("TripPlanContentLink HTTP handler requires service")
	}
	return &Handler{service: service}
}

func (handler *Handler) RegisterRoutes(mux *stdhttp.ServeMux) {
	if mux == nil {
		panic("TripPlanContentLink HTTP handler requires ServeMux")
	}
	mux.HandleFunc(mustPattern(putOperation), handler.handlePut)
	mux.HandleFunc(mustPattern(removeOperation), handler.handleRemove)
	mux.HandleFunc(mustPattern(listOperation), handler.handleList)
}

type putBody struct {
	ExpectedVersion *int64 `json:"expectedVersion"`
	RevisionNumber  *int64 `json:"revisionNumber"`
	TargetKind      string `json:"targetKind"`
	DayIndex        *int   `json:"dayIndex"`
	ItemID          string `json:"itemId"`
	Visibility      string `json:"visibility"`
	SourceVersion   *int64 `json:"sourceVersion"`
}

type removeBody struct {
	ExpectedVersion *int64 `json:"expectedVersion"`
	Reason          string `json:"reason"`
}

func (handler *Handler) handlePut(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, key, err := commandAttribution(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	var body putBody
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil || body.ExpectedVersion == nil ||
		body.RevisionNumber == nil || body.SourceVersion == nil {
		writeError(writer, request, invalidArgument(err, "link version and target are required"))
		return
	}
	result, err := handler.service.Put(request.Context(), application.PutCommand{
		ActorPersonaID: actor, IdempotencyKey: key,
		TripID:          strings.TrimSpace(request.PathValue("tripId")),
		PostID:          strings.TrimSpace(request.PathValue("postId")),
		ExpectedVersion: *body.ExpectedVersion, RevisionNumber: *body.RevisionNumber,
		TargetKind: model.TargetKind(body.TargetKind), DayIndex: body.DayIndex,
		ItemID: body.ItemID, Visibility: model.Visibility(body.Visibility),
		SourceVersion: *body.SourceVersion,
	})
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	status := stdhttp.StatusOK
	if result.Link.Version == 1 {
		status = stdhttp.StatusCreated
	}
	httpcodec.WriteJSON(writer, status, linkSlice(result.Link), "travel_trip_plan_content_link")
}

func (handler *Handler) handleRemove(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, key, err := commandAttribution(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	var body removeBody
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil || body.ExpectedVersion == nil {
		writeError(writer, request, invalidArgument(err, "expectedVersion is required"))
		return
	}
	result, err := handler.service.Remove(request.Context(), application.RemoveCommand{
		ActorPersonaID: actor, IdempotencyKey: key,
		TripID:          strings.TrimSpace(request.PathValue("tripId")),
		PostID:          strings.TrimSpace(request.PathValue("postId")),
		ExpectedVersion: *body.ExpectedVersion, Reason: body.Reason,
	})
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, linkSlice(result.Link), "travel_trip_plan_content_link")
}

func (handler *Handler) handleList(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, err := queryActor(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	tripID := strings.TrimSpace(request.PathValue("tripId"))
	links, err := handler.service.List(request.Context(), actor, tripID)
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	items := make([]map[string]any, 0, len(links))
	for _, link := range links {
		items = append(items, linkSlice(link))
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, map[string]any{
		"tripId": tripID, "links": items,
	}, "travel_trip_plan_content_link")
}

func linkSlice(link model.Link) map[string]any {
	return map[string]any{
		"linkId": link.LinkID, "version": link.Version, "tripId": link.TripID,
		"postId": link.PostID, "revisionNumber": link.RevisionNumber,
		"targetKind": link.TargetKind, "dayIndex": link.DayIndex, "itemId": link.ItemID, "visibility": link.Visibility,
		"linkedByPersonaId": link.LinkedByPersonaID, "sourceVersion": link.SourceVersion,
		"status": link.Status, "createdAt": link.CreatedAt, "updatedAt": link.UpdatedAt,
	}
}

func commandAttribution(request *stdhttp.Request) (string, string, error) {
	current, ok := operation.FromContext(request.Context())
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return "", "", triperrors.AppErrorFromTripPermissionDenied(
			"TripPlanContentLink command requires a verified persona operation context",
		)
	}
	key := strings.TrimSpace(current.IdempotencyKey)
	if key == "" {
		return "", "", linkerrors.AppErrorFromTripContentLinkInvalidArgument("idempotency key is required")
	}
	return strings.TrimSpace(current.Actor.PersonaID), key, nil
}

func queryActor(request *stdhttp.Request) (string, error) {
	current, ok := operation.FromContext(request.Context())
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return "", triperrors.AppErrorFromTripPermissionDenied(
			"TripPlanContentLink query requires a verified persona operation context",
		)
	}
	return strings.TrimSpace(current.Actor.PersonaID), nil
}

func invalidArgument(decodeErr error, fallback string) error {
	if decodeErr != nil {
		return linkerrors.AppErrorFromTripContentLinkInvalidArgument(decodeErr.Error())
	}
	return linkerrors.AppErrorFromTripContentLinkInvalidArgument(fallback)
}

func mapApplicationError(err error) error {
	switch {
	case errors.Is(err, model.ErrInvalidArgument), errors.Is(err, revisionmodel.ErrInvalidRevision):
		return linkerrors.AppErrorFromTripContentLinkInvalidArgument(err.Error())
	case errors.Is(err, ports.ErrNotFound):
		return linkerrors.AppErrorFromTripContentLinkNotFound(err.Error())
	case errors.Is(err, tripports.ErrNotFound):
		return triperrors.AppErrorFromTripNotFound(err.Error())
	case errors.Is(err, model.ErrPermissionDenied), errors.Is(err, membershipmodel.ErrPermissionDenied):
		return triperrors.AppErrorFromTripPermissionDenied(err.Error())
	case errors.Is(err, model.ErrRevisionConflict), errors.Is(err, ports.ErrCommitConflict):
		return linkerrors.AppErrorFromTripContentLinkRevisionConflict(err.Error())
	case errors.Is(err, ports.ErrIdempotencyConflict):
		return linkerrors.AppErrorFromTripContentLinkIdempotencyConflict(err.Error())
	case errors.Is(err, ports.ErrPostUnavailable):
		return linkerrors.AppErrorFromTripContentLinkPostUnavailable(err.Error())
	default:
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return err
		}
		return linkerrors.AppErrorFromTripContentLinkStorageFailed(err.Error())
	}
}

func mustPattern(operationID string) string {
	for _, descriptor := range operationsecurity.ForDomain("travel") {
		if descriptor.CanonicalOperationID == operationID {
			return descriptor.Method + " " + descriptor.PathTemplate
		}
	}
	panic("missing generated TripPlanContentLink operation descriptor: " + operationID)
}

func writeError(writer stdhttp.ResponseWriter, request *stdhttp.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
