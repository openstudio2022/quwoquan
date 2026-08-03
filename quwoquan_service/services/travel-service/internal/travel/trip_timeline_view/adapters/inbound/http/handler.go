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
	timelineerrors "quwoquan_service/services/travel-service/generated/travel/trip_timeline_view"
	membershipmodel "quwoquan_service/services/travel-service/internal/travel/trip_membership/domain/model"
	tripports "quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/ports"
	"quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/domain/ports"
)

const getOperation = "travel.trip_timeline_view.GetTripTimeline"

type Handler struct {
	reader *application.Reader
}

func NewHandler(reader *application.Reader) *Handler {
	if reader == nil {
		panic("TripTimelineView HTTP handler requires reader")
	}
	return &Handler{reader: reader}
}

func (handler *Handler) RegisterRoutes(mux *stdhttp.ServeMux) {
	if mux == nil {
		panic("TripTimelineView HTTP handler requires ServeMux")
	}
	mux.HandleFunc(mustPattern(getOperation), handler.handleGet)
}

func (handler *Handler) handleGet(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, err := queryActor(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	view, err := handler.reader.Get(
		request.Context(), actor, strings.TrimSpace(request.PathValue("tripId")),
	)
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, view, "travel_trip_timeline_view")
}

func queryActor(request *stdhttp.Request) (string, error) {
	current, ok := operation.FromContext(request.Context())
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return "", triperrors.AppErrorFromTripPermissionDenied(
			"TripTimelineView query requires a verified persona operation context",
		)
	}
	return strings.TrimSpace(current.Actor.PersonaID), nil
}

func mapApplicationError(err error) error {
	switch {
	case errors.Is(err, ports.ErrProjectionUnavailable), errors.Is(err, ports.ErrNotFound):
		return timelineerrors.AppErrorFromTripTimelineProjectionUnavailable(err.Error())
	case errors.Is(err, tripports.ErrNotFound):
		return triperrors.AppErrorFromTripNotFound(err.Error())
	case errors.Is(err, membershipmodel.ErrPermissionDenied):
		return triperrors.AppErrorFromTripPermissionDenied(err.Error())
	default:
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return err
		}
		return timelineerrors.AppErrorFromTripTimelineProjectionFailed(err.Error())
	}
}

func mustPattern(operationID string) string {
	for _, descriptor := range operationsecurity.ForDomain("travel") {
		if descriptor.CanonicalOperationID == operationID {
			return descriptor.Method + " " + descriptor.PathTemplate
		}
	}
	panic("missing generated TripTimelineView operation descriptor: " + operationID)
}

func writeError(writer stdhttp.ResponseWriter, request *stdhttp.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
