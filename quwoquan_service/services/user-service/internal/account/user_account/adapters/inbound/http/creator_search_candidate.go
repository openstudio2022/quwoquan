package http

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"quwoquan_service/generated/operationsecurity"
	rterr "quwoquan_service/runtime/errors"
	rt "quwoquan_service/runtime/search"
	generated "quwoquan_service/services/user-service/generated/account/user_account"
	app "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	"time"
)

type CreatorSearchCandidateHandler struct {
	facade *app.CreatorSearchCandidateQueryFacade
}

func NewCreatorSearchCandidateHandler(f *app.CreatorSearchCandidateQueryFacade) *CreatorSearchCandidateHandler {
	return &CreatorSearchCandidateHandler{f}
}
func (h *CreatorSearchCandidateHandler) Register(mux *http.ServeMux) {
	for _, d := range operationsecurity.ForDomain("user") {
		if d.CanonicalOperationID == "user.user_account.ReadCreatorSearchCandidate" {
			mux.HandleFunc(d.Method+" "+d.PathTemplate, h.read)
			return
		}
	}
	panic("Creator search candidate operation absent")
}
func (h *CreatorSearchCandidateHandler) read(w http.ResponseWriter, r *http.Request) {
	trustedContext, ok := trustedServiceOperationContext(w, r,
		"user.user_account.ReadCreatorSearchCandidate",
		"user.creator_search.candidate.read", "service:content-service")
	if !ok {
		return
	}
	var query struct {
		Release rt.ReleaseCandidateBinding `json:"release"`
	}
	if err := rt.DecodeCreatorValue(r.Body, &query); err != nil || query.Release.Validate() != nil {
		rterr.WriteHTTPError(w, generated.AppErrorFromCreatorSearchInvalidCandidate("invalid candidate query"), rterr.HTTPWriteOptionsFromRequest(r))
		return
	}
	ctx, cancel := context.WithTimeout(trustedContext, 1500*time.Millisecond)
	defer cancel()
	result, err := h.facade.Read(ctx, query.Release)
	if err != nil {
		failure := generated.AppErrorFromCreatorSearchUnavailable("candidate query failed")
		if errors.Is(err, app.ErrCreatorCandidateInvalid) || errors.Is(err, rt.ErrCreatorSourceInvalid) {
			failure = generated.AppErrorFromCreatorSearchInvalidCandidate("candidate identity collision or drift")
		}
		rterr.WriteHTTPError(w, failure, rterr.HTTPWriteOptionsFromRequest(r))
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	_ = json.NewEncoder(w).Encode(result)
}
