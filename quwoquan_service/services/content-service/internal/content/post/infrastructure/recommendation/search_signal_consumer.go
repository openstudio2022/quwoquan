package recommendation

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"log/slog"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

const (
	SearchRecommendationSignalStream = "events.search.recommendation_signals"
	SearchRecommendationSignalDLQ    = "events.search.recommendation_signals.dlq"
	SearchSignalConsumerGroup        = "content-service"
	searchSignalDedupTTL             = 24 * time.Hour
	searchSignalStreamTTL            = 24 * time.Hour
	searchSignalRetryMinIdle         = 30 * time.Second
)

// SearchSignalConsumer reads search-service Redis Stream signals and projects
// them into rm_recommend_feature through the existing RecommendFeatureProjector.
type SearchSignalConsumer struct {
	redis     rtredis.Client
	projector searchSignalProjector
	consumer  string
	logger    *slog.Logger
}

type searchSignalProjector interface {
	Project(ctx context.Context, event ProjectorEvent) error
}

func NewSearchSignalConsumer(redis rtredis.Client, projector searchSignalProjector, consumer string, logger *slog.Logger) *SearchSignalConsumer {
	if logger == nil {
		logger = slog.Default()
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = "content-search-signal-worker"
	}
	return &SearchSignalConsumer{redis: redis, projector: projector, consumer: consumer, logger: logger}
}

func (c *SearchSignalConsumer) EnsureGroup(ctx context.Context) error {
	if c == nil || c.redis == nil {
		return fmt.Errorf("search signal consumer redis not configured")
	}
	return c.redis.XGroupCreateMkStream(ctx, SearchRecommendationSignalStream, SearchSignalConsumerGroup, "0")
}

func (c *SearchSignalConsumer) ProcessOnce(ctx context.Context) (int, error) {
	if c == nil || c.redis == nil || c.projector == nil {
		return 0, fmt.Errorf("search signal consumer not configured")
	}
	if err := c.EnsureGroup(ctx); err != nil {
		return 0, err
	}
	messages, _, err := c.redis.XAutoClaim(
		ctx,
		SearchRecommendationSignalStream,
		SearchSignalConsumerGroup,
		c.consumer,
		searchSignalRetryMinIdle,
		"0-0",
		20,
	)
	if err != nil {
		return 0, err
	}
	if len(messages) < 20 {
		fresh, readErr := c.redis.XReadGroup(
			ctx,
			SearchSignalConsumerGroup,
			c.consumer,
			map[string]string{SearchRecommendationSignalStream: ">"},
			int64(20-len(messages)),
			200*time.Millisecond,
		)
		if readErr != nil {
			return 0, readErr
		}
		messages = append(messages, fresh...)
	}
	processed := 0
	for _, msg := range messages {
		dedupKey := searchSignalDedupKey(msg)
		if dedupKey != "" {
			claimed, err := c.redis.SetNX(ctx, dedupKey, msg.ID, searchSignalDedupTTL)
			if err != nil {
				return processed, err
			}
			if !claimed {
				if err := c.redis.XAck(ctx, SearchRecommendationSignalStream, SearchSignalConsumerGroup, msg.ID); err != nil {
					return processed, err
				}
				processed++
				continue
			}
		}
		if err := c.processMessage(ctx, msg); err != nil {
			c.logger.ErrorContext(ctx, "search recommendation signal consume failed",
				slog.String("streamId", msg.ID),
				slog.String("searchRequestId", msg.Values["searchRequestId"]),
				slog.String("err", err.Error()))
			if isMalformedSearchSignal(err) {
				if _, dlqErr := c.redis.XAdd(
					ctx,
					SearchRecommendationSignalDLQ,
					deadLetterSearchSignalValues(msg, err),
				); dlqErr != nil {
					return processed, fmt.Errorf("search signal dlq: %w", dlqErr)
				}
				if expErr := c.redis.Expire(ctx, SearchRecommendationSignalDLQ, searchSignalStreamTTL); expErr != nil {
					return processed, fmt.Errorf("search signal dlq expire: %w", expErr)
				}
				if ackErr := c.redis.XAck(
					ctx,
					SearchRecommendationSignalStream,
					SearchSignalConsumerGroup,
					msg.ID,
				); ackErr != nil {
					return processed, ackErr
				}
				processed++
				continue
			}
			if dedupKey != "" {
				_ = c.redis.Del(ctx, dedupKey)
			}
			return processed, err
		}
		if err := c.redis.XAck(ctx, SearchRecommendationSignalStream, SearchSignalConsumerGroup, msg.ID); err != nil {
			return processed, err
		}
		processed++
	}
	return processed, nil
}

