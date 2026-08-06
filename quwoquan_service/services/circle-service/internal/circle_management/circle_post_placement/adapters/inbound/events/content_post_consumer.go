package events

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"strconv"
	"strings"
	"sync"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	placementports "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/domain/ports"
)

const (
	ContentPostLifecycleStream       = "events.content.post_lifecycle"
	ContentPostLifecycleDLQ          = "events.content.post_lifecycle.dlq"
	contentPostConsumerGroup         = "circle-service"
	contentPostMaxAttempts     int64 = 5
	contentPostStreamRetention       = 7 * 24 * time.Hour
)

// ContentPostConsumer maintains Circle's typed external Post reference through
// Redis Stream consumer-group delivery. Mongo inbox and aggregate version make
// new delivery, pending reclaim and duplicate XADD converge to one projection.
type ContentPostConsumer struct {
	transport               runtimemessaging.DurableDeliveryTransport
	projection              placementports.PostLifecycleProjection
	failures                placementports.PostLifecycleFailureStore
	invalidateDiscoveryFeed func(context.Context) error
	consumer                string
	minIdle                 time.Duration
	logger                  *slog.Logger
	mu                      sync.RWMutex
	lastSuccess             time.Time
	lastFailure             error
}

func NewContentPostConsumer(
	transport runtimemessaging.DurableDeliveryTransport,
	projection placementports.PostLifecycleProjection,
	failures placementports.PostLifecycleFailureStore,
	consumer string,
	logger *slog.Logger,
) *ContentPostConsumer {
	if logger == nil {
		logger = slog.Default()
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = "circle-post-projection"
	}
	return &ContentPostConsumer{
		transport: transport, projection: projection, failures: failures,
		consumer: consumer, minIdle: 30 * time.Second, logger: logger,
	}
}

// WithDiscoveryFeedCacheInvalidator keeps sibling infrastructure composition
// in cmd while this object depends only on the invalidation behavior it needs.
func (consumer *ContentPostConsumer) WithDiscoveryFeedCacheInvalidator(
	invalidate func(context.Context) error,
) *ContentPostConsumer {
	if consumer == nil {
		return nil
	}
	consumer.invalidateDiscoveryFeed = invalidate
	return consumer
}

func (consumer *ContentPostConsumer) EnsureGroup(ctx context.Context) error {
	if consumer == nil || consumer.transport == nil {
		return fmt.Errorf("Content Post consumer transport is not configured")
	}
	return consumer.transport.EnsureDurableConsumerGroup(
		ctx,
		ContentPostLifecycleStream,
		contentPostConsumerGroup,
		"0",
	)
}

func (consumer *ContentPostConsumer) ProcessOnce(ctx context.Context) (int, error) {
	if consumer == nil || consumer.transport == nil || consumer.projection == nil || consumer.failures == nil {
		return 0, fmt.Errorf("Content Post consumer is not fully configured")
	}
	if err := consumer.EnsureGroup(ctx); err != nil {
		consumer.recordFailure(err)
		return 0, err
	}
	claimed, _, err := consumer.transport.ReclaimDurable(
		ctx,
		ContentPostLifecycleStream,
		contentPostConsumerGroup,
		consumer.consumer,
		consumer.minIdle,
		"0-0",
		50,
	)
	if err != nil {
		consumer.recordFailure(err)
		return 0, err
	}
	newMessages, err := consumer.transport.ReadDurable(
		ctx,
		runtimemessaging.StreamReadRequest{
			Stream:   ContentPostLifecycleStream,
			Group:    contentPostConsumerGroup,
			Consumer: consumer.consumer,
			Count:    50,
			Block:    200 * time.Millisecond,
		},
	)
	if err != nil {
		consumer.recordFailure(err)
		return 0, err
	}
	messages := uniqueStreamMessages(claimed, newMessages)
	processed := 0
	var firstErr error
	for _, message := range messages {
		if err := consumer.processMessage(ctx, message); err != nil {
			if firstErr == nil {
				firstErr = err
			}
			continue
		}
		processed++
	}
	if firstErr != nil {
		consumer.recordFailure(firstErr)
		return processed, firstErr
	}
	consumer.recordSuccess()
	return processed, nil
}

