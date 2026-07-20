// Package application holds the search-service use cases: the unified query
// (suggest|result) over the recall backend and search feedback intake.
package application

import (
	"context"
	"log/slog"
	"strings"
	"time"

	rtsearch "quwoquan_service/runtime/search"
)

// DefaultResultTargets is the result-page recall scope. chat.* is local_only and
// is intentionally excluded from the cloud search path.
var DefaultResultTargets = []rtsearch.Target{
	rtsearch.TargetArticle, rtsearch.TargetPhoto, rtsearch.TargetVideo,
	rtsearch.TargetCircle, rtsearch.TargetUser, rtsearch.TargetEntity, rtsearch.TargetGroup,
	rtsearch.TargetLocation,
}

// SuggestLimit / ResultLimit are the default page sizes when callers omit limit.
const (
	SuggestLimit = 12
	ResultLimit  = 20
	// RankingVersion lets observability/AB attribute hits to a ranking revision.
	RankingVersion = "search-v1"
)

// FeedbackEvent mirrors the metadata SearchFeedbackEvent entity.
type FeedbackEvent struct {
	SearchRequestID string `json:"searchRequestId"`
	ViewerID        string `json:"-"`
	EventType       string `json:"eventType"`
	ObjectID        string `json:"objectId,omitempty"`
	Target          string `json:"target,omitempty"`
	RankPosition    int    `json:"rankPosition,omitempty"`
	ReferralSource  string `json:"referralSource,omitempty"`
	FeedRequestID   string `json:"feedRequestId,omitempty"`
	DwellMs         int    `json:"dwellMs,omitempty"`
}

// FeedbackSink persists/forwards feedback events for query-heat mining and
// relevance evaluation. The cloud aggregation pipeline implements it; the
// service stays decoupled from storage (DDD: domain-facing port).
type FeedbackSink interface {
	Record(ctx context.Context, ev FeedbackEvent) error
}

// QueryLog mirrors the metadata SearchQuery entity write subset. It is the
// raw record of one /search call, the write source for search-term heat
// mining and relevance evaluation. SearchRequestID ties later impression/click/
// dwell feedback and ranking observability back to this single request.
type QueryLog struct {
	SearchRequestID  string
	Query            string // normalized query term (single-sourced normalization)
	RawQuery         string
	SessionID        string
	Mode             string
	ViewerID         string
	ObjectTypes      []string
	ResultCount      int
	RankingVersion   string
	ExperimentBucket string
	RelatedTerms     []string
	TopObjectIDs     []string
	CreatedAt        time.Time
}

// QueryLogSink persists query logs (best-effort, off the hot path). Implemented
// in infrastructure (Mongo); the service stays decoupled from the driver (DDD).
type QueryLogSink interface {
	Log(ctx context.Context, q QueryLog) error
}

// SearchSignalPublisher publishes structured search intent signals to downstream
// recommendation consumers. Implemented in infrastructure; failures stay
// best-effort so search retrieval never depends on recommendation plumbing.
type SearchSignalPublisher interface {
	PublishSearchSignal(ctx context.Context, signal SearchRecommendationSignal) error
}

// SearchRecommendationSignal mirrors SearchRecommendationSignalPublished.
type SearchRecommendationSignal struct {
	SearchRequestID     string
	SessionID           string
	UserID              string
	Query               string
	NormalizedQuery     string
	RelatedTerms        []string
	TopClickedObjectIDs []string
	RankingVersion      string
	ExperimentBucket    string
	ResultCount         int
	CreatedAt           time.Time
}

// SearchService runs the canonical search(request) over the injected backend.
type SearchService struct {
	backend  rtsearch.RecallBackend
	feedback FeedbackSink
	queryLog QueryLogSink
	signals  SearchSignalPublisher
	logger   *slog.Logger
}

// Option configures optional SearchService collaborators without breaking the
// minimal (backend, feedback) constructor used by lighter wirings/tests.
type Option func(*SearchService)

// WithQueryLogSink injects the query-log persistence port (best-effort logging).
func WithQueryLogSink(sink QueryLogSink) Option {
	return func(s *SearchService) { s.queryLog = sink }
}

