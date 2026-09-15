package http

import (
	"encoding/json"
	"errors"
	"net/http"
	"quwoquan_service/generated/operationsecurity"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	rt "quwoquan_service/runtime/search"
	generated "quwoquan_service/services/content-service/generated/content/post"
	app "quwoquan_service/services/content-service/internal/content/post/application/public"
)

type ReleaseQueriesHandler struct {
	prepare *app.ReleaseQueryPrepareFacade
	sources app.ReleaseSourceQueries
}

func NewReleaseQueriesHandler(prepare *app.ReleaseQueryPrepareFacade, sources app.ReleaseSourceQueries) *ReleaseQueriesHandler {
	return &ReleaseQueriesHandler{prepare, sources}
}
func (h *ReleaseQueriesHandler) Register(mux *http.ServeMux) {
	for _, d := range operationsecurity.ForDomain("content") {
		switch d.CanonicalOperationID {
		case "content.post.PreparePostReleaseQueries":
			mux.HandleFunc(d.Method+" "+d.PathTemplate, h.handle)
		case "content.post.ReadPostReleaseCandidate":
			mux.HandleFunc(d.Method+" "+d.PathTemplate, h.source)
		}
	}
}
func (h *ReleaseQueriesHandler) handle(w http.ResponseWriter, r *http.Request) {
	var c app.PreparePostReleaseQueriesCommand
	if rt.DecodeCreatorValue(r.Body, &c) != nil {
		releaseQueryFailure(w, r, app.ErrReleaseQueryInvalid)
		return
	}
	invocation, ok := operation.FromContext(r.Context())
	if !ok || invocation.IdempotencyKey == "" || c.IdempotencyKey != invocation.IdempotencyKey {
		releaseQueryFailure(w, r, app.ErrReleaseQueryInvalid)
		return
	}
	result, err := h.prepare.Prepare(r.Context(), c)
	if err != nil {
		releaseQueryFailure(w, r, err)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(result)
}
func (h *ReleaseQueriesHandler) source(w http.ResponseWriter, r *http.Request) {
	var q struct {
		Release rt.ReleaseCandidateBinding `json:"release"`
	}
	if rt.DecodeCreatorValue(r.Body, &q) != nil {
		releaseQueryFailure(w, r, app.ErrReleaseQueryInvalid)
		return
	}
	result, err := h.sources.ReadPostCandidate(r.Context(), q.Release)
	if err != nil {
		releaseQueryFailure(w, r, err)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	_ = json.NewEncoder(w).Encode(result)
}
func releaseQueryFailure(w http.ResponseWriter, r *http.Request, err error) {
	failure := generated.AppErrorFromContentReleaseQueryBarrierUnavailable("release query dependency unavailable")
	if errors.Is(err, app.ErrReleaseQueryInvalid) || errors.Is(err, rt.ErrCreatorSourceInvalid) {
		failure = generated.AppErrorFromContentReleaseQueryBarrierInvalid("release source drift")
	}
	if errors.Is(err, app.ErrReleaseQueryNotReady) {
		failure = generated.AppErrorFromContentReleaseQueryBarrierNotReady("required query not ready")
	}
	rterr.WriteHTTPError(w, failure, rterr.HTTPWriteOptionsFromRequest(r))
}
