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
	placementerrors "quwoquan_service/services/travel-service/generated/travel/trip_plan_placement"
	membershipmodel "quwoquan_service/services/travel-service/internal/travel/trip_membership/domain/model"
	tripports "quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/ports"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/domain/ports"
)

const (
	putOperation         = "travel.trip_plan_placement.PutTripPlanPlacement"
	removeOperation      = "travel.trip_plan_placement.RemoveTripPlanPlacement"
	listTripOperation    = "travel.trip_plan_placement.ListTripPlanPlacements"
	listSurfaceOperation = "travel.trip_plan_placement.ListSurfaceTripPlacements"
)

type Handler struct {
	service *application.Service
}

func NewHandler(service *application.Service) *Handler {
	if service == nil {
		panic("TripPlanPlacement HTTP handler requires service")
	}
	return &Handler{service: service}
}

func (handler *Handler) RegisterRoutes(mux *stdhttp.ServeMux) {
	if mux == nil {
		panic("TripPlanPlacement HTTP handler requires ServeMux")
	}
	mux.HandleFunc(mustPattern(putOperation), handler.handlePut)
	mux.HandleFunc(mustPattern(removeOperation), handler.handleRemove)
	mux.HandleFunc(mustPattern(listTripOperation), handler.handleListTrip)
	mux.HandleFunc(mustPattern(listSurfaceOperation), handler.handleListSurface)
}

type placementBody struct {
	SourceVersion   *int64 `json:"sourceVersion"`
	ExpectedVersion *int64 `json:"expectedVersion"`
}

func (handler *Handler) handlePut(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, key, err := commandAttribution(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	var body placementBody
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil ||
		body.SourceVersion == nil || body.ExpectedVersion == nil {
		writeError(writer, request, invalidArgument(err, "sourceVersion and expectedVersion are required"))
		return
	}
	result, err := handler.service.Put(request.Context(), application.PutCommand{
		ActorPersonaID: actor, IdempotencyKey: key,
		TripID:        strings.TrimSpace(request.PathValue("tripId")),
		SurfaceKind:   model.SurfaceKind(strings.TrimSpace(request.PathValue("surfaceKind"))),
		SurfaceID:     strings.TrimSpace(request.PathValue("surfaceId")),
		SourceVersion: *body.SourceVersion, ExpectedVersion: *body.ExpectedVersion,
	})
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	status := stdhttp.StatusOK
	if result.Placement.Version == 1 && !result.IdempotentReplay {
		status = stdhttp.StatusCreated
	}
	httpcodec.WriteJSON(writer, status, placementSlice(result.Placement), "travel_trip_plan_placement")
}

func (handler *Handler) handleRemove(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, key, err := commandAttribution(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	var body placementBody
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil ||
		body.SourceVersion == nil || body.ExpectedVersion == nil {
		writeError(writer, request, invalidArgument(err, "sourceVersion and expectedVersion are required"))
		return
	}
	result, err := handler.service.Remove(request.Context(), application.RemoveCommand{
		ActorPersonaID: actor, IdempotencyKey: key,
		TripID:        strings.TrimSpace(request.PathValue("tripId")),
		SurfaceKind:   model.SurfaceKind(strings.TrimSpace(request.PathValue("surfaceKind"))),
		SurfaceID:     strings.TrimSpace(request.PathValue("surfaceId")),
		SourceVersion: *body.SourceVersion, ExpectedVersion: *body.ExpectedVersion,
	})
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, placementSlice(result.Placement), "travel_trip_plan_placement")
}

func (handler *Handler) handleListTrip(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, err := queryActor(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	tripID := strings.TrimSpace(request.PathValue("tripId"))
	placements, err := handler.service.ListByTrip(request.Context(), actor, tripID)
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	writeList(writer, map[string]any{"tripId": tripID}, placements)
}

func (handler *Handler) handleListSurface(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, err := queryActor(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	kind := model.SurfaceKind(strings.TrimSpace(request.PathValue("surfaceKind")))
	surfaceID := strings.TrimSpace(request.PathValue("surfaceId"))
	placements, err := handler.service.ListBySurface(request.Context(), actor, kind, surfaceID)
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	writeList(writer, map[string]any{"surfaceKind": kind, "surfaceId": surfaceID}, placements)
}

func writeList(writer stdhttp.ResponseWriter, envelope map[string]any, placements []model.Placement) {
	items := make([]map[string]any, 0, len(placements))
	for _, placement := range placements {
		items = append(items, placementSlice(placement))
	}
	envelope["placements"] = items
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, envelope, "travel_trip_plan_placement")
}

func placementSlice(placement model.Placement) map[string]any {
	return map[string]any{
		"placementId":        placement.PlacementID,
		"version":            placement.Version,
		"tripId":             placement.TripID,
		"surfaceKind":        placement.SurfaceKind,
		"surfaceId":          placement.SurfaceID,
		"sourceVersion":      placement.SourceVersion,
		"status":             placement.Status,
		"createdByPersonaId": placement.CreatedByPersonaID,
		"createdAt":          placement.CreatedAt,
		"updatedAt":          placement.UpdatedAt,
	}
}

func commandAttribution(request *stdhttp.Request) (string, string, error) {
	current, ok := operation.FromContext(request.Context())
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return "", "", triperrors.AppErrorFromTripPermissionDenied(
			"TripPlanPlacement command requires a verified persona operation context",
		)
	}
	key := strings.TrimSpace(current.IdempotencyKey)
	if key == "" {
		return "", "", placementerrors.AppErrorFromTripPlacementInvalidArgument("idempotency key is required")
	}
	return strings.TrimSpace(current.Actor.PersonaID), key, nil
}

func queryActor(request *stdhttp.Request) (string, error) {
	current, ok := operation.FromContext(request.Context())
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return "", triperrors.AppErrorFromTripPermissionDenied(
			"TripPlanPlacement query requires a verified persona operation context",
		)
	}
	return strings.TrimSpace(current.Actor.PersonaID), nil
}

