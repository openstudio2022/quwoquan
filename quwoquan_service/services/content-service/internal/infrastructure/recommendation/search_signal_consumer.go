package recommendation

import (
	"context"
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
	searchSignalConsumerGroup        = "content-service"
	searchSignalDedupTTL             = 24 * time.Hour
	searchSignalStreamTTL            = 24 * time.Hour
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
	return c.redis.XGroupCreateMkStream(ctx, SearchRecommendationSignalStream, searchSignalConsumerGroup, "0")
}

func (c *SearchSignalConsumer) ProcessOnce(ctx context.Context) (int, error) {
	if c == nil || c.redis == nil || c.projector == nil {
		return 0, fmt.Errorf("search signal consumer not configured")
	}
	if err := c.EnsureGroup(ctx); err != nil {
		return 0, err
	}
	messages, err := c.redis.XReadGroup(ctx, searchSignalConsumerGroup, c.consumer, map[string]string{SearchRecommendationSignalStream: ">"}, 20, 200*time.Millisecond)
	if err != nil {
		return 0, err
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
				if err := c.redis.XAck(ctx, SearchRecommendationSignalStream, searchSignalConsumerGroup, msg.ID); err != nil {
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
			if dedupKey != "" {
				_ = c.redis.Del(ctx, dedupKey)
			}
			if _, dlqErr := c.redis.XAdd(ctx, SearchRecommendationSignalDLQ, deadLetterSearchSignalValues(msg, err)); dlqErr != nil {
				return processed, fmt.Errorf("search signal dlq: %w", dlqErr)
			}
			if expErr := c.redis.Expire(ctx, SearchRecommendationSignalDLQ, searchSignalStreamTTL); expErr != nil {
				return processed, fmt.Errorf("search signal dlq expire: %w", expErr)
			}
			processed++
			continue
		}
		if err := c.redis.XAck(ctx, SearchRecommendationSignalStream, searchSignalConsumerGroup, msg.ID); err != nil {
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
	occurredAt := parseSignalTime(msg.Values["createdAt"])
	payload := map[string]any{
		"userId":              msg.Values["userId"],
		"sessionId":           msg.Values["sessionId"],
		"searchRequestId":     msg.Values["searchRequestId"],
		"query":               msg.Values["query"],
		"normalizedQuery":     msg.Values["normalizedQuery"],
		"relatedTerms":        stringList(msg.Values["relatedTerms"]),
		"topClickedObjectIds": stringList(msg.Values["topClickedObjectIds"]),
		"rankingVersion":      msg.Values["rankingVersion"],
		"experimentBucket":    msg.Values["experimentBucket"],
		"resultCount":         intValue(msg.Values["resultCount"]),
	}
	return c.projector.Project(ctx, ProjectorEvent{
		ID:            msg.ID,
		Type:          "SearchRecommendationSignalPublished",
		AggregateType: "SearchQuery",
		AggregateID:   msg.Values["searchRequestId"],
		Payload:       payload,
		OccurredAt:    occurredAt,
	})
}

func searchSignalDedupKey(msg rtredis.StreamMessage) string {
	requestID := strings.TrimSpace(msg.Values["searchRequestId"])
	if requestID == "" {
		return ""
	}
	return "events.search.recommendation_signals.dedup:" + requestID
}

func deadLetterSearchSignalValues(msg rtredis.StreamMessage, err error) map[string]string {
	values := map[string]string{
		"streamId": msg.ID,
		"error":    err.Error(),
	}
	for key, value := range msg.Values {
		values[key] = value
	}
	return values
}

func stringList(raw string) []string {
	var out []string
	if strings.TrimSpace(raw) == "" {
		return nil
	}
	if err := json.Unmarshal([]byte(raw), &out); err == nil {
		return out
	}
	return nil
}

func intValue(raw string) int {
	n, _ := strconv.Atoi(strings.TrimSpace(raw))
	return n
}

func parseSignalTime(raw string) time.Time {
	if ts, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(raw)); err == nil {
		return ts.UTC()
	}
	return time.Now().UTC()
}
