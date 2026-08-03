// Package application owns SearchRequestFact append behavior and its typed
// downstream publication after the immutable fact has been persisted.
package application

import (
	"context"
	"log/slog"
	"strings"
	"time"

	signalapplication "quwoquan_service/services/search-service/internal/search/recommendation_signal_fact/application"
	requestdomain "quwoquan_service/services/search-service/internal/search/search_request_fact/domain"
)

// QueryLog is the immutable SearchRequestFact write payload. SearchRequestID
// correlates later feedback and ranking observations with this one request.
type QueryLog = requestdomain.QueryLog

// QueryLogSink appends SearchRequestFact records without exposing MongoDB to
// the query facade.
type QueryLogSink interface {
	Log(context.Context, QueryLog) error
}

// Recorder is the SearchRequestFact application facade used by SearchIndexView
// after a response has been formed. Recommendation signals are emitted only
// after the immutable request fact has persisted successfully.
type Recorder struct {
	sink    QueryLogSink
	signals signalapplication.Publisher
	logger  *slog.Logger
}

func NewRecorder(
	sink QueryLogSink,
	signals signalapplication.Publisher,
	logger *slog.Logger,
) *Recorder {
	if logger == nil {
		logger = slog.Default()
	}
	return &Recorder{sink: sink, signals: signals, logger: logger}
}

// Record appends the fact and then publishes its typed derived signal. It runs
// on a bounded detached context owned by the inbound adapter, so persistence
// cannot extend user-visible search latency.
func (r *Recorder) Record(ctx context.Context, query QueryLog) {
	if r == nil || r.sink == nil {
		return
	}
	if query.CreatedAt.IsZero() {
		query.CreatedAt = time.Now().UTC()
	}
	if err := query.Validate(); err != nil {
		r.logger.WarnContext(ctx, "invalid SearchRequestFact", slog.String("err", err.Error()))
		return
	}
	if err := r.sink.Log(ctx, query); err != nil {
		r.logger.WarnContext(
			ctx,
			"search request fact append failed",
			slog.String("searchRequestId", query.SearchRequestID),
			slog.String("err", err.Error()),
		)
		return
	}
	if r.signals == nil {
		return
	}
	if err := r.signals.PublishSearchSignal(ctx, signalapplication.Signal{
		SignalID:         "query:" + strings.TrimSpace(query.SearchRequestID),
		SignalType:       "query",
		SearchRequestID:  query.SearchRequestID,
		SessionID:        query.SessionID,
		UserID:           query.ViewerID,
		NormalizedQuery:  query.Query,
		RelatedTerms:     query.RelatedTerms,
		ExperimentBucket: query.ExperimentBucket,
		ResultCount:      query.ResultCount,
		CreatedAt:        query.CreatedAt,
	}); err != nil {
		r.logger.WarnContext(
			ctx,
			"search request fact signal publish failed",
			slog.String("searchRequestId", query.SearchRequestID),
			slog.String("err", err.Error()),
		)
	}
}
