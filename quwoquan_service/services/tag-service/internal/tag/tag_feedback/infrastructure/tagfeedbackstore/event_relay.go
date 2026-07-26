package tagfeedbackstore

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	feedbackmodel "quwoquan_service/services/tag-service/internal/tag/tag_feedback/domain/tagfeedback/model"
)

const (
	feedbackEventRelayPollInterval = 500 * time.Millisecond
	feedbackEventRelayMaxBackoff   = 30 * time.Second
)

// EventRelay publishes committed feedback facts and acknowledges them only
// after the durable stream append succeeds. A crash between publish and
// acknowledgement replays the same event ID and is intentionally at-least-once.
type EventRelay struct {
	sink      *Sink
	publisher FeedbackEventPublisher
	logger    *slog.Logger

	healthMu sync.RWMutex
	lastScan time.Time
	lastErr  error
}

func NewEventRelay(
	sink *Sink,
	publisher FeedbackEventPublisher,
	logger *slog.Logger,
) (*EventRelay, error) {
	if sink == nil || sink.feedback == nil || publisher == nil {
		return nil, fmt.Errorf(
			"tag feedback event relay requires sink and publisher",
		)
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &EventRelay{
		sink:      sink,
		publisher: publisher,
		logger:    logger,
	}, nil
}

// ProcessOnce publishes at most one pending TagFeedbackRecorded event.
func (relay *EventRelay) ProcessOnce(ctx context.Context) (bool, error) {
	if relay == nil ||
		relay.sink == nil ||
		relay.sink.feedback == nil ||
		relay.publisher == nil {
		return false, fmt.Errorf("tag feedback event relay is not configured")
	}

	var feedback feedbackmodel.Feedback
	err := relay.sink.feedback.FindOne(
		ctx,
		bson.M{"eventPublishedAt": bson.M{"$exists": false}},
		options.FindOne().SetSort(bson.D{
			{Key: "recordedAt", Value: 1},
			{Key: "_id", Value: 1},
		}),
	).Decode(&feedback)
	if errors.Is(err, mongo.ErrNoDocuments) {
		relay.recordSuccess()
		return false, nil
	}
	if err != nil {
		relay.recordFailure(err)
		return false, fmt.Errorf("load pending tag feedback event: %w", err)
	}

	if err := relay.publisher.PublishTagFeedbackRecorded(
		ctx,
		feedback,
	); err != nil {
		relay.recordFailure(err)
		return true, err
	}

	publishedAt := time.Now().UTC()
	result, err := relay.sink.feedback.UpdateOne(
		ctx,
		bson.M{
			"_id":              feedback.ID,
			"eventPublishedAt": bson.M{"$exists": false},
		},
		bson.M{"$set": bson.M{"eventPublishedAt": publishedAt}},
	)
	if err != nil {
		relay.recordFailure(err)
		return true, fmt.Errorf(
			"acknowledge tag feedback event publication: %w",
			err,
		)
	}
	if result.MatchedCount == 0 {
		alreadyPublished, findErr := relay.sink.feedback.CountDocuments(
			ctx,
			bson.M{
				"_id":              feedback.ID,
				"eventPublishedAt": bson.M{"$exists": true},
			},
		)
		if findErr != nil {
			relay.recordFailure(findErr)
			return true, fmt.Errorf(
				"verify tag feedback event acknowledgement: %w",
				findErr,
			)
		}
		if alreadyPublished != 1 {
			err = fmt.Errorf(
				"tag feedback event acknowledgement target is missing",
			)
			relay.recordFailure(err)
			return true, err
		}
	}

	relay.recordSuccess()
	return true, nil
}

func (relay *EventRelay) Run(ctx context.Context) {
	retryDelay := feedbackEventRelayPollInterval
	for {
		didWork, err := relay.ProcessOnce(ctx)
		if err != nil {
			if ctx.Err() == nil {
				relay.logger.ErrorContext(
					ctx,
					"tag feedback event relay failed",
					slog.String("err", err.Error()),
				)
			}
			if !waitForFeedbackEventRelay(ctx, retryDelay) {
				return
			}
			retryDelay = min(
				retryDelay*2,
				feedbackEventRelayMaxBackoff,
			)
			continue
		}
		retryDelay = feedbackEventRelayPollInterval
		if didWork {
			continue
		}
		if !waitForFeedbackEventRelay(
			ctx,
			feedbackEventRelayPollInterval,
		) {
			return
		}
	}
}

func (relay *EventRelay) Healthy(
	_ context.Context,
	maxStaleness time.Duration,
) error {
	if relay == nil {
		return fmt.Errorf("tag feedback event relay is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	relay.healthMu.RLock()
	lastScan := relay.lastScan
	lastErr := relay.lastErr
	relay.healthMu.RUnlock()
	if lastErr != nil {
		return fmt.Errorf("tag feedback event relay unhealthy: %w", lastErr)
	}
	if lastScan.IsZero() || time.Since(lastScan) > maxStaleness {
		return fmt.Errorf("tag feedback event relay heartbeat is stale")
	}
	return nil
}

func (relay *EventRelay) recordSuccess() {
	relay.healthMu.Lock()
	relay.lastScan = time.Now().UTC()
	relay.lastErr = nil
	relay.healthMu.Unlock()
}

func (relay *EventRelay) recordFailure(err error) {
	relay.healthMu.Lock()
	relay.lastScan = time.Now().UTC()
	relay.lastErr = err
	relay.healthMu.Unlock()
}

func waitForFeedbackEventRelay(
	ctx context.Context,
	delay time.Duration,
) bool {
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-timer.C:
		return true
	}
}
