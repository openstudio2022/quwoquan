package http

import (
	"errors"
	stdhttp "net/http"
	"strings"

	"quwoquan_service/generated/operationsecurity"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/httpcodec"
	"quwoquan_service/runtime/operation"
	membershiperrors "quwoquan_service/services/travel-service/generated/travel/trip_membership"
	triperrors "quwoquan_service/services/travel-service/generated/travel/trip_plan"
	"quwoquan_service/services/travel-service/internal/travel/trip_membership/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_membership/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_membership/domain/ports"
)

const (
	putOperation    = "travel.trip_membership.PutTripMembership"
	departOperation = "travel.trip_membership.DepartTripMembership"
	listOperation   = "travel.trip_membership.ListTripMemberships"
)

type Handler struct {
	service *application.Service
}

func NewHandler(service *application.Service) *Handler {
	if service == nil {
		panic("TripMembership HTTP handler requires service")
	}
	return &Handler{service: service}
}

func (handler *Handler) RegisterRoutes(mux *stdhttp.ServeMux) {
	if mux == nil {
		panic("TripMembership HTTP handler requires ServeMux")
	}
	mux.HandleFunc(mustPattern(putOperation), handler.handlePut)
	mux.HandleFunc(mustPattern(departOperation), handler.handleDepart)
	mux.HandleFunc(mustPattern(listOperation), handler.handleList)
}

type sourceRefBody struct {
	ObjectTypeRef string `json:"objectTypeRef"`
	ObjectID      string `json:"objectId"`
}

type putBody struct {
	Role            string         `json:"role"`
	SourceKind      string         `json:"sourceKind"`
	SourceObjectRef *sourceRefBody `json:"sourceObjectRef"`
	SourceVersion   *int64         `json:"sourceVersion"`
	ExpectedVersion *int64         `json:"expectedVersion"`
}

type departBody struct {
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
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil ||
		body.ExpectedVersion == nil || body.SourceVersion == nil {
		writeError(writer, request, invalidArgument(err, "expectedVersion and sourceVersion are required"))
		return
	}
	var sourceRef *model.SourceRef
	if body.SourceObjectRef != nil {
		sourceRef = &model.SourceRef{
			ObjectTypeRef: body.SourceObjectRef.ObjectTypeRef,
			ObjectID:      body.SourceObjectRef.ObjectID,
		}
	}
	result, err := handler.service.Put(request.Context(), application.PutCommand{
		ActorPersonaID:  actor,
		IdempotencyKey:  key,
		TripID:          strings.TrimSpace(request.PathValue("tripId")),
		PersonaID:       strings.TrimSpace(request.PathValue("personaId")),
		ExpectedVersion: *body.ExpectedVersion,
		Role:            model.Role(body.Role),
		SourceKind:      model.SourceKind(body.SourceKind),
		SourceObjectRef: sourceRef,
		SourceVersion:   *body.SourceVersion,
	})
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	status := stdhttp.StatusOK
	if result.Membership.Version == 1 && !result.IdempotentReplay {
		status = stdhttp.StatusCreated
	}
	httpcodec.WriteJSON(writer, status, membershipSlice(result.Membership), "travel_trip_membership")
}

func (handler *Handler) handleDepart(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, key, err := commandAttribution(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	var body departBody
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil || body.ExpectedVersion == nil {
		writeError(writer, request, invalidArgument(err, "expectedVersion is required"))
		return
	}
	result, err := handler.service.Depart(request.Context(), application.DepartCommand{
		ActorPersonaID:  actor,
		IdempotencyKey:  key,
		TripID:          strings.TrimSpace(request.PathValue("tripId")),
		PersonaID:       strings.TrimSpace(request.PathValue("personaId")),
		ExpectedVersion: *body.ExpectedVersion,
		Reason:          body.Reason,
	})
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, membershipSlice(result.Membership), "travel_trip_membership")
}

func (handler *Handler) handleList(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	actor, err := queryActor(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	tripID := strings.TrimSpace(request.PathValue("tripId"))
	memberships, err := handler.service.List(request.Context(), actor, tripID)
	if err != nil {
		writeError(writer, request, mapApplicationError(err))
		return
	}
	items := make([]map[string]any, 0, len(memberships))
	for _, membership := range memberships {
		items = append(items, membershipSlice(membership))
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, map[string]any{
		"tripId": tripID, "memberships": items,
	}, "travel_trip_membership")
}

func commandAttribution(request *stdhttp.Request) (string, string, error) {
	current, ok := operation.FromContext(request.Context())
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return "", "", triperrors.AppErrorFromTripPermissionDenied(
			"TripMembership command requires a verified persona operation context",
		)
	}
	key := strings.TrimSpace(current.IdempotencyKey)
	if key == "" {
		return "", "", membershiperrors.AppErrorFromTripMembershipInvalidArgument("idempotency key is required")
	}
	return strings.TrimSpace(current.Actor.PersonaID), key, nil
}

func queryActor(request *stdhttp.Request) (string, error) {
	current, ok := operation.FromContext(request.Context())
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return "", triperrors.AppErrorFromTripPermissionDenied(
			"TripMembership query requires a verified persona operation context",
		)
	}
	return strings.TrimSpace(current.Actor.PersonaID), nil
}

func membershipSlice(membership model.Membership) map[string]any {
	return map[string]any{
		"membershipId":    membership.MembershipID,
		"version":         membership.Version,
		"tripId":          membership.TripID,
		"personaId":       membership.PersonaID,
		"role":            membership.Role,
		"state":           membership.State,
		"sourceKind":      membership.SourceKind,
		"sourceObjectRef": membership.SourceObjectRef,
		"sourceVersion":   membership.SourceVersion,
		"joinedAt":        membership.JoinedAt,
		"updatedAt":       membership.UpdatedAt,
	}
}

func invalidArgument(decodeErr error, fallback string) error {
	if decodeErr != nil {
		return membershiperrors.AppErrorFromTripMembershipInvalidArgument(decodeErr.Error())
	}
	return membershiperrors.AppErrorFromTripMembershipInvalidArgument(fallback)
}

func mapApplicationError(err error) error {
	switch {
	case errors.Is(err, model.ErrInvalidArgument):
		return membershiperrors.AppErrorFromTripMembershipInvalidArgument(err.Error())
	case errors.Is(err, ports.ErrNotFound):
		return membershiperrors.AppErrorFromTripMembershipNotFound(err.Error())
	case errors.Is(err, model.ErrPermissionDenied):
		return triperrors.AppErrorFromTripPermissionDenied(err.Error())
	case errors.Is(err, model.ErrRevisionConflict), errors.Is(err, ports.ErrCommitConflict):
		return membershiperrors.AppErrorFromTripMembershipRevisionConflict(err.Error())
	case errors.Is(err, ports.ErrIdempotencyConflict):
		return membershiperrors.AppErrorFromTripMembershipIdempotencyConflict(err.Error())
	case errors.Is(err, ports.ErrSourceUnavailable):
		return membershiperrors.AppErrorFromTripMembershipSourceUnavailable(err.Error())
	default:
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return err
		}
		return membershiperrors.AppErrorFromTripMembershipStorageFailed(err.Error())
	}
}

func mustPattern(operationID string) string {
	for _, descriptor := range operationsecurity.ForDomain("travel") {
		if descriptor.CanonicalOperationID == operationID {
			return descriptor.Method + " " + descriptor.PathTemplate
		}
	}
	panic("missing generated TripMembership operation descriptor: " + operationID)
}

func writeError(writer stdhttp.ResponseWriter, request *stdhttp.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
