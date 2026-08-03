package persistence

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/domain/ports"
)

const (
	placementCollection = "trip_plan_placements"
	receiptCollection   = "trip_plan_placement_command_receipts"
	outboxCollection    = "trip_plan_placement_outbox"
	sequenceCollection  = "trip_plan_placement_outbox_sequences"
)

type MongoStore struct {
	placements *mongo.Collection
	receipts   *mongo.Collection
	outbox     *mongo.Collection
	sequences  *mongo.Collection
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		panic("TripPlanPlacement MongoStore requires database")
	}
	return &MongoStore{
		placements: database.Collection(placementCollection),
		receipts:   database.Collection(receiptCollection),
		outbox:     database.Collection(outboxCollection),
		sequences:  database.Collection(sequenceCollection),
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.placements.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "tripId", Value: 1}, {Key: "surfaceKind", Value: 1}, {Key: "surfaceId", Value: 1},
			},
			Options: options.Index().SetName("uq_trip_plan_placement_surface").SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "surfaceKind", Value: 1}, {Key: "surfaceId", Value: 1},
				{Key: "status", Value: 1}, {Key: "updatedAt", Value: -1},
			},
			Options: options.Index().SetName("idx_trip_plan_placement_surface_active"),
		},
	}); err != nil {
		return err
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "expiresAt", Value: 1}},
		Options: options.Index().SetName("ttl_trip_plan_placement_command_receipts").SetExpireAfterSeconds(0),
	}); err != nil {
		return err
	}
	_, err := store.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "publishedAt", Value: 1}, {Key: "leaseExpiresAt", Value: 1}, {Key: "outboxSequence", Value: 1}},
			Options: options.Index().SetName("idx_trip_plan_placement_outbox_pending"),
		},
		{
			Keys:    bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}},
			Options: options.Index().SetName("uq_trip_plan_placement_outbox_version").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "outboxSequence", Value: 1}},
			Options: options.Index().SetName("uq_trip_plan_placement_outbox_sequence").SetUnique(true),
		},
	})
	return err
}

func (store *MongoStore) Get(
	ctx context.Context,
	tripID string,
	kind model.SurfaceKind,
	surfaceID string,
) (model.Placement, error) {
	var placement model.Placement
	err := store.placements.FindOne(ctx, placementFilter(tripID, kind, surfaceID)).Decode(&placement)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Placement{}, ports.ErrNotFound
	}
	return placement, err
}

func (store *MongoStore) ListByTrip(ctx context.Context, tripID string) ([]model.Placement, error) {
	return store.list(ctx, bson.M{"tripId": strings.TrimSpace(tripID)})
}

func (store *MongoStore) ListActiveBySurface(
	ctx context.Context,
	kind model.SurfaceKind,
	surfaceID string,
) ([]model.Placement, error) {
	return store.list(ctx, bson.M{
		"surfaceKind": kind, "surfaceId": strings.TrimSpace(surfaceID), "status": model.StatusActive,
	})
}

