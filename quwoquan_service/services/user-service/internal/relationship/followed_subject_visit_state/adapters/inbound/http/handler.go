package http

import (
	"context"
	"net/http"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	httpcodec "quwoquan_service/runtime/httpcodec"
	"quwoquan_service/runtime/operation"
	visitapp "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/application"
)

type ActorPersonaResolver interface {
	ResolveActorPersonaID(context.Context, *http.Request, string) (string, error)
}

type Handler struct {
	service  *visitapp.VisitService
	resolver ActorPersonaResolver
}

func NewHandler(service *visitapp.VisitService, resolver ActorPersonaResolver) *Handler {
	if service == nil || resolver == nil {
		panic("FollowedSubjectVisitState HTTP handler requires service and actor resolver")
	}
	return &Handler{service: service, resolver: resolver}
}

func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /user/followed-subjects/{subjectType}/{subjectAction}", h.markVisited)
}

type requestBody struct {
	VisitedAt       string `json:"visitedAt,omitempty"`
	ClientRequestID string `json:"clientRequestId,omitempty"`
}

func (h *Handler) markVisited(w http.ResponseWriter, r *http.Request) {
	subjectID, ok := strings.CutSuffix(r.PathValue("subjectAction"), ":mark-visited")
	if !ok || strings.TrimSpace(subjectID) == "" {
		writeError(w, r, invalid("path must be {subjectId}:mark-visited"))
		return
	}
	personaID, err := h.resolver.ResolveActorPersonaID(r.Context(), r, "")
	if err != nil {
		writeError(w, r, err)
		return
	}
	var body requestBody
	if r.Body != nil && r.ContentLength != 0 {
		if err := httpcodec.DecodeStrictJSON(r, &body); err != nil {
			writeError(w, r, invalid(err.Error()))
			return
		}
	}
	visitedAt := time.Now().UTC()
	if raw := strings.TrimSpace(body.VisitedAt); raw != "" {
		visitedAt, err = time.Parse(time.RFC3339, raw)
		if err != nil {
			writeError(w, r, invalid("visitedAt must use RFC3339"))
			return
		}
	}
	clientRequestID := strings.TrimSpace(body.ClientRequestID)
	if clientRequestID == "" {
		clientRequestID = idempotencyKey(r)
	}
	result, err := h.service.MarkVisited(r.Context(), visitapp.MarkVisitedInput{
		PersonaID: personaID, SubjectType: r.PathValue("subjectType"),
		SubjectID: subjectID, VisitedAt: visitedAt, ClientRequestID: clientRequestID,
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	httpcodec.WriteJSON(w, http.StatusOK, map[string]any{
		"subjectId": result.SubjectID, "subjectType": result.SubjectType,
		"lastVisitedAt":    result.LastVisitedAt.UTC().Format(time.RFC3339),
		"hasUnreadChanges": result.HasUnreadChanges,
	}, "followed_subject_visit_state")
}

func idempotencyKey(r *http.Request) string {
	if invocation, ok := operation.FromContext(r.Context()); ok {
		if key := strings.TrimSpace(invocation.IdempotencyKey); key != "" {
			return key
		}
	}
	return strings.TrimSpace(r.Header.Get("Idempotency-Key"))
}

func invalid(debug string) error {
	return rterr.NewInvalidArgument(rterr.ModuleUser, "参数无效", debug)
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}
