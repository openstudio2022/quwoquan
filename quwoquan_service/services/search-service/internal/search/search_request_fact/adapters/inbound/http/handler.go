// Package http exposes SearchRequestFact-owned query projections.
package http

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/generated/operationsecurity"
	rterrors "quwoquan_service/runtime/errors"
	"quwoquan_service/services/search-service/internal/search/search_request_fact/application"
)

const listHotQueriesOperation = "search.search_request_fact.ListHotQueries"

type Handler struct {
	hotQueries application.TermHeatReader
}

func NewHandler(hotQueries application.TermHeatReader) *Handler {
	return &Handler{hotQueries: hotQueries}
}

func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	h.Register(mux)
	return mux
}

func (h *Handler) Register(mux *http.ServeMux) {
	mux.HandleFunc(mustOperationPattern(listHotQueriesOperation), h.handleHotQueries)
}

type hotQueryWire struct {
	Query     string  `json:"query"`
	Relevance float64 `json:"relevance"`
}

func (h *Handler) handleHotQueries(w http.ResponseWriter, r *http.Request) {
	requestID := requestIDFrom(r)
	if h.hotQueries == nil {
		writeErr(w, requestID, rterrors.NewUnavailable(
			rterrors.ModuleSearch,
			"热词暂时不可用，请稍后再试。",
			"term-heat reader is not configured",
		))
		return
	}
	limit := 10
	if raw := strings.TrimSpace(r.URL.Query().Get("limit")); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed <= 0 || parsed > 20 {
			writeErr(w, requestID, rterrors.NewInvalidArgument(
				rterrors.ModuleSearch,
				"热词数量参数不正确。",
				"hot query limit must be between 1 and 20",
			))
			return
		}
		limit = parsed
	}
	heats, err := h.hotQueries.RelatedTerms(r.Context(), "", limit)
	if err != nil {
		writeErr(w, requestID, rterrors.NewUnavailable(
			rterrors.ModuleSearch,
			"热词暂时不可用，请稍后再试。",
			"list hot queries: "+err.Error(),
		))
		return
	}
	items := make([]hotQueryWire, 0, len(heats))
	for _, heat := range heats {
		query := strings.TrimSpace(heat.NormalizedTerm)
		if query == "" {
			continue
		}
		items = append(items, hotQueryWire{Query: query, Relevance: heat.Relevance})
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func mustOperationPattern(canonicalOperationID string) string {
	for _, descriptor := range operationsecurity.ForDomain("search") {
		if descriptor.CanonicalOperationID == canonicalOperationID {
			return strings.TrimSpace(descriptor.Method) + " " +
				strings.TrimSpace(descriptor.PathTemplate)
		}
	}
	panic(fmt.Sprintf("generated search operation route missing: %s", canonicalOperationID))
}

func requestIDFrom(r *http.Request) string {
	if id := strings.TrimSpace(r.Header.Get("X-Request-Id")); id != "" {
		return id
	}
	return fmt.Sprintf("search.hot.%d", time.Now().UnixNano())
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeErr(w http.ResponseWriter, requestID string, err error) {
	rterrors.WriteHTTPError(w, err, rterrors.HTTPWriteOptions{RequestID: requestID})
}