func (c *SearchSignalConsumer) Run(ctx context.Context, interval time.Duration) {
	if interval <= 0 {
		interval = 500 * time.Millisecond
	}
	if err := c.EnsureGroup(ctx); err != nil {
		c.logger.ErrorContext(ctx, "search signal consumer ensure group failed", slog.String("err", err.Error()))
		return
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}
		if _, err := c.ProcessOnce(ctx); err != nil {
			c.logger.ErrorContext(ctx, "search signal consumer tick failed", slog.String("err", err.Error()))
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (c *SearchSignalConsumer) processMessage(ctx context.Context, msg rtredis.StreamMessage) error {
	signalID := strings.TrimSpace(msg.Values["signalId"])
	signalType := strings.TrimSpace(msg.Values["signalType"])
	requestID := strings.TrimSpace(msg.Values["searchRequestId"])
	if signalID == "" || requestID == "" {
		return malformedSearchSignal("missing_signal_identity")
	}
	occurredAt, err := parseSignalTime(msg.Values["createdAt"])
	if err != nil {
		return err
	}
	relatedTerms, err := stringList(msg.Values["relatedTerms"])
	if err != nil {
		return malformedSearchSignal("invalid_related_terms")
	}
	engagedObjectIDs, err := stringList(msg.Values["engagedObjectIds"])
	if err != nil {
		return malformedSearchSignal("invalid_engaged_object_ids")
	}
	resultCount, err := intValue(msg.Values["resultCount"])
	if err != nil {
		return malformedSearchSignal("invalid_result_count")
	}
	normalizedQuery := strings.TrimSpace(msg.Values["normalizedQuery"])
	switch signalType {
	case "query":
		if normalizedQuery == "" || len(engagedObjectIDs) != 0 {
			return malformedSearchSignal("invalid_query_signal")
		}
	case "click":
		if normalizedQuery != "" || len(engagedObjectIDs) == 0 {
			return malformedSearchSignal("invalid_click_signal")
		}
	default:
		return malformedSearchSignal("unsupported_signal_type")
	}
	payload := map[string]any{
		"signalId":         signalID,
		"signalType":       signalType,
		"userId":           msg.Values["userId"],
		"sessionId":        msg.Values["sessionId"],
		"searchRequestId":  requestID,
		"normalizedQuery":  normalizedQuery,
		"relatedTerms":     relatedTerms,
		"engagedObjectIds": engagedObjectIDs,
		"rankingVersion":   msg.Values["rankingVersion"],
		"experimentBucket": msg.Values["experimentBucket"],
		"resultCount":      resultCount,
	}
	return c.projector.Project(ctx, ProjectorEvent{
		ID:            signalID,
		Type:          "SearchRecommendationSignalPublished",
		AggregateType: "SearchQuery",
		AggregateID:   requestID,
		Payload:       payload,
		OccurredAt:    occurredAt,
	})
}

func searchSignalDedupKey(msg rtredis.StreamMessage) string {
	signalID := strings.TrimSpace(msg.Values["signalId"])
	if signalID == "" {
		return ""
	}
	digest := sha256.Sum256([]byte(signalID))
	return fmt.Sprintf("events.search.recommendation_signals.dedup:%x", digest)
}

func deadLetterSearchSignalValues(msg rtredis.StreamMessage, err error) map[string]string {
	signalDigest := sha256.Sum256([]byte(strings.TrimSpace(msg.Values["signalId"])))
	return map[string]string{
		"sourceStreamId": msg.ID,
		"signalDigest":   fmt.Sprintf("%x", signalDigest),
		"errorCode":      err.Error(),
		"quarantinedAt":  time.Now().UTC().Format(time.RFC3339Nano),
	}
}

func stringList(raw string) ([]string, error) {
	var out []string
	if strings.TrimSpace(raw) == "" {
		return nil, nil
	}
	if err := json.Unmarshal([]byte(raw), &out); err != nil {
		return nil, err
	}
	return uniqueNonEmpty(out), nil
}

func intValue(raw string) (int, error) {
	if strings.TrimSpace(raw) == "" {
		return 0, nil
	}
	n, err := strconv.Atoi(strings.TrimSpace(raw))
	if err != nil || n < 0 {
		return 0, fmt.Errorf("invalid non-negative integer")
	}
	return n, nil
}

func parseSignalTime(raw string) (time.Time, error) {
	ts, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(raw))
	if err != nil {
		return time.Time{}, malformedSearchSignal("invalid_created_at")
	}
	return ts.UTC(), nil
}

type malformedSearchSignalError struct {
	code string
}

func (e malformedSearchSignalError) Error() string {
	return e.code
}

func malformedSearchSignal(code string) error {
	return malformedSearchSignalError{code: code}
}

func isMalformedSearchSignal(err error) bool {
	_, ok := err.(malformedSearchSignalError)
	return ok
}