func (consumer *ContentPostConsumer) Run(ctx context.Context, interval time.Duration) {
	if interval <= 0 {
		interval = 250 * time.Millisecond
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := consumer.ProcessOnce(ctx); err != nil && ctx.Err() == nil {
			consumer.logger.ErrorContext(ctx, "Content Post projection consume failed", slog.String("error", err.Error()))
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (consumer *ContentPostConsumer) Healthy(maxStaleness time.Duration) error {
	if consumer == nil {
		return fmt.Errorf("Content Post consumer is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	consumer.mu.RLock()
	defer consumer.mu.RUnlock()
	if consumer.lastSuccess.IsZero() {
		return fmt.Errorf("Content Post consumer has not completed a scan")
	}
	if consumer.lastFailure != nil {
		return fmt.Errorf("Content Post consumer last failure: %w", consumer.lastFailure)
	}
	if time.Since(consumer.lastSuccess) > maxStaleness {
		return fmt.Errorf("Content Post consumer heartbeat is stale")
	}
	return nil
}

func (consumer *ContentPostConsumer) processMessage(ctx context.Context, message runtimemessaging.StreamDelivery) error {
	values := runtimemessaging.DurableFieldMap(message.Fields)
	event, err := decodePostLifecycleMessage(values)
	if err == nil {
		err = consumer.projection.ApplyPostLifecycle(ctx, event)
	}
	if err == nil && consumer.invalidateDiscoveryFeed != nil {
		err = consumer.invalidateDiscoveryFeed(ctx)
	}
	if err != nil {
		attempts, recordErr := consumer.failures.RecordPostLifecycleFailure(ctx, message.ID, values["eventId"], err)
		if recordErr != nil {
			return fmt.Errorf("record Content Post projection failure: %w", recordErr)
		}
		if attempts < contentPostMaxAttempts {
			return fmt.Errorf("Content Post projection attempt %d/%d: %w", attempts, contentPostMaxAttempts, err)
		}
		if _, dlqErr := consumer.transport.PublishDeadLetter(
			ctx,
			runtimemessaging.DeadLetterMessage{
				SourceStream:      ContentPostLifecycleStream,
				DestinationStream: ContentPostLifecycleDLQ,
				SourceID:          message.ID,
				Reason:            "projection_failed",
				Fields:            postLifecycleDLQFields(message, err, attempts),
			},
		); dlqErr != nil {
			return fmt.Errorf("append Content Post projection DLQ: %w", dlqErr)
		}
		if expireErr := consumer.transport.SetDurableRetention(ctx, ContentPostLifecycleDLQ, contentPostStreamRetention); expireErr != nil {
			return fmt.Errorf("refresh Content Post projection DLQ retention: %w", expireErr)
		}
		if ackErr := consumer.transport.AckDurable(ctx, ContentPostLifecycleStream, contentPostConsumerGroup, message.ID); ackErr != nil {
			return fmt.Errorf("ack dead-lettered Content Post event: %w", ackErr)
		}
		return consumer.failures.ClearPostLifecycleFailure(ctx, message.ID)
	}
	if err := consumer.transport.AckDurable(ctx, ContentPostLifecycleStream, contentPostConsumerGroup, message.ID); err != nil {
		return fmt.Errorf("ack Content Post lifecycle event: %w", err)
	}
	return consumer.failures.ClearPostLifecycleFailure(ctx, message.ID)
}

func decodePostLifecycleMessage(values map[string]string) (placementports.PostLifecycleEvent, error) {
	if strings.TrimSpace(values["aggregateType"]) != "Post" {
		return placementports.PostLifecycleEvent{}, fmt.Errorf("Content lifecycle aggregateType must be Post")
	}
	version, err := strconv.ParseInt(strings.TrimSpace(values["aggregateVersion"]), 10, 64)
	if err != nil || version <= 0 {
		return placementports.PostLifecycleEvent{}, fmt.Errorf("Content Post lifecycle aggregateVersion is invalid")
	}
	occurredAt, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(values["occurredAt"]))
	if err != nil {
		return placementports.PostLifecycleEvent{}, fmt.Errorf("Content Post lifecycle occurredAt is invalid")
	}
	var payload struct {
		PostID                    string   `json:"postId"`
		AuthorID                  string   `json:"authorId"`
		AuthorDisplayNameSnapshot string   `json:"authorDisplayNameSnapshot"`
		AuthorAvatarURLSnapshot   string   `json:"authorAvatarUrlSnapshot"`
		Status                    string   `json:"status"`
		Visibility                string   `json:"visibility"`
		ModerationStatus          string   `json:"moderationStatus"`
		ContentType               string   `json:"contentType"`
		ContentIdentity           string   `json:"contentIdentity"`
		AssistantUsePolicy        string   `json:"assistantUsePolicy"`
		Title                     string   `json:"title"`
		Body                      string   `json:"body"`
		Summary                   string   `json:"summary"`
		MediaURLs                 []string `json:"mediaUrls"`
		MediaItems                []struct {
			URL string `json:"url"`
		} `json:"mediaItems"`
		CoverURL        string `json:"coverUrl"`
		ThumbnailURL    string `json:"thumbnailUrl"`
		VideoURL        string `json:"videoUrl"`
		Width           int64  `json:"width"`
		Height          int64  `json:"height"`
		DurationMs      int64  `json:"durationMs"`
		LikeCount       int64  `json:"likeCount"`
		CommentCount    int64  `json:"commentCount"`
		ShareCount      int64  `json:"shareCount"`
		ContentVertical string `json:"contentVertical"`
		CreatedAt       string `json:"createdAt"`
		UpdatedAt       string `json:"updatedAt"`
		PublishedAt     string `json:"publishedAt"`
	}
	if err := json.Unmarshal([]byte(values["payload"]), &payload); err != nil {
		return placementports.PostLifecycleEvent{}, fmt.Errorf("decode Content Post lifecycle payload: %w", err)
	}
	postID := strings.TrimSpace(values["aggregateId"])
	payloadPostID := strings.TrimSpace(payload.PostID)
	if postID == "" || payloadPostID != "" && payloadPostID != postID {
		return placementports.PostLifecycleEvent{}, fmt.Errorf("Content Post lifecycle aggregate identity mismatch")
	}
	event := placementports.PostLifecycleEvent{
		EventID: strings.TrimSpace(values["eventId"]), EventType: strings.TrimSpace(values["eventType"]),
		PostID: postID, PostVersion: version, OwnerPersonaID: strings.TrimSpace(payload.AuthorID),
		State: strings.TrimSpace(payload.Status), Visibility: strings.TrimSpace(payload.Visibility),
		Moderation: strings.TrimSpace(payload.ModerationStatus), OccurredAt: occurredAt.UTC(),
	}
	if event.EventID == "" || event.EventType == "" {
		return placementports.PostLifecycleEvent{}, fmt.Errorf("Content Post lifecycle event identity is incomplete")
	}
	if postLifecycleCarriesFeedSnapshot(event.EventType) {
		createdAt, err := parsePostLifecycleSnapshotTime(payload.CreatedAt, "createdAt")
		if err != nil {
			return placementports.PostLifecycleEvent{}, err
		}
		updatedAt, err := parsePostLifecycleSnapshotTime(payload.UpdatedAt, "updatedAt")
		if err != nil {
			return placementports.PostLifecycleEvent{}, err
		}
		publishedAt, err := parsePostLifecycleSnapshotTime(payload.PublishedAt, "publishedAt")
		if err != nil {
			return placementports.PostLifecycleEvent{}, err
		}
		if strings.TrimSpace(payload.ContentType) == "" || event.OwnerPersonaID == "" {
			return placementports.PostLifecycleEvent{}, fmt.Errorf("Content Post feed snapshot is incomplete")
		}
		mediaURLs := compactPostMediaURLs(payload.MediaURLs, payload.MediaItems)
		event.FeedItem = &placementports.PostFeedItemSnapshot{
			ContentType:        strings.TrimSpace(payload.ContentType),
			ContentIdentity:    strings.TrimSpace(payload.ContentIdentity),
			AssistantUsePolicy: strings.TrimSpace(payload.AssistantUsePolicy),
			AuthorDisplayName:  strings.TrimSpace(payload.AuthorDisplayNameSnapshot),
			AuthorAvatarURL:    strings.TrimSpace(payload.AuthorAvatarURLSnapshot),
			Title:              payload.Title, Body: payload.Body, Summary: payload.Summary,
			CoverURL: strings.TrimSpace(payload.CoverURL), MediaURLs: mediaURLs,
			VideoURL: strings.TrimSpace(payload.VideoURL), ThumbnailURL: strings.TrimSpace(payload.ThumbnailURL),
			Width: payload.Width, Height: payload.Height, DurationMs: payload.DurationMs,
			LikeCount: payload.LikeCount, CommentCount: payload.CommentCount, ShareCount: payload.ShareCount,
			ContentVertical: strings.TrimSpace(payload.ContentVertical),
			CreatedAt:       createdAt, UpdatedAt: updatedAt, PublishedAt: publishedAt,
		}
	}
	return event, nil
}

func postLifecycleCarriesFeedSnapshot(eventType string) bool {
	switch strings.TrimSpace(eventType) {
	case "PostPublished", "PostUpdated", "PostSettingsUpdated", "PostPromotedToWork":
		return true
	default:
		return false
	}
}

func parsePostLifecycleSnapshotTime(raw, field string) (time.Time, error) {
	parsed, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(raw))
	if err != nil || parsed.IsZero() {
		return time.Time{}, fmt.Errorf("Content Post feed snapshot %s is invalid", field)
	}
	return parsed.UTC(), nil
}

func compactPostMediaURLs(
	direct []string,
	items []struct {
		URL string `json:"url"`
	},
) []string {
	seen := make(map[string]struct{}, len(direct)+len(items))
	result := make([]string, 0, len(direct)+len(items))
	appendURL := func(raw string) {
		value := strings.TrimSpace(raw)
		if value == "" {
			return
		}
		if _, exists := seen[value]; exists {
			return
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	for _, value := range direct {
		appendURL(value)
	}
	for _, item := range items {
		appendURL(item.URL)
	}
	return result
}

func uniqueStreamMessages(groups ...[]runtimemessaging.StreamDelivery) []runtimemessaging.StreamDelivery {
	seen := make(map[string]struct{})
	result := make([]runtimemessaging.StreamDelivery, 0)
	for _, messages := range groups {
		for _, message := range messages {
			if _, exists := seen[message.ID]; exists {
				continue
			}
			seen[message.ID] = struct{}{}
			result = append(result, message)
		}
	}
	return result
}

func postLifecycleDLQFields(
	message runtimemessaging.StreamDelivery,
	cause error,
	attempts int64,
) []runtimemessaging.DurableField {
	values := map[string]string{
		"sourceStream": ContentPostLifecycleStream, "streamId": message.ID,
		"error": cause.Error(), "attempts": strconv.FormatInt(attempts, 10),
		"deadLetteredAt": time.Now().UTC().Format(time.RFC3339Nano),
	}
	for key, value := range runtimemessaging.DurableFieldMap(message.Fields) {
		if key == "sourceId" || key == "reason" {
			continue
		}
		values[key] = value
	}
	return runtimemessaging.DurableFieldsFromMap(values)
}

func (consumer *ContentPostConsumer) recordSuccess() {
	consumer.mu.Lock()
	defer consumer.mu.Unlock()
	consumer.lastSuccess = time.Now().UTC()
	consumer.lastFailure = nil
}

func (consumer *ContentPostConsumer) recordFailure(err error) {
	consumer.mu.Lock()
	defer consumer.mu.Unlock()
	consumer.lastFailure = err
}
