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
	signalapplication "quwoquan_service/services/search-service/internal/search/recommendation_signal_fact/application"
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

// StreamPublisher publishes the object-owned recommendation signal fact.
type StreamPublisher struct {
	transport StreamTransport
	logger    *slog.Logger
}

var _ signalapplication.Publisher = (*StreamPublisher)(nil)

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

func (p *StreamPublisher) PublishSearchSignal(
	ctx context.Context,
	signal signalapplication.Signal,
) error {
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
			slog.String("signalType", signal.SignalType),
			slog.String("searchRequestId", signal.SearchRequestID))
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

func StreamValues(signal signalapplication.Signal) (map[string]string, error) {
	createdAt := signal.CreatedAt
	if createdAt.IsZero() {
		createdAt = time.Now().UTC()
	}
	related, err := jsonList(signal.RelatedTerms)
	if err != nil {
		return nil, fmt.Errorf("encode relatedTerms: %w", err)
	}
	engagedObjects, err := jsonList(signal.EngagedObjectIDs)
	if err != nil {
		return nil, fmt.Errorf("encode engagedObjectIds: %w", err)
	}
	signalID := strings.TrimSpace(signal.SignalID)
	signalType := strings.TrimSpace(signal.SignalType)
	searchRequestID := strings.TrimSpace(signal.SearchRequestID)
	normalizedQuery := strings.TrimSpace(signal.NormalizedQuery)
	if signalID == "" || searchRequestID == "" {
		return nil, fmt.Errorf("signalId and searchRequestId are required")
	}
	switch signalType {
	case "query":
		if normalizedQuery == "" || len(signal.EngagedObjectIDs) > 0 {
			return nil, fmt.Errorf("query signal requires normalizedQuery and no engaged objects")
		}
	case "click":
		if len(signal.EngagedObjectIDs) == 0 || normalizedQuery != "" {
			return nil, fmt.Errorf("click signal requires engaged objects and no query")
		}
	default:
		return nil, fmt.Errorf("unsupported signalType %q", signalType)
	}
	return map[string]string{
		"eventType":        "SearchRecommendationSignalPublished",
		"signalId":         signalID,
		"signalType":       signalType,
		"searchRequestId":  searchRequestID,
		"sessionId":        strings.TrimSpace(signal.SessionID),
		"userId":           strings.TrimSpace(signal.UserID),
		"normalizedQuery":  normalizedQuery,
		"relatedTerms":     related,
		"engagedObjectIds": engagedObjects,
		"experimentBucket": strings.TrimSpace(signal.ExperimentBucket),
		"resultCount":      strconv.Itoa(signal.ResultCount),
		"createdAt":        createdAt.UTC().Format(time.RFC3339Nano),
	}, nil
}

func jsonList(values []string) (string, error) {
	cleaned := make([]string, 0, len(values))
	for _, value := range values {
		if normalized := strings.TrimSpace(value); normalized != "" {
			cleaned = append(cleaned, normalized)
		}
	}
	raw, err := json.Marshal(cleaned)
	if err != nil {
		return "", err
	}
	return string(raw), nil
}
