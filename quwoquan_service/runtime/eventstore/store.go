package eventstore

import (
	"context"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

var (
	eventstoreAppendTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "eventstore",
		Name:      "append_total",
		Help:      "Total events appended by aggregate_type and status.",
	}, []string{"aggregate_type", "status"})

	eventstorePublishFailures = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "eventstore",
		Name:      "publish_failures_total",
		Help:      "Total publisher failures by aggregate_type.",
	}, []string{"aggregate_type"})
)

// StoredEvent is the persistent representation of a domain event.
type StoredEvent struct {
	ID            string         `bson:"_id"            json:"id"`
	Type          string         `bson:"type"           json:"type"`
	AggregateType string         `bson:"aggregateType"  json:"aggregateType"`
	AggregateID   string         `bson:"aggregateId"    json:"aggregateId"`
	Version       int64          `bson:"version"        json:"version"`
	Payload       map[string]any `bson:"payload"        json:"payload"`
	Metadata      EventMeta      `bson:"metadata"       json:"metadata"`
	OccurredAt    time.Time      `bson:"occurredAt"     json:"occurredAt"`
	StoredAt      time.Time      `bson:"storedAt"       json:"storedAt"`
}

type EventMeta struct {
	TraceID     string `bson:"traceId"     json:"traceId"`
	RequestID   string `bson:"requestId"   json:"requestId"`
	UserID      string `bson:"userId"      json:"userId"`
	Producer    string `bson:"producer"    json:"producer"`
	CausationID string `bson:"causationId" json:"causationId,omitempty"`
}

// Store persists domain events to MongoDB and optionally publishes them.
type Store struct {
	coll       *mongo.Collection
	publishers []Publisher
}

// Publisher defines a downstream event sink (e.g., MQ, Projector bus).
type Publisher interface {
	Publish(ctx context.Context, event StoredEvent) error
}

// PublisherFunc adapts a function to the Publisher interface.
type PublisherFunc func(ctx context.Context, event StoredEvent) error

func (f PublisherFunc) Publish(ctx context.Context, event StoredEvent) error {
	return f(ctx, event)
}

// Option configures the Store.
type Option func(*Store)

func WithPublisher(p Publisher) Option {
	return func(s *Store) { s.publishers = append(s.publishers, p) }
}

// NewStore creates an EventStore backed by MongoDB.
func NewStore(db *mongo.Database, opts ...Option) (*Store, error) {
	coll := db.Collection("domain_events")

	s := &Store{coll: coll}
	for _, o := range opts {
		o(s)
	}

	if err := s.ensureIndexes(context.Background()); err != nil {
		return nil, err
	}

	return s, nil
}

func (s *Store) ensureIndexes(ctx context.Context) error {
	indexes := []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "aggregateType", Value: 1},
				{Key: "aggregateId", Value: 1},
				{Key: "version", Value: 1},
			},
			Options: options.Index().SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "type", Value: 1},
				{Key: "occurredAt", Value: -1},
			},
		},
		{
			Keys: bson.D{
				{Key: "metadata.traceId", Value: 1},
			},
		},
	}

	_, err := s.coll.Indexes().CreateMany(ctx, indexes)
	return err
}

// Append persists an event and publishes it to all registered publishers.
func (s *Store) Append(ctx context.Context, event StoredEvent) error {
	if event.StoredAt.IsZero() {
		event.StoredAt = time.Now().UTC()
	}

	_, err := s.coll.InsertOne(ctx, event)
	if err != nil {
		eventstoreAppendTotal.WithLabelValues(event.AggregateType, "error").Inc()
		return err
	}
	eventstoreAppendTotal.WithLabelValues(event.AggregateType, "ok").Inc()

	for _, p := range s.publishers {
		if pubErr := p.Publish(ctx, event); pubErr != nil {
			eventstorePublishFailures.WithLabelValues(event.AggregateType).Inc()
			_ = pubErr
		}
	}

	return nil
}

// AppendBatch persists multiple events atomically.
func (s *Store) AppendBatch(ctx context.Context, events []StoredEvent) error {
	if len(events) == 0 {
		return nil
	}

	docs := make([]any, len(events))
	now := time.Now().UTC()
	for i := range events {
		if events[i].StoredAt.IsZero() {
			events[i].StoredAt = now
		}
		docs[i] = events[i]
	}

	_, err := s.coll.InsertMany(ctx, docs)
	if err != nil {
		for _, ev := range events {
			eventstoreAppendTotal.WithLabelValues(ev.AggregateType, "error").Inc()
		}
		return err
	}
	for _, ev := range events {
		eventstoreAppendTotal.WithLabelValues(ev.AggregateType, "ok").Inc()
	}

	for _, event := range events {
		for _, p := range s.publishers {
			if pubErr := p.Publish(ctx, event); pubErr != nil {
				eventstorePublishFailures.WithLabelValues(event.AggregateType).Inc()
				_ = pubErr
			}
		}
	}

	return nil
}

// LoadEvents returns events for a specific aggregate, ordered by version.
func (s *Store) LoadEvents(ctx context.Context, aggregateType, aggregateID string) ([]StoredEvent, error) {
	filter := bson.M{
		"aggregateType": aggregateType,
		"aggregateId":   aggregateID,
	}
	opts := options.Find().SetSort(bson.D{{Key: "version", Value: 1}})

	cursor, err := s.coll.Find(ctx, filter, opts)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	var events []StoredEvent
	if err := cursor.All(ctx, &events); err != nil {
		return nil, err
	}
	return events, nil
}

// LoadEventsByType returns events of a specific type since a timestamp.
func (s *Store) LoadEventsByType(ctx context.Context, eventType string, since time.Time, limit int64) ([]StoredEvent, error) {
	filter := bson.M{
		"type":       eventType,
		"occurredAt": bson.M{"$gte": since},
	}
	opts := options.Find().
		SetSort(bson.D{{Key: "occurredAt", Value: 1}}).
		SetLimit(limit)

	cursor, err := s.coll.Find(ctx, filter, opts)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	var events []StoredEvent
	if err := cursor.All(ctx, &events); err != nil {
		return nil, err
	}
	return events, nil
}

// LatestVersion returns the highest version number for an aggregate.
func (s *Store) LatestVersion(ctx context.Context, aggregateType, aggregateID string) (int64, error) {
	filter := bson.M{
		"aggregateType": aggregateType,
		"aggregateId":   aggregateID,
	}
	opts := options.FindOne().SetSort(bson.D{{Key: "version", Value: -1}})

	var event StoredEvent
	err := s.coll.FindOne(ctx, filter, opts).Decode(&event)
	if err == mongo.ErrNoDocuments {
		return 0, nil
	}
	if err != nil {
		return 0, err
	}
	return event.Version, nil
}
