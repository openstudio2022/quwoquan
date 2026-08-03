package persistence

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"

	mediaprocessing "quwoquan_service/services/content-service/internal/media/media_asset/application/processing"
)

type mediaProcessingDeadLetterDocument struct {
	ID            string    `bson:"_id"`
	Consumer      string    `bson:"consumer"`
	EventID       string    `bson:"eventId"`
	EventType     string    `bson:"eventType"`
	AggregateType string    `bson:"aggregateType"`
	AggregateID   string    `bson:"aggregateId"`
	Checkpoint    string    `bson:"checkpoint"`
	OccurredAt    time.Time `bson:"occurredAt"`
	Reason        string    `bson:"reason"`
	QuarantinedAt time.Time `bson:"quarantinedAt"`
}

// QuarantineMediaProcessingEvent commits only immutable event identity and a
// stable reason. It must succeed before Worker advances the shared checkpoint;
// duplicate delivery is an idempotent success rather than a second dead letter.
func (s *MongoMediaStore) QuarantineMediaProcessingEvent(
	ctx context.Context,
	event mediaprocessing.PoisonEvent,
) error {
	if s == nil || s.processingDeadLetters == nil {
		return fmt.Errorf("media processing dead-letter store is not configured")
	}
	consumer := strings.TrimSpace(event.Consumer)
	eventID := strings.TrimSpace(event.EventID)
	checkpoint := strings.TrimSpace(event.Checkpoint)
	reason := strings.TrimSpace(event.Reason)
	if consumer == "" || eventID == "" || checkpoint == "" || reason == "" ||
		event.OccurredAt.IsZero() || event.QuarantinedAt.IsZero() {
		return fmt.Errorf("media processing dead-letter requires durable event identity")
	}
	document := mediaProcessingDeadLetterDocument{
		ID:            consumer + ":" + eventID,
		Consumer:      consumer,
		EventID:       eventID,
		EventType:     strings.TrimSpace(event.EventType),
		AggregateType: strings.TrimSpace(event.AggregateType),
		AggregateID:   strings.TrimSpace(event.AggregateID),
		Checkpoint:    checkpoint,
		OccurredAt:    event.OccurredAt.UTC(),
		Reason:        reason,
		QuarantinedAt: event.QuarantinedAt.UTC(),
	}
	if _, err := s.processingDeadLetters.InsertOne(ctx, document); err != nil {
		if mongo.IsDuplicateKeyError(err) {
			return nil
		}
		return fmt.Errorf("insert media processing dead letter: %w", err)
	}
	return nil
}

var _ mediaprocessing.PoisonEventRecorder = (*MongoMediaStore)(nil)