func invalidArgument(decodeErr error, fallback string) error {
	if decodeErr != nil {
		return placementerrors.AppErrorFromTripPlacementInvalidArgument(decodeErr.Error())
	}
	return placementerrors.AppErrorFromTripPlacementInvalidArgument(fallback)
}

func mapApplicationError(err error) error {
	switch {
	case errors.Is(err, model.ErrInvalidArgument):
		return placementerrors.AppErrorFromTripPlacementInvalidArgument(err.Error())
	case errors.Is(err, ports.ErrNotFound):
		return placementerrors.AppErrorFromTripPlacementNotFound(err.Error())
	case errors.Is(err, tripports.ErrNotFound):
		return triperrors.AppErrorFromTripNotFound(err.Error())
	case errors.Is(err, model.ErrPermissionDenied), errors.Is(err, membershipmodel.ErrPermissionDenied):
		return triperrors.AppErrorFromTripPermissionDenied(err.Error())
	case errors.Is(err, model.ErrRevisionConflict), errors.Is(err, ports.ErrCommitConflict):
		return placementerrors.AppErrorFromTripPlacementRevisionConflict(err.Error())
	case errors.Is(err, ports.ErrIdempotencyConflict):
		return placementerrors.AppErrorFromTripPlacementIdempotencyConflict(err.Error())
	case errors.Is(err, ports.ErrSurfaceUnavailable):
		return placementerrors.AppErrorFromTripPlacementSurfaceUnavailable(err.Error())
	default:
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return err
		}
		return placementerrors.AppErrorFromTripPlacementStorageFailed(err.Error())
	}
}

func mustPattern(operationID string) string {
	for _, descriptor := range operationsecurity.ForDomain("travel") {
		if descriptor.CanonicalOperationID == operationID {
			return descriptor.Method + " " + descriptor.PathTemplate
		}
	}
	panic("missing generated TripPlanPlacement operation descriptor: " + operationID)
}

func writeError(writer stdhttp.ResponseWriter, request *stdhttp.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
