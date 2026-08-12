// Package http adapts the canonical search query operations.
package http

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rterrors "quwoquan_service/runtime/errors"
	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
	requestapplication "quwoquan_service/services/search-service/internal/search/search_request_fact/application"
)

const moduleSearch = rterrors.Module("SEARCH")

// queryLogTimeout bounds the detached best-effort query-log write so a stuck
// Mongo never leaks goroutines or holds resources after the response is served.
const queryLogTimeout = 5 * time.Second

const SearchSessionIDHeader = "X-Session-Id"

const contractGraphSHA256Header = "X-Contract-Graph-SHA256"

// maxRequestBodyBytes caps the search/feedback request body. Search payloads are
// small (query + a handful of filters); a bounded reader rejects oversized
// bodies cheaply instead of letting them consume memory under load.
const maxRequestBodyBytes = 64 << 10 // 64 KiB

// Handler serves the canonical search routes.
type Handler struct {
	svc             *application.SearchService
	decorator       *application.RankingDecorator
	observer        application.SearchRequestObserver
	intersections   *application.IntersectionAttacher
	requestFacts    *requestapplication.Recorder
	candidateDigest string
}

type HandlerConfig struct {
	Intersections   *application.IntersectionAttacher
	RequestFacts    *requestapplication.Recorder
	CandidateDigest string
}

// NewHandler 构造 HTTP 适配器；observer 可为空。
func NewHandler(
	svc *application.SearchService,
	decorator *application.RankingDecorator,
	observer application.SearchRequestObserver,
) *Handler {
	return &Handler{svc: svc, decorator: decorator, observer: observer}
}

func NewHandlerWithConfig(
	svc *application.SearchService,
	decorator *application.RankingDecorator,
	observer application.SearchRequestObserver,
	config HandlerConfig,
) *Handler {
	return &Handler{
		svc:             svc,
		decorator:       decorator,
		observer:        observer,
		intersections:   config.Intersections,
		requestFacts:    config.RequestFacts,
		candidateDigest: strings.TrimSpace(config.CandidateDigest),
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
}

type searchRequestWire struct {
	Query       string   `json:"query"`
	Mode        string   `json:"mode"`
	ObjectTypes []string `json:"objectTypes"`
	IDs         []string `json:"ids"`
	Limit       int      `json:"limit"`
	Cursor      string   `json:"cursor"`
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
// envelope fields (requestId/experimentBucket/relatedTerms)
// declared in metadata. Per-hit rankReasons/rankPosition ride on the embedded
// RetrieveHit (single-sourced in runtime/search).
type searchResponseWire struct {
	Hits             []canonicalSearchHitWire  `json:"hits"`
	Citations        []rtsearch.Citation       `json:"citations"`
	Facets           []rtsearch.Facet          `json:"facets"`
	DegradeSignals   []rtsearch.DegradeSignal  `json:"degradeSignals"`
	Provenance       rtsearch.Provenance       `json:"provenance"`
	RequestID        string                    `json:"requestId"`
	ExperimentBucket string                    `json:"experimentBucket,omitempty"`
	RelatedTerms     []string                  `json:"relatedTerms"`
	InterpretedQuery rtsearch.InterpretedQuery `json:"interpretedQuery"`
	NextCursor       string                    `json:"nextCursor,omitempty"`
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
	experimentSubjectKey, err := SubjectKeyFor(viewer, r)
	if err != nil {
		writeErr(
			w,
			requestID,
			rterrors.NewInvalidArgument(
				moduleSearch,
				"匿名搜索需要有效的会话标识。",
				err.Error(),
			),
		)
		return
	}
	// Canonical normalization (single source: runtime/search.Analyze) so the
	// query log, heat mining and ranking all key off the same normalized term.
	normalizedQuery := rtsearch.Analyze(body.Query, nil).Normalized
	in := application.QueryInput{
		Query:       body.Query,
		Mode:        body.Mode,
		ObjectTypes: body.ObjectTypes,
		IDs:         body.IDs,
		Limit:       body.Limit,
		Tags:        body.Filters.Tags,
		TimeRange:   parseTimeRange(body),
		Near:        parseNear(body),
		Cursor:      body.Cursor,
	}
	caller := queryCallerFrom(r)
	identity := application.QueryExecutionIdentity{
		CandidateDigest: h.candidateDigest,
		PolicyDigest:    h.decorator.PolicyDigest(),
	}
	if caller.ServiceName == "api-edge" || strings.EqualFold(strings.TrimSpace(body.Mode), "retrieval") {
		contractGraphDigest := "sha256:" + operationsecurity.ContractGraphSHA256
		if caller.ServiceName != "" && r.Header.Get(contractGraphSHA256Header) != contractGraphDigest {
			writeErr(w, requestID, rterrors.NewInvalidArgument(
				moduleSearch,
				"搜索契约暂不可用，请重试。",
				"search owner ContractGraph binding does not match embedded runtime identity",
			))
			return
		}
		ownerResponse, ownerErr := h.svc.ExecuteOwnerQuery(r.Context(), in, viewer, caller, identity)
		if ownerErr != nil {
			h.writeSearchExecutionError(w, requestID, ownerErr)
			return
		}
		if caller.ServiceName != "" {
			w.Header().Set(contractGraphSHA256Header, contractGraphDigest)
		}
		writeJSON(w, http.StatusOK, ownerResponse)
		return
	}

	// 计时覆盖召回、排序与交集 attach；异步 query log 仍在响应后执行。
	start := time.Now()
	execution, err := h.svc.Execute(r.Context(), in, viewer, caller, identity)
	if err != nil {
		h.observeSearch(application.SearchObservation{
			Mode: body.Mode, Bucket: application.BucketControl,
			Seconds: time.Since(start).Seconds(), Err: true,
		})
		h.writeSearchExecutionError(w, requestID, err)
		return
	}
	resp := execution.Response

	ranked, err := h.decorator.Decorate(
		r.Context(),
		resp,
		normalizedQuery,
		experimentSubjectKey,
	)
	if err != nil {
		h.observeSearch(application.SearchObservation{
			Mode: body.Mode, Bucket: application.BucketControl,
			Seconds: time.Since(start).Seconds(), Err: true,
		})
		writeErr(
			w,
			requestID,
			rterrors.NewUnavailable(
				moduleSearch,
				"搜索暂时不可用，请稍后再试。",
				"experiment assignment: "+err.Error(),
			),
		)
		return
	}
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
		Hits:             canonicalSearchHits(resp.Hits),
		Citations:        resp.Citations,
		Facets:           resp.Facets,
		DegradeSignals:   resp.DegradeSignals,
		Provenance:       resp.Provenance,
		RequestID:        requestID,
		ExperimentBucket: ranked.ExperimentBucket,
		RelatedTerms:     ranked.RelatedTerms,
		InterpretedQuery: execution.InterpretedQuery,
		NextCursor:       execution.NextCursor,
	})

	// Best-effort query log on a detached context so a slow/failed Mongo write
	// never blocks or fails the search that was already served.
	h.logQueryAsync(r, requestapplication.QueryLog{
		SearchRequestID:  requestID,
		Query:            normalizedQuery,
		SessionID:        strings.TrimSpace(r.Header.Get(SearchSessionIDHeader)),
		Mode:             body.Mode,
		ViewerID:         viewer.UserID,
		ObjectTypes:      body.ObjectTypes,
		ResultCount:      len(resp.Hits),
		ExperimentBucket: ranked.ExperimentBucket,
		RelatedTerms:     ranked.RelatedTerms,
	})
}

