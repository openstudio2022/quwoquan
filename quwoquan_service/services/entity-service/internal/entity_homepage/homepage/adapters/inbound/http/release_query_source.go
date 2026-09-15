package httpadapter

import (
	"encoding/json"
	"net/http"
	"quwoquan_service/generated/operationsecurity"
	"quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	rt "quwoquan_service/runtime/search"
	app "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application"
	"slices"
	"strings"
)

type ReleaseCandidateHandler struct {
	facade *app.HomepageReleaseCandidateQueryFacade
}

func NewReleaseCandidateHandler(f *app.HomepageReleaseCandidateQueryFacade) *ReleaseCandidateHandler {
	return &ReleaseCandidateHandler{f}
}
func (h *ReleaseCandidateHandler) Register(mux *http.ServeMux) {
	for _, d := range operationsecurity.ForDomain("entity") {
		if d.CanonicalOperationID == "entity.homepage.ReadHomepageReleaseCandidate" {
			mux.HandleFunc(d.Method+" "+d.PathTemplate, h.read)
			return
		}
	}
	panic("Homepage source operation absent")
}
func (h *ReleaseCandidateHandler) read(w http.ResponseWriter, r *http.Request) {
	p, ok := auth.PrincipalFromContext(r.Context())
	if !ok || p.Subject != "service:content-service" || !slices.Contains(strings.Fields(p.Scope), "entity.release.source.read") {
		code, _ := rterr.ParseCode("GATEWAY.USER.forbidden")
		rterr.WriteHTTPError(w, rterr.NewAppError(code, "当前账号没有该操作权限", "source principal mismatch"), rterr.HTTPWriteOptionsFromRequest(r))
		return
	}
	var q struct {
		Release rt.ReleaseCandidateBinding `json:"release"`
	}
	if rt.DecodeCreatorValue(r.Body, &q) != nil {
		h.fail(w, r)
		return
	}
	result, err := h.facade.Read(r.Context(), q.Release)
	if err != nil {
		h.fail(w, r)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	_ = json.NewEncoder(w).Encode(result)
}
func (h *ReleaseCandidateHandler) fail(w http.ResponseWriter, r *http.Request) {
	code, _ := rterr.ParseCode("ENTITY.RELEASE.candidate_unavailable")
	rterr.WriteHTTPError(w, rterr.NewAppError(code, "候选主页暂时不可用", "Homepage source read failed").WithMetadata("candidate_unavailable", 503), rterr.HTTPWriteOptionsFromRequest(r))
}
