package searchsignals

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"sort"
	"strconv"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/search-service/internal/application"
)

const (
	StreamName       = "events.search.recommendation_signals"
	StreamTTLSeconds = 86400
	StreamTTL        = StreamTTLSeconds * time.Second
)

type StreamTransport interface {
	runtimemessaging.MessageTransport
	runtimemessaging.DurableDeliveryTransport
}

// StreamPublisher publishes SearchRecommendationSignalPublished events to the
// cross-service Redis Stream consumed by content-service.
type StreamPublisher struct {
	transport StreamTransport
	logger    *slog.Logger
}

var _ application.SearchSignalPublisher = (*StreamPublisher)(nil)

func NewStreamPublisher(
	transport StreamTransport,
	logger *slog.Logger,
) (*StreamPublisher, error) {
	if transport == nil {
		return nil, fmt.Errorf("search recommendation signal publisher requires message transport")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &StreamPublisher{transport: transport, logger: logger}, nil
}

func (p *StreamPublisher) PublishSearchSignal(ctx context.Context, signal application.SearchRecommendationSignal) error {
	if p == nil || p.transport == nil {
		return fmt.Errorf("search recommendation signal transport is unavailable")
	}
	values, err := StreamValues(signal)
	if err != nil {
		return err
	}
	if _, err := p.transport.AppendDurable(ctx, runtimemessaging.DurableMessage{
		Stream: StreamName,
		Fields: durableFields(values),
	}); err != nil {
		return fmt.Errorf("publish search recommendation signal: %w", err)
	}
	if err := p.transport.SetDurableRetention(ctx, StreamName, StreamTTL); err != nil {
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

func durableFields(values map[string]string) []runtimemessaging.DurableField {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	fields := make([]runtimemessaging.DurableField, 0, len(keys))
	for _, key := range keys {
		fields = append(fields, runtimemessaging.DurableField{
			Name:  key,
			Value: values[key],
		})
	}
	return fields
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