func (store *MongoStore) list(ctx context.Context, filter bson.M) ([]model.Placement, error) {
	cursor, err := store.placements.Find(
		ctx, filter, options.Find().SetSort(bson.D{{Key: "updatedAt", Value: -1}, {Key: "_id", Value: 1}}),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var placements []model.Placement
	if err := cursor.All(ctx, &placements); err != nil {
		return nil, err
	}
	if placements == nil {
		placements = []model.Placement{}
	}
	return placements, nil
}

type receiptDocument struct {
	ID            string          `bson:"_id"`
	CommandDigest string          `bson:"commandDigest"`
	Placement     model.Placement `bson:"placement"`
	ExpiresAt     time.Time       `bson:"expiresAt"`
}

func (document receiptDocument) receipt() ports.Receipt {
	return ports.Receipt{
		IdempotencyKey: document.ID,
		CommandDigest:  document.CommandDigest,
		Result:         ports.CommandResult{Placement: document.Placement},
		ExpiresAt:      document.ExpiresAt,
	}
}

func (store *MongoStore) FindReceipt(ctx context.Context, key string) (ports.Receipt, bool, error) {
	var document receiptDocument
	err := store.receipts.FindOne(ctx, bson.M{"_id": strings.TrimSpace(key)}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return ports.Receipt{}, false, nil
	}
	if err != nil {
		return ports.Receipt{}, false, err
	}
	return document.receipt(), true, nil
}

func (store *MongoStore) Commit(ctx context.Context, commit ports.Commit) error {
	if err := validateCommit(commit); err != nil {
		return err
	}
	if receipt, found, err := store.FindReceipt(ctx, commit.Receipt.IdempotencyKey); err != nil {
		return err
	} else if found {
		if receipt.CommandDigest != commit.Receipt.CommandDigest {
			return ports.ErrIdempotencyConflict
		}
		return nil
	}
	session, err := store.placements.Database().Client().StartSession()
	if err != nil {
		return err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if receipt, found, findErr := store.FindReceipt(txCtx, commit.Receipt.IdempotencyKey); findErr != nil {
			return nil, findErr
		} else if found {
			if receipt.CommandDigest != commit.Receipt.CommandDigest {
				return nil, ports.ErrIdempotencyConflict
			}
			return nil, nil
		}
		if err := store.persistPlacement(txCtx, commit); err != nil {
			return nil, err
		}
		if err := store.appendOutbox(txCtx, commit); err != nil {
			return nil, err
		}
		_, insertErr := store.receipts.InsertOne(txCtx, receiptDocument{
			ID: commit.Receipt.IdempotencyKey, CommandDigest: commit.Receipt.CommandDigest,
			Placement: commit.Receipt.Result.Placement, ExpiresAt: commit.Receipt.ExpiresAt.UTC(),
		})
		if mongo.IsDuplicateKeyError(insertErr) {
			return nil, ports.ErrIdempotencyConflict
		}
		return nil, insertErr
	})
	return err
}

func (store *MongoStore) persistPlacement(ctx context.Context, commit ports.Commit) error {
	if commit.ExpectedVersion == 0 {
		if _, err := store.placements.InsertOne(ctx, commit.Placement); err != nil {
			if mongo.IsDuplicateKeyError(err) {
				return ports.ErrCommitConflict
			}
			return err
		}
		return nil
	}
	result, err := store.placements.ReplaceOne(ctx, bson.M{
		"_id": commit.Placement.PlacementID, "version": commit.ExpectedVersion,
	}, commit.Placement)
	if err != nil {
		return err
	}
	if result.MatchedCount != 1 {
		return ports.ErrCommitConflict
	}
	return nil
}

func (store *MongoStore) appendOutbox(ctx context.Context, commit ports.Commit) error {
	var sequence struct {
		Value int64 `bson:"value"`
	}
	if err := store.sequences.FindOneAndUpdate(
		ctx,
		bson.M{"_id": "TripPlanPlacement"},
		bson.M{"$inc": bson.M{"value": int64(1)}},
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&sequence); err != nil {
		return err
	}
	_, err := store.outbox.InsertOne(ctx, bson.M{
		"_id": commit.Event.EventID, "outboxSequence": sequence.Value,
		"eventType": commit.Event.EventType, "aggregateId": commit.Event.AggregateID,
		"aggregateVersion": commit.Event.AggregateVersion, "payloadJson": commit.Event.Payload,
		"occurredAt": commit.Event.OccurredAt.UTC(), "publishAttempts": 0,
	})
	if mongo.IsDuplicateKeyError(err) {
		return ports.ErrCommitConflict
	}
	return err
}

func placementFilter(tripID string, kind model.SurfaceKind, surfaceID string) bson.M {
	return bson.M{
		"tripId": strings.TrimSpace(tripID), "surfaceKind": kind, "surfaceId": strings.TrimSpace(surfaceID),
	}
}

func validateCommit(commit ports.Commit) error {
	if commit.Placement.Validate() != nil ||
		strings.TrimSpace(commit.Receipt.IdempotencyKey) == "" ||
		strings.TrimSpace(commit.Receipt.CommandDigest) == "" ||
		commit.Receipt.ExpiresAt.IsZero() ||
		strings.TrimSpace(commit.Event.EventID) == "" ||
		commit.Event.EventType != "TripPlanPlacementChanged" ||
		commit.Event.AggregateID != commit.Placement.PlacementID ||
		commit.Event.AggregateVersion != commit.Placement.Version ||
		commit.Event.OccurredAt.IsZero() {
		return model.ErrInvalidArgument
	}
	return nil
}

var _ ports.Store = (*MongoStore)(nil)
