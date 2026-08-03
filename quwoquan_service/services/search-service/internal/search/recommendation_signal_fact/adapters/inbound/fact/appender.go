package fact

import (
	"context"
	"errors"

	signalapplication "quwoquan_service/services/search-service/internal/search/recommendation_signal_fact/application"
)

// Appender is the single internal-port adapter used by SearchRequestFact and
// SearchFeedbackFact after their own immutable facts have committed.
type Appender struct {
	application *signalapplication.Appender
}

func NewAppender(application *signalapplication.Appender) (*Appender, error) {
	if application == nil {
		return nil, errors.New("RecommendationSignalFact application appender is required")
	}
	return &Appender{application: application}, nil
}

func (adapter *Appender) PublishSearchSignal(
	ctx context.Context,
	signal signalapplication.Signal,
) error {
	return adapter.application.Append(ctx, signal)
}