// WithLogger injects the structured logger used for best-effort failures.
func WithLogger(logger *slog.Logger) Option {
	return func(s *SearchService) {
		if logger != nil {
			s.logger = logger
		}
	}
}

// WithSearchSignalPublisher injects the best-effort downstream recommendation
// signal publisher.
func WithSearchSignalPublisher(pub SearchSignalPublisher) Option {
	return func(s *SearchService) { s.signals = pub }
}

// NewSearchService builds the use case. feedback/queryLog may be nil (accepted
// and dropped), so alpha wirings without Mongo still run the retrieve path.
func NewSearchService(backend rtsearch.RecallBackend, feedback FeedbackSink, opts ...Option) *SearchService {
	s := &SearchService{backend: backend, feedback: feedback, logger: slog.Default()}
	for _, opt := range opts {
		opt(s)
	}
	return s
}

// QueryInput is the canonical query-first input shared by App + AI agents.
type QueryInput struct {
	Query       string
	Mode        string
	ObjectTypes []string
	Limit       int
	Tags        []string
	TimeRange   *rtsearch.TimeRange
	// Near is the optional 附近 geo radius filter; it spans every target that
	// carries a Geo dimension (entity/content today, user/circle next).
	Near *rtsearch.GeoNear
}

// Search runs the unified retrieve over the backend, mapping the query-first
// input into the frozen RetrieveRequest contract (single-sourced in runtime).
func (s *SearchService) Search(ctx context.Context, in QueryInput, viewer rtsearch.Viewer) (rtsearch.RetrieveResponse, error) {
	limit := in.Limit
	if limit <= 0 {
		if strings.EqualFold(in.Mode, "suggest") {
			limit = SuggestLimit
		} else {
			limit = ResultLimit
		}
	}
	filters := rtsearch.RetrieveFilters{Tags: in.Tags, TimeRange: in.TimeRange, Near: in.Near}
	req := rtsearch.BuildQueryFirstRequest(in.Query, in.ObjectTypes, limit, filters, DefaultResultTargets)
	return rtsearch.Retrieve(ctx, req, s.backend, viewer)
}

// LogQuery records a query log entry as a best-effort side channel. It NEVER
// blocks or fails the main retrieve path: on a nil sink it is a no-op, and on a
// sink error it emits a structured warning (no empty catch) and returns. The
// caller invokes it after the response is built so logging latency never enters
// the user-perceived search latency.
func (s *SearchService) LogQuery(ctx context.Context, q QueryLog) {
	if q.CreatedAt.IsZero() {
		q.CreatedAt = time.Now().UTC()
	}
	if s.queryLog == nil {
		// Query-log persistence is optional in alpha, but the recommendation
		// signal can still flow when Redis is configured.
	} else if err := s.queryLog.Log(ctx, q); err != nil {
		s.logger.WarnContext(ctx, "search query log persist failed (best-effort, retrieve unaffected)",
			slog.String("searchRequestId", q.SearchRequestID),
			slog.String("err", err.Error()),
		)
	}
	if s.signals == nil {
		return
	}
	if err := s.signals.PublishSearchSignal(ctx, SearchRecommendationSignal{
		SearchRequestID:     q.SearchRequestID,
		SessionID:           q.SessionID,
		UserID:              q.ViewerID,
		Query:               q.RawQuery,
		NormalizedQuery:     q.Query,
		RelatedTerms:        q.RelatedTerms,
		TopClickedObjectIDs: q.TopObjectIDs,
		RankingVersion:      q.RankingVersion,
		ExperimentBucket:    q.ExperimentBucket,
		ResultCount:         q.ResultCount,
		CreatedAt:           q.CreatedAt,
	}); err != nil {
		s.logger.WarnContext(ctx, "search recommendation signal publish failed (best-effort, retrieve unaffected)",
			slog.String("searchRequestId", q.SearchRequestID),
			slog.String("err", err.Error()),
		)
	}
}

// ReportFeedback forwards a feedback event to the sink (no-op when unset).
func (s *SearchService) ReportFeedback(ctx context.Context, ev FeedbackEvent) error {
	if s.feedback == nil {
		return nil
	}
	return s.feedback.Record(ctx, ev)
}
