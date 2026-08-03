package http

import (
	"context"
	"net/http"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	httpcodec "quwoquan_service/runtime/httpcodec"
	"quwoquan_service/runtime/operation"
	subjectfollowapp "quwoquan_service/services/user-service/internal/relationship/subject_follow/application"
)

type ActorPersonaResolver interface {
	ResolveActorPersonaID(context.Context, *http.Request, string) (string, error)
}

type Handler struct {
	service  *subjectfollowapp.SubjectFollowService
	resolver ActorPersonaResolver
}

func NewHandler(
	service *subjectfollowapp.SubjectFollowService,
	resolver ActorPersonaResolver,
) *Handler {
	if service == nil || resolver == nil {
		panic("SubjectFollow HTTP handler requires service and actor resolver")
	}
	return &Handler{service: service, resolver: resolver}
}

func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /relationships/subjects/{subjectType}/{subjectId}/follow", h.follow)
	mux.HandleFunc("DELETE /relationships/subjects/{subjectType}/{subjectId}/follow", h.unfollow)
}

type requestBody struct {
	Source string `json:"source,omitempty"`
}

func (h *Handler) follow(w http.ResponseWriter, r *http.Request)   { h.execute(w, r, true) }
func (h *Handler) unfollow(w http.ResponseWriter, r *http.Request) { h.execute(w, r, false) }

func (h *Handler) execute(w http.ResponseWriter, r *http.Request, follow bool) {
	personaID, err := h.resolver.ResolveActorPersonaID(r.Context(), r, "")
	if err != nil {
		writeError(w, r, err)
		return
	}
	idempotencyKey := commandIdempotencyKey(r)
	if idempotencyKey == "" {
		writeError(w, r, invalid("Idempotency-Key is required"))
		return
	}
	var body requestBody
	if r.Body != nil && r.ContentLength != 0 {
		if err := httpcodec.DecodeStrictJSON(r, &body); err != nil {
			writeError(w, r, invalid(err.Error()))
			return
		}
	}
	command := subjectfollowapp.FollowSubjectCommand{
		PersonaID: personaID, SubjectType: r.PathValue("subjectType"),
		SubjectID: r.PathValue("subjectId"), Source: body.Source,
		IdempotencyKey: idempotencyKey,
	}
	execute := h.service.Follow
	if !follow {
		execute = h.service.Unfollow
	}
	result, err := execute(r.Context(), command)
	if err != nil {
		writeError(w, r, err)
		return
	}
	httpcodec.WriteJSON(w, http.StatusOK, map[string]any{
		"personaId": result.Follow.PersonaID, "subjectType": result.Follow.SubjectType,
		"subjectId": result.Follow.SubjectID, "state": result.Follow.State,
		"idempotentReplay": result.IdempotentReplay,
		"updatedAt":        result.Follow.UpdatedAt.UTC().Format(time.RFC3339),
	}, "subject_follow")
}

func commandIdempotencyKey(r *http.Request) string {
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
