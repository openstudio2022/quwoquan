package eventing

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	domaineventing "quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/eventing"
)

type outboxSource struct {
	name       string
	collection *mongo.Collection
}

type MongoOutboxStore struct {
	sources []outboxSource
}

func NewMongoOutboxStore(database *mongo.Database) *MongoOutboxStore {
	if database == nil {
		panic("Travel MongoOutboxStore requires database")
	}
	return &MongoOutboxStore{sources: []outboxSource{
		{name: "TripPlan", collection: database.Collection("trip_plan_outbox")},
		{name: "TripMembership", collection: database.Collection("trip_membership_outbox")},
		{name: "TripPlanPlacement", collection: database.Collection("trip_plan_placement_outbox")},
		{name: "TripMoment", collection: database.Collection("trip_moment_outbox")},
		{name: "TripPlanContentLink", collection: database.Collection("trip_plan_content_link_outbox")},
		{name: "TripShareSnapshot", collection: database.Collection("trip_share_snapshot_outbox")},
		{name: "TripPlanTemplate", collection: database.Collection("trip_plan_template_outbox")},
		{name: "TripGuideAssignment", collection: database.Collection("trip_guide_assignment_outbox")},
	}}
}

type outboxDocument struct {
	ID               string         `bson:"_id"`
	EventType        string         `bson:"eventType"`
	AggregateID      string         `bson:"aggregateId"`
	AggregateVersion int64          `bson:"aggregateVersion"`
	Payload          map[string]any `bson:"payloadJson"`
	OccurredAt       time.Time      `bson:"occurredAt"`
	ClaimedBy        string         `bson:"claimedBy"`
}

func (store *MongoOutboxStore) ClaimPending(
	ctx context.Context,
	workerID string,
	now time.Time,
	lease time.Duration,
	limit int,
) ([]domaineventing.ClaimedEvent, error) {
	workerID = strings.TrimSpace(workerID)
	if store == nil || len(store.sources) == 0 || workerID == "" || now.IsZero() || lease <= 0 {
		return nil, domaineventing.ErrInvalidEvent
	}
	if limit <= 0 || limit > 200 {
		limit = 100
	}
	claimed := make([]domaineventing.ClaimedEvent, 0, limit)
	for len(claimed) < limit {
		claimedThisRound := false
		for _, source := range store.sources {
			if len(claimed) >= limit {
				break
			}
			event, found, err := claimOne(ctx, source, workerID, now.UTC(), lease)
			if err != nil {
				_ = store.ReleaseClaims(ctx, workerID, claimed)
				return nil, err
			}
			if found {
				claimed = append(claimed, event)
				claimedThisRound = true
			}
		}
		if !claimedThisRound {
			break
		}
	}
	return claimed, nil
}

func claimOne(
	ctx context.Context,
	source outboxSource,
	workerID string,
	now time.Time,
	lease time.Duration,
) (domaineventing.ClaimedEvent, bool, error) {
	var document outboxDocument
	err := source.collection.FindOneAndUpdate(
		ctx,
		bson.M{
			"publishedAt": bson.M{"$exists": false},
			"$or": []bson.M{
				{"leaseExpiresAt": bson.M{"$exists": false}},
				{"leaseExpiresAt": bson.M{"$lte": now}},
			},
		},
		bson.M{
			"$set": bson.M{"claimedBy": workerID, "leaseExpiresAt": now.Add(lease)},
			"$inc": bson.M{"publishAttempts": 1},
		},
		options.FindOneAndUpdate().
			SetSort(bson.D{{Key: "outboxSequence", Value: 1}}).
			SetReturnDocument(options.After),
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return domaineventing.ClaimedEvent{}, false, nil
	}
	if err != nil {
		return domaineventing.ClaimedEvent{}, false, err
	}
	return domaineventing.ClaimedEvent{Event: domaineventing.Event{
		Source: source.name, EventID: document.ID, EventType: document.EventType,
		AggregateID: document.AggregateID, AggregateVersion: document.AggregateVersion,
		Payload: document.Payload, OccurredAt: document.OccurredAt,
	}, ClaimedBy: document.ClaimedBy}, true, nil
}

func (store *MongoOutboxStore) MarkPublished(
	ctx context.Context,
	event domaineventing.ClaimedEvent,
	workerID string,
	publishedAt time.Time,
) error {
	source, found := store.source(event.Source)
	if !found || strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(workerID) == "" || publishedAt.IsZero() {
		return domaineventing.ErrInvalidEvent
	}
	result, err := source.collection.UpdateOne(
		ctx,
		bson.M{
			"_id":         strings.TrimSpace(event.EventID),
			"claimedBy":   strings.TrimSpace(workerID),
			"publishedAt": bson.M{"$exists": false},
		},
		bson.M{
			"$set":   bson.M{"publishedAt": publishedAt.UTC()},
			"$unset": bson.M{"claimedBy": "", "leaseExpiresAt": ""},
		},
	)
	if err != nil {
		return err
	}
	if result.MatchedCount != 1 {
		return domaineventing.ErrOutboxConflict
	}
	return nil
}

func (store *MongoOutboxStore) ReleaseClaims(
	ctx context.Context,
	workerID string,
	events []domaineventing.ClaimedEvent,
) error {
	workerID = strings.TrimSpace(workerID)
	if len(events) == 0 {
		return nil
	}
	if workerID == "" {
		return domaineventing.ErrInvalidEvent
	}
	bySource := map[string][]string{}
	for _, event := range events {
		bySource[event.Source] = append(bySource[event.Source], event.EventID)
	}
	for sourceName, eventIDs := range bySource {
		source, found := store.source(sourceName)
		if !found {
			return domaineventing.ErrInvalidEvent
		}
		if _, err := source.collection.UpdateMany(
			ctx,
			bson.M{
				"_id": bson.M{"$in": eventIDs}, "claimedBy": workerID,
				"publishedAt": bson.M{"$exists": false},
			},
			bson.M{"$unset": bson.M{"claimedBy": "", "leaseExpiresAt": ""}},
		); err != nil {
			return err
		}
	}
	return nil
}

func (store *MongoOutboxStore) source(name string) (outboxSource, bool) {
	if store == nil {
		return outboxSource{}, false
	}
	name = strings.TrimSpace(name)
	for _, source := range store.sources {
		if source.name == name {
			return source, true
		}
	}
	return outboxSource{}, false
}

var _ domaineventing.OutboxStore = (*MongoOutboxStore)(nil)