func (h *Handler) writeSearchExecutionError(w http.ResponseWriter, requestID string, err error) {
	if errors.Is(err, application.ErrSearchForbidden) {
		writeErr(w, requestID, rterrors.NewAppError(
			rterrors.NewCode(moduleSearch, rterrors.KindUser, "forbidden"),
			"当前身份不能执行该检索模式。", err.Error(),
		).WithMetadata("forbidden", http.StatusForbidden))
		return
	}
	if errors.Is(err, application.ErrSearchInvalid) || errors.Is(err, application.ErrSearchCursor) {
		writeErr(w, requestID, rterrors.NewInvalidArgument(moduleSearch, "搜索请求格式不正确。", err.Error()))
		return
	}
	writeErr(w, requestID, rterrors.NewUnavailable(moduleSearch, "搜索暂时不可用，请稍后再试。", "retrieve: "+err.Error()))
}

func (h *Handler) logQueryAsync(r *http.Request, qlog requestapplication.QueryLog) {
	if h.requestFacts == nil {
		return
	}
	logCtx, cancel := context.WithTimeout(context.WithoutCancel(r.Context()), queryLogTimeout)
	go func() {
		defer cancel()
		h.requestFacts.Record(logCtx, qlog)
	}()
}

func (h *Handler) observeSearch(observation application.SearchObservation) {
	if h.observer != nil {
		h.observer.ObserveSearch(observation)
	}
}

// SubjectKeyFor returns the canonical stable AB assignment unit: logged-in
// viewer identity first, otherwise the anonymous session identity declared by
// the SearchRequestFact contract. Request IDs are intentionally excluded because they
// would re-roll the experiment arm on every keystroke.
func SubjectKeyFor(viewer rtsearch.Viewer, r *http.Request) (string, error) {
	if id := strings.TrimSpace(viewer.UserID); id != "" && !strings.HasPrefix(id, "service:") {
		return id, nil
	}
	if sessionID := strings.TrimSpace(r.Header.Get(SearchSessionIDHeader)); sessionID != "" {
		return sessionID, nil
	}
	if principal, ok := rtauth.PrincipalFromContext(r.Context()); ok {
		serviceName := strings.TrimSpace(principal.ServiceActorID)
		if serviceName == "" && strings.HasPrefix(strings.TrimSpace(principal.Subject), "service:") {
			serviceName = strings.TrimPrefix(strings.TrimSpace(principal.Subject), "service:")
		}
		if serviceName == "assistant-service" {
			return "service:assistant-service", nil
		}
	}
	return "", fmt.Errorf("anonymous search requires a non-empty %s header", SearchSessionIDHeader)
}

func queryCallerFrom(r *http.Request) application.QueryCaller {
	sessionID := strings.TrimSpace(r.Header.Get(SearchSessionIDHeader))
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return application.QueryCaller{PrincipalKey: "session:" + sessionID}
	}
	serviceName := strings.TrimSpace(principal.ServiceActorID)
	if serviceName == "" && strings.HasPrefix(strings.TrimSpace(principal.Subject), "service:") {
		serviceName = strings.TrimPrefix(strings.TrimSpace(principal.Subject), "service:")
	}
	accountID := strings.TrimSpace(principal.Actor.AccountID)
	personaID := strings.TrimSpace(principal.Actor.PersonaID)
	principalKey := ""
	switch {
	case personaID != "":
		principalKey = "persona:" + personaID
	case accountID != "" && !strings.HasPrefix(accountID, "service:"):
		principalKey = "account:" + accountID
	case sessionID != "":
		principalKey = "session:" + sessionID
	default:
		principalKey = "service:" + serviceName
	}
	if serviceName != "" {
		principalKey += "|service:" + serviceName
	}
	scopes := strings.Fields(principal.Scope)
	scopes = append(scopes, principal.Permissions...)
	return application.QueryCaller{
		PrincipalKey: principalKey,
		ServiceName:  serviceName,
		Scopes:       scopes,
	}
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
