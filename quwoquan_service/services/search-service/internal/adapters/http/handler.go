// Package http adapts the search-service use cases to the canonical HTTP
// contract: POST /v1/search and POST /v1/search/feedback.
package http

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	rterrors "quwoquan_service/runtime/errors"
	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/services/search-service/internal/application"
	"quwoquan_service/services/search-service/internal/infrastructure/searchmetrics"
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
	svc       *application.SearchService
	decorator *application.RankingDecorator
}

// NewHandler constructs the HTTP adapter. decorator must be non-nil; pass a
// decorator with a nil TermHeatProvider for wirings without the heat read model
// (relatedTerms empty, base ranking, AB bucket still assigned).
func NewHandler(svc *application.SearchService, decorator *application.RankingDecorator) *Handler {
	return &Handler{svc: svc, decorator: decorator}
}

// Routes registers the canonical search routes (method-scoped patterns).
func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("POST /v1/search", h.handleSearch)
	mux.HandleFunc("POST /v1/search/feedback", h.handleFeedback)
	return mux
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

	// Time only the retrieve so the latency SLI reflects user-perceived search
	// latency (logging happens off this path, after the response is served).
	start := time.Now()
	resp, err := h.svc.Search(r.Context(), in, viewer)
	elapsed := time.Since(start).Seconds()
	if err != nil {
		searchmetrics.ObserveSearch(searchmetrics.SearchObservation{
			Mode: body.Mode, Bucket: application.BucketControl, Seconds: elapsed, Err: true,
		})
		writeErr(w, requestID, rterrors.NewUnavailable(moduleSearch, "搜索暂时不可用，请稍后再试。", "retrieve: "+err.Error()))
		return
	}

	ranked := h.decorator.Decorate(r.Context(), resp, normalizedQuery, subjectKeyFor(viewer, r, requestID))
	resp.Hits = ranked.Hits

	termHeatApplied := ranked.ExperimentBucket == application.BucketTermHeat && len(ranked.RelatedTerms) > 0
	searchmetrics.ObserveSearch(searchmetrics.SearchObservation{
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
		RawQuery:         body.Query,
		SessionID:        strings.TrimSpace(r.Header.Get("X-Session-Id")),
		Mode:             body.Mode,
		ViewerID:         viewer.UserID,
		ObjectTypes:      body.ObjectTypes,
		ResultCount:      len(resp.Hits),
		RankingVersion:   ranked.RankingVersion,
		ExperimentBucket: ranked.ExperimentBucket,
		RelatedTerms:     ranked.RelatedTerms,
		TopObjectIDs:     ranked.TopObjectIDs,
	})
}

func (h *Handler) logQueryAsync(r *http.Request, qlog application.QueryLog) {
	logCtx, cancel := context.WithTimeout(context.WithoutCancel(r.Context()), queryLogTimeout)
	go func() {
		defer cancel()
		h.svc.LogQuery(logCtx, qlog)
	}()
}

func (h *Handler) handleFeedback(w http.ResponseWriter, r *http.Request) {
	requestID := requestIDFrom(r)
	r.Body = http.MaxBytesReader(w, r.Body, maxRequestBodyBytes)
	var ev application.FeedbackEvent
	if err := json.NewDecoder(r.Body).Decode(&ev); err != nil {
		writeErr(w, requestID, rterrors.NewInvalidArgument(moduleSearch, "反馈格式不正确。", "decode feedback body: "+err.Error()))
		return
	}
	if strings.TrimSpace(ev.SearchRequestID) == "" || strings.TrimSpace(ev.EventType) == "" {
		writeErr(w, requestID, rterrors.NewInvalidArgument(moduleSearch, "反馈缺少必要字段。", "missing searchRequestId/eventType"))
		return
	}
	if err := h.svc.ReportFeedback(r.Context(), ev); err != nil {
		writeErr(w, requestID, rterrors.NewUnavailable(moduleSearch, "反馈暂时无法记录。", "record feedback: "+err.Error()))
		return
	}
	searchmetrics.ObserveFeedback(ev.EventType)
	writeJSON(w, http.StatusAccepted, map[string]any{"accepted": true, "requestId": requestID})
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
	return rtsearch.Viewer{UserID: strings.TrimSpace(r.Header.Get("X-User-Id"))}
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
