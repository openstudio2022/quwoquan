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
	shareerrors "quwoquan_service/services/travel-service/generated/travel/trip_share_snapshot"
	membershipmodel "quwoquan_service/services/travel-service/internal/travel/trip_membership/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/domain/ports"
)

const (
	createOperation = "travel.trip_share_snapshot.CreateTripShareSnapshot"
	getOperation    = "travel.trip_share_snapshot.GetTripShareSnapshot"
)

type Handler struct{ service *application.Service }

func NewHandler(service *application.Service) *Handler {
	if service == nil {
		panic("TripShareSnapshot HTTP handler requires service")
	}
	return &Handler{service: service}
}

func (handler *Handler) RegisterRoutes(mux *stdhttp.ServeMux) {
	if mux == nil {
		panic("TripShareSnapshot HTTP handler requires ServeMux")
	}
	mux.HandleFunc(mustPattern(createOperation), handler.handleCreate)
	mux.HandleFunc(mustPattern(getOperation), handler.handleGet)
}

type createBody struct {
	SourceRevisionID string   `json:"sourceRevisionId"`
	SourceDigest     string   `json:"sourceDigest"`
	Scope            string   `json:"scope"`
	DayIndex         *int     `json:"dayIndex"`
	ItemID           string   `json:"itemId"`
	MomentIDs        []string `json:"momentIds"`
	Visibility       string   `json:"visibility"`
}

func (handler *Handler) handleCreate(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, key, err := commandAttribution(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	var body createBody
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil || body.MomentIDs == nil {
		writeError(writer, request, shareerrors.AppErrorFromTripShareSnapshotInvalidArgument(errorText(err, "momentIds is required")))
		return
	}
	result, err := handler.service.Create(request.Context(), application.CreateCommand{
		ActorPersonaID: actor, IdempotencyKey: key,
		TripID:           strings.TrimSpace(request.PathValue("tripId")),
		SourceRevisionID: body.SourceRevisionID, SourceDigest: body.SourceDigest,
		Scope: model.Scope(body.Scope), DayIndex: body.DayIndex, ItemID: body.ItemID,
		MomentIDs: body.MomentIDs, Visibility: model.Visibility(body.Visibility),
	})
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusCreated, result.Snapshot, "travel_trip_share_snapshot")
}

func (handler *Handler) handleGet(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor := ""
	if current, ok := operation.FromContext(request.Context()); ok {
		actor = strings.TrimSpace(current.Actor.PersonaID)
	}
	snapshot, err := handler.service.Get(
		request.Context(), actor, strings.TrimSpace(request.PathValue("snapshotId")),
	)
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, snapshot, "travel_trip_share_snapshot")
}

func commandAttribution(request *stdhttp.Request) (string, string, error) {
	current, ok := operation.FromContext(request.Context())
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return "", "", triperrors.AppErrorFromTripPermissionDenied(
			"TripShareSnapshot command requires a verified persona operation context",
		)
	}
	key := strings.TrimSpace(current.IdempotencyKey)
	if key == "" {
		return "", "", shareerrors.AppErrorFromTripShareSnapshotInvalidArgument("idempotency key is required")
	}
	return strings.TrimSpace(current.Actor.PersonaID), key, nil
}

func mapApplicationError(err error) error {
	switch {
	case errors.Is(err, model.ErrInvalidArgument):
		return shareerrors.AppErrorFromTripShareSnapshotInvalidArgument(err.Error())
	case errors.Is(err, model.ErrSourceConflict):
		return shareerrors.AppErrorFromTripShareSnapshotSourceConflict(err.Error())
	case errors.Is(err, ports.ErrNotFound):
		return shareerrors.AppErrorFromTripShareSnapshotNotFound(err.Error())
	case errors.Is(err, ports.ErrIdempotencyConflict):
		return shareerrors.AppErrorFromTripShareSnapshotIdempotencyConflict(err.Error())
	case errors.Is(err, membershipmodel.ErrPermissionDenied):
		return triperrors.AppErrorFromTripPermissionDenied(err.Error())
	default:
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return err
		}
		return shareerrors.AppErrorFromTripShareSnapshotStorageFailed(err.Error())
	}
}

func mustPattern(operationID string) string {
	for _, descriptor := range operationsecurity.ForDomain("travel") {
		if descriptor.CanonicalOperationID == operationID {
			return descriptor.Method + " " + descriptor.PathTemplate
		}
	}
	panic("missing generated TripShareSnapshot operation descriptor: " + operationID)
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
