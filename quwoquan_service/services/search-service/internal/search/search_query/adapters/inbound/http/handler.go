// Package http adapts the canonical search query operations.
package http

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rterrors "quwoquan_service/runtime/errors"
	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/services/search-service/internal/search/search_query/application"
)

const moduleSearch = rterrors.Module("SEARCH")

// queryLogTimeout bounds the detached best-effort query-log write so a stuck
// Mongo never leaks goroutines or holds resources after the response is served.
const queryLogTimeout = 5 * time.Second

// maxRequestBodyBytes caps the search/feedback request body. Search payloads are
// small (query + a handful of filters); a bounded reader rejects oversized
// bodies cheaply instead of letting them consume memory under load.
const maxRequestBodyBytes = 64 << 10 // 64 KiB

// Handler serves the canonical search routes.
type Handler struct {
	svc           *application.SearchService
	decorator     *application.RankingDecorator
	observer      application.SearchRequestObserver
	hotQueries    application.TermHeatProvider
	intersections *application.IntersectionAttacher
}

type HandlerConfig struct {
	HotQueries    application.TermHeatProvider
	Intersections *application.IntersectionAttacher
}

// NewHandler 构造 HTTP 适配器；observer 可为空。
func NewHandler(
	svc *application.SearchService,
	decorator *application.RankingDecorator,
	observer application.SearchRequestObserver,
	hotQueries ...application.TermHeatProvider,
) *Handler {
	handler := &Handler{svc: svc, decorator: decorator, observer: observer}
	if len(hotQueries) > 0 {
		handler.hotQueries = hotQueries[0]
	}
	return handler
}

func NewHandlerWithConfig(
	svc *application.SearchService,
	decorator *application.RankingDecorator,
	observer application.SearchRequestObserver,
	config HandlerConfig,
) *Handler {
	return &Handler{
		svc:           svc,
		decorator:     decorator,
		observer:      observer,
		hotQueries:    config.HotQueries,
		intersections: config.Intersections,
	}
}

// Routes registers the canonical search routes (method-scoped patterns).
func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	h.Register(mux)
	return mux
}

// Register 挂载搜索路由到既有 mux（与 RecentSearchHandler.Register 组合使用）。
func (h *Handler) Register(mux *http.ServeMux) {
	mux.HandleFunc(mustOperationPattern(searchQueryOperation), h.handleSearch)
	mux.HandleFunc(mustOperationPattern(listHotQueriesOperation), h.handleHotQueries)
}

type hotQueryWire struct {
	Query     string  `json:"query"`
	Relevance float64 `json:"relevance"`
}

