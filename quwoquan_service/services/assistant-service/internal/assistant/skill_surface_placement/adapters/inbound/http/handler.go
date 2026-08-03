package http

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	placementerrors "quwoquan_service/services/assistant-service/generated/assistant/skill_surface_placement"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/model"
)

const (
	getOperation = "assistant.skill_surface_placement.GetSkillSurfacePlacement"
	putOperation = "assistant.skill_surface_placement.PutSkillSurfacePlacement"
)

type Handler struct {
	commands *application.CommandFacade
	queries  *application.QueryFacade
}

func NewHandler(commands *application.CommandFacade, queries *application.QueryFacade) *Handler {
	return &Handler{commands: commands, queries: queries}
}

func (handler *Handler) RegisterRoutes(mux *http.ServeMux) {
	get := mustOperationDescriptor(getOperation)
	put := mustOperationDescriptor(putOperation)
	mux.HandleFunc(get.Method+" "+get.PathTemplate, handler.handleGet)
	mux.HandleFunc(put.Method+" "+put.PathTemplate, handler.handlePut)
}

func (handler *Handler) handleGet(writer http.ResponseWriter, request *http.Request) {
	actor, err := requireActor(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	placement, err := handler.queries.Get(
		request.Context(),
		actor.AccountID,
		actor.PersonaID,
		strings.TrimSpace(request.PathValue("surfaceKind")),
		strings.TrimSpace(request.PathValue("surfaceId")),
	)
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err))
		return
	}
	writeJSON(writer, http.StatusOK, placement)
}

func (handler *Handler) handlePut(writer http.ResponseWriter, request *http.Request) {
	actor, err := requireActor(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	var body struct {
		Policy           string   `json:"policy"`
		DisabledSkillIDs []string `json:"disabledSkillIds"`
		Status           string   `json:"status"`
		ExpectedRevision int64    `json:"expectedRevision"`
	}
	decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, 64<<10))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		writeHTTPError(
			writer,
			request,
			placementerrors.AppErrorFromSkillPlacementInvalidArgument(err.Error()),
		)
		return
	}
	result, err := handler.commands.Put(request.Context(), model.PutInput{
		SurfaceKind:      strings.TrimSpace(request.PathValue("surfaceKind")),
		SurfaceID:        strings.TrimSpace(request.PathValue("surfaceId")),
		ActorAccountID:   actor.AccountID,
		ActorPersonaID:   actor.PersonaID,
		Policy:           body.Policy,
		DisabledSkillIDs: body.DisabledSkillIDs,
		Status:           body.Status,
		ExpectedRevision: body.ExpectedRevision,
		IdempotencyKey:   strings.TrimSpace(request.Header.Get("Idempotency-Key")),
	})
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err))
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"placement": result.Placement,
		"changed":   result.Changed,
		"replayed":  result.Replayed,
	})
}

type placementActor struct {
	AccountID string
	PersonaID string
}

func requireActor(request *http.Request) (placementActor, error) {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if ok && strings.TrimSpace(principal.Actor.AccountID) != "" &&
		strings.TrimSpace(principal.Actor.PersonaID) != "" {
		return placementActor{
			AccountID: strings.TrimSpace(principal.Actor.AccountID),
			PersonaID: strings.TrimSpace(principal.Actor.PersonaID),
		}, nil
	}
	return placementActor{}, placementerrors.AppErrorFromSkillPlacementUnauthorized(
		"SkillSurfacePlacement requires a verified account and persona principal",
	)
}

func mapDomainError(err error) error {
	switch {
	case errors.Is(err, model.ErrNotFound):
		return placementerrors.AppErrorFromSkillPlacementNotFound(err.Error())
	case errors.Is(err, model.ErrForbidden):
		return placementerrors.AppErrorFromSkillPlacementForbidden(err.Error())
	case errors.Is(err, model.ErrInvalidArgument):
		return placementerrors.AppErrorFromSkillPlacementInvalidArgument(err.Error())
	case errors.Is(err, model.ErrRevisionConflict):
		return placementerrors.AppErrorFromSkillPlacementRevisionConflict(err.Error())
	case errors.Is(err, model.ErrIdempotencyConflict):
		return placementerrors.AppErrorFromSkillPlacementIdempotencyConflict(err.Error())
	case errors.Is(err, model.ErrUnknownSkill):
		return placementerrors.AppErrorFromSkillPlacementUnknownSkill(err.Error())
	case errors.Is(err, model.ErrAuthorityUnavailable):
		return placementerrors.AppErrorFromSkillPlacementAuthorityUnavailable(err.Error())
	case errors.Is(err, model.ErrPackageUnavailable):
		return placementerrors.AppErrorFromSkillPlacementPackageUnavailable(err.Error())
	case errors.Is(err, model.ErrStorageUnavailable):
		return placementerrors.AppErrorFromSkillPlacementStorageUnavailable(err.Error())
	default:
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return err
		}
		return placementerrors.AppErrorFromSkillPlacementStorageUnavailable(err.Error())
	}
}

func mustOperationDescriptor(canonicalOperationID string) rtauth.OperationSecurityDescriptor {
	for _, descriptor := range operationsecurity.ForDomain("assistant") {
		if descriptor.CanonicalOperationID == canonicalOperationID {
			return descriptor
		}
	}
	panic("missing generated operation descriptor: " + canonicalOperationID)
}

func writeJSON(writer http.ResponseWriter, status int, payload any) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(payload)
}

func writeHTTPError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
