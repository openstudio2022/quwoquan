package searchsignals

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/search-service/internal/application"
)

const (
	StreamName       = "events.search.recommendation_signals"
	StreamTTLSeconds = 86400
	StreamTTL        = StreamTTLSeconds * time.Second
)

// StreamPublisher publishes SearchRecommendationSignalPublished events to the
// cross-service Redis Stream consumed by content-service.
type StreamPublisher struct {
	redis  rtredis.Client
	logger *slog.Logger
}

var _ application.SearchSignalPublisher = (*StreamPublisher)(nil)

func NewStreamPublisher(redis rtredis.Client, logger *slog.Logger) *StreamPublisher {
	if logger == nil {
		logger = slog.Default()
	}
	return &StreamPublisher{redis: redis, logger: logger}
}

func (p *StreamPublisher) PublishSearchSignal(ctx context.Context, signal application.SearchRecommendationSignal) error {
	if p == nil || p.redis == nil {
		return nil
	}
	values, err := StreamValues(signal)
	if err != nil {
		return err
	}
	if _, err := p.redis.XAdd(ctx, StreamName, values); err != nil {
		return fmt.Errorf("publish search recommendation signal: %w", err)
	}
	if err := p.redis.Expire(ctx, StreamName, StreamTTL); err != nil {
		return fmt.Errorf("expire search recommendation signal stream: %w", err)
	}
	if p.logger != nil {
		p.logger.DebugContext(ctx, "search recommendation signal published",
			slog.String("stream", StreamName),
			slog.String("searchRequestId", signal.SearchRequestID),
			slog.String("userId", signal.UserID))
	}
	return nil
}

func StreamValues(signal application.SearchRecommendationSignal) (map[string]string, error) {
	createdAt := signal.CreatedAt
	if createdAt.IsZero() {
		createdAt = time.Now().UTC()
	}
	related, err := jsonList(signal.RelatedTerms)
	if err != nil {
		return nil, fmt.Errorf("encode relatedTerms: %w", err)
	}
	topObjects, err := jsonList(signal.TopClickedObjectIDs)
	if err != nil {
		return nil, fmt.Errorf("encode topClickedObjectIds: %w", err)
	}
	return map[string]string{
		"eventType":           "SearchRecommendationSignalPublished",
		"searchRequestId":     strings.TrimSpace(signal.SearchRequestID),
		"sessionId":           strings.TrimSpace(signal.SessionID),
		"userId":              strings.TrimSpace(signal.UserID),
		"query":               strings.TrimSpace(signal.Query),
		"normalizedQuery":     strings.TrimSpace(signal.NormalizedQuery),
		"relatedTerms":        related,
		"topClickedObjectIds": topObjects,
		"rankingVersion":      strings.TrimSpace(signal.RankingVersion),
		"experimentBucket":    strings.TrimSpace(signal.ExperimentBucket),
		"resultCount":         strconv.Itoa(signal.ResultCount),
		"createdAt":           createdAt.UTC().Format(time.RFC3339Nano),
	}, nil
}

func jsonList(values []string) (string, error) {
	cleaned := make([]string, 0, len(values))
	for _, value := range values {
		if v := strings.TrimSpace(value); v != "" {
			cleaned = append(cleaned, v)
		}
	}
	raw, err := json.Marshal(cleaned)
	if err != nil {
		return "", err
	}
	return string(raw), nil
}
