package http

import (
	"context"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	httpcodec "quwoquan_service/runtime/httpcodec"
	followingapp "quwoquan_service/services/user-service/internal/profile_projection/following_subject/application"
)

type ActorPersonaResolver interface {
	ResolveActorPersonaID(context.Context, *http.Request, string) (string, error)
}

type Handler struct {
	service  *followingapp.QueryService
	resolver ActorPersonaResolver
}

func NewHandler(service *followingapp.QueryService, resolver ActorPersonaResolver) *Handler {
	if service == nil || resolver == nil {
		panic("FollowingSubject HTTP handler requires query service and actor resolver")
	}
	return &Handler{service: service, resolver: resolver}
}

func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /user/following-subjects", h.list)
}

func (h *Handler) list(w http.ResponseWriter, r *http.Request) {
	personaID, err := h.resolver.ResolveActorPersonaID(r.Context(), r, "")
	if err != nil {
		writeError(w, r, err)
		return
	}
	items, err := h.service.ListFollowingSubjects(
		r.Context(), personaID, strings.TrimSpace(r.URL.Query().Get("subjectType")), limit(r),
	)
	if err != nil {
		writeError(w, r, err)
		return
	}
	if items == nil {
		items = []followingapp.FollowingSubjectItem{}
	}
	httpcodec.WriteJSON(w, http.StatusOK, map[string]any{"items": items}, "following_subject")
}

func limit(r *http.Request) int {
	value, err := strconv.Atoi(strings.TrimSpace(r.URL.Query().Get("limit")))
	if err != nil || value <= 0 || value > 100 {
		return 20
	}
	return value
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}