func (h *Handler) handleHotQueries(w http.ResponseWriter, r *http.Request) {
	requestID := requestIDFrom(r)
	if h.hotQueries == nil {
		writeErr(
			w,
			requestID,
			rterrors.NewUnavailable(
				moduleSearch,
				"热词暂时不可用，请稍后再试。",
				"term-heat reader is not configured",
			),
		)
		return
	}
	limit := 10
	if raw := strings.TrimSpace(r.URL.Query().Get("limit")); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed <= 0 || parsed > 20 {
			writeErr(
				w,
				requestID,
				rterrors.NewInvalidArgument(
					moduleSearch,
					"热词数量参数不正确。",
					"hot query limit must be between 1 and 20",
				),
			)
			return
		}
		limit = parsed
	}
	heats, err := h.hotQueries.RelatedTerms(r.Context(), "", limit)
	if err != nil {
		writeErr(
			w,
			requestID,
			rterrors.NewUnavailable(
				moduleSearch,
				"热词暂时不可用，请稍后再试。",
				"list hot queries: "+err.Error(),
			),
		)
		return
	}
	items := make([]hotQueryWire, 0, len(heats))
	for _, heat := range heats {
		query := strings.TrimSpace(heat.NormalizedTerm)
		if query == "" {
			continue
		}
		items = append(items, hotQueryWire{
			Query:     query,
			Relevance: heat.Relevance,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

type searchRequestWire struct {
	Query       string   `json:"query"`
	Mode        string   `json:"mode"`
	ObjectTypes []string `json:"objectTypes"`
	Limit       int      `json:"limit"`
	Filters     struct {
		Tags      []string `json:"tags"`
		TimeRange *struct {
			From string `json:"from"`
			To   string `json:"to"`
		} `json:"timeRange"`
		// near is the optional 附近 geo radius filter; lat/lng pin + radiusKm.
		Near *struct {
			Lat      float64 `json:"lat"`
			Lng      float64 `json:"lng"`
			RadiusKm float64 `json:"radiusKm"`
		} `json:"near"`
	} `json:"filters"`
}

// searchResponseWire embeds the unified RetrieveResponse and adds the commercial
// envelope fields (requestId/rankingVersion/experimentBucket/relatedTerms)
// declared in metadata. Per-hit rankReasons/rankPosition ride on the embedded
// RetrieveHit (single-sourced in runtime/search).
type searchResponseWire struct {
	rtsearch.RetrieveResponse
	RequestID        string   `json:"requestId"`
	RankingVersion   string   `json:"rankingVersion"`
	ExperimentBucket string   `json:"experimentBucket,omitempty"`
	RelatedTerms     []string `json:"relatedTerms,omitempty"`
}

func (h *Handler) handleSearch(w http.ResponseWriter, r *http.Request) {
	requestID := requestIDFrom(r)
	r.Body = http.MaxBytesReader(w, r.Body, maxRequestBodyBytes)
	var body searchRequestWire
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, requestID, rterrors.NewInvalidArgument(moduleSearch, "搜索请求格式不正确。", "decode search body: "+err.Error()))
		return
	}
	if strings.TrimSpace(body.Query) == "" {
		writeErr(w, requestID, rterrors.NewInvalidArgument(moduleSearch, "请输入搜索内容。", "empty query"))
		return
	}

	viewer := viewerFrom(r)
	// Canonical normalization (single source: runtime/search.Analyze) so the
	// query log, heat mining and ranking all key off the same normalized term.
	normalizedQuery := rtsearch.Analyze(body.Query, nil).Normalized
	in := application.QueryInput{
		Query:       body.Query,
		Mode:        body.Mode,
		ObjectTypes: body.ObjectTypes,
		Limit:       body.Limit,
		Tags:        body.Filters.Tags,
		TimeRange:   parseTimeRange(body),
		Near:        parseNear(body),
	}

	// 计时覆盖召回、排序与交集 attach；异步 query log 仍在响应后执行。
	start := time.Now()
	resp, err := h.svc.Search(r.Context(), in, viewer)
	if err != nil {
		h.observeSearch(application.SearchObservation{
			Mode: body.Mode, Bucket: application.BucketControl,
			Seconds: time.Since(start).Seconds(), Err: true,
		})
		if errors.Is(err, application.ErrSearchInvalid) {
			writeErr(w, requestID, rterrors.NewInvalidArgument(moduleSearch, "搜索对象类型不受支持。", err.Error()))
		} else {
			writeErr(w, requestID, rterrors.NewUnavailable(moduleSearch, "搜索暂时不可用，请稍后再试。", "retrieve: "+err.Error()))
		}
		return
	}

	ranked := h.decorator.Decorate(r.Context(), resp, normalizedQuery, subjectKeyFor(viewer, r, requestID))
	resp.Hits = ranked.Hits
	if h.intersections != nil {
		resp = h.intersections.Attach(r.Context(), viewerPersonaIDFrom(r), resp)
	}
	elapsed := time.Since(start).Seconds()

	termHeatApplied := ranked.ExperimentBucket == application.BucketTermHeat && len(ranked.RelatedTerms) > 0
	h.observeSearch(application.SearchObservation{
		Mode:            body.Mode,
		Bucket:          ranked.ExperimentBucket,
		Seconds:         elapsed,
		ResultCount:     len(resp.Hits),
		Degraded:        len(resp.DegradeSignals) > 0,
		TermHeatApplied: termHeatApplied,
	})

	writeJSON(w, http.StatusOK, searchResponseWire{
		RetrieveResponse: resp,
		RequestID:        requestID,
		RankingVersion:   ranked.RankingVersion,
		ExperimentBucket: ranked.ExperimentBucket,
		RelatedTerms:     ranked.RelatedTerms,
	})

	// Best-effort query log on a detached context so a slow/failed Mongo write
	// never blocks or fails the search that was already served.
	h.logQueryAsync(r, application.QueryLog{
		SearchRequestID:  requestID,
		Query:            normalizedQuery,
		SessionID:        strings.TrimSpace(r.Header.Get("X-Session-Id")),
		Mode:             body.Mode,
		ViewerID:         viewer.UserID,
		ObjectTypes:      body.ObjectTypes,
		ResultCount:      len(resp.Hits),
		RankingVersion:   ranked.RankingVersion,
		ExperimentBucket: ranked.ExperimentBucket,
		RelatedTerms:     ranked.RelatedTerms,
	})
}

func (h *Handler) logQueryAsync(r *http.Request, qlog application.QueryLog) {
	logCtx, cancel := context.WithTimeout(context.WithoutCancel(r.Context()), queryLogTimeout)
	go func() {
		defer cancel()
		h.svc.LogQuery(logCtx, qlog)
	}()
}

func (h *Handler) observeSearch(observation application.SearchObservation) {
	if h.observer != nil {
		h.observer.ObserveSearch(observation)
	}
}

// subjectKeyFor returns the STABLE AB bucketing key: the logged-in viewer id
// (sticky per user), else a client session id (sticky per session). When neither
// exists it returns "" — NOT the per-request id. Bucketing on a per-request id
// would re-roll the experiment arm on every keystroke, so the same query would
// jump between control and term_heat (different result order each time). With ""
// the assignment is forced to control (see Experiments.Assign), so identity-less
// anonymous traffic gets stable, repeatable results; App/Gateway must inject a
// stable X-Session-Id for anonymous users to participate in the experiment.
func subjectKeyFor(viewer rtsearch.Viewer, r *http.Request, _ string) string {
	if id := strings.TrimSpace(viewer.UserID); id != "" {
		return id
	}
	if sid := strings.TrimSpace(r.Header.Get("X-Session-Id")); sid != "" {
		return sid
	}
	return ""
}

func parseTimeRange(body searchRequestWire) *rtsearch.TimeRange {
	if body.Filters.TimeRange == nil {
		return nil
	}
	tr := &rtsearch.TimeRange{}
	if v := strings.TrimSpace(body.Filters.TimeRange.From); v != "" {
		if ts, err := time.Parse(time.RFC3339, v); err == nil {
			tr.From = ts
		}
	}
	if v := strings.TrimSpace(body.Filters.TimeRange.To); v != "" {
		if ts, err := time.Parse(time.RFC3339, v); err == nil {
			tr.To = ts
		}
	}
	if tr.From.IsZero() && tr.To.IsZero() {
		return nil
	}
	return tr
}

// parseNear maps the wire near filter into the runtime GeoNear. A missing block
// or non-positive radius yields nil so it is treated as "no nearby constraint".
func parseNear(body searchRequestWire) *rtsearch.GeoNear {
	n := body.Filters.Near
	if n == nil || n.RadiusKm <= 0 {
		return nil
	}
	return &rtsearch.GeoNear{Lat: n.Lat, Lng: n.Lng, RadiusKm: n.RadiusKm}
}

func viewerFrom(r *http.Request) rtsearch.Viewer {
	// Visibility is implicit; the cloud path only returns public objects.
	// chat.* private content stays local_only on the App.
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return rtsearch.Viewer{}
	}
	viewerID := strings.TrimSpace(principal.Actor.PersonaID)
	if viewerID == "" {
		viewerID = strings.TrimSpace(principal.Actor.AccountID)
	}
	return rtsearch.Viewer{UserID: viewerID}
}

func viewerPersonaIDFrom(r *http.Request) string {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return ""
	}
	return strings.TrimSpace(principal.Actor.PersonaID)
}

func requestIDFrom(r *http.Request) string {
	if id := strings.TrimSpace(r.Header.Get("X-Request-Id")); id != "" {
		return id
	}
	return fmt.Sprintf("search.req.%d", time.Now().UnixNano())
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeErr(w http.ResponseWriter, requestID string, err error) {
	rterrors.WriteHTTPError(w, err, rterrors.HTTPWriteOptions{RequestID: requestID})
}
