package persistence

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/ports"
)

const (
	momentCollection   = "trip_moments"
	receiptCollection  = "trip_moment_command_receipts"
	outboxCollection   = "trip_moment_outbox"
	sequenceCollection = "trip_moment_outbox_sequences"
)

type MongoStore struct {
	moments   *mongo.Collection
	receipts  *mongo.Collection
	outbox    *mongo.Collection
	sequences *mongo.Collection
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		panic("TripMoment MongoStore requires database")
	}
	return &MongoStore{
		moments: database.Collection(momentCollection), receipts: database.Collection(receiptCollection),
		outbox: database.Collection(outboxCollection), sequences: database.Collection(sequenceCollection),
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.moments.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "tripId", Value: 1}, {Key: "status", Value: 1},
				{Key: "capturedAt", Value: 1}, {Key: "_id", Value: 1},
			},
			Options: options.Index().SetName("idx_trip_moment_timeline"),
		},
		{
			Keys: bson.D{
				{Key: "tripId", Value: 1}, {Key: "revisionNumber", Value: 1},
				{Key: "itemId", Value: 1}, {Key: "status", Value: 1},
			},
			Options: options.Index().SetName("idx_trip_moment_item"),
		},
	}); err != nil {
		return err
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "expiresAt", Value: 1}},
		Options: options.Index().SetName("ttl_trip_moment_command_receipts").SetExpireAfterSeconds(0),
	}); err != nil {
		return err
	}
	_, err := store.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "publishedAt", Value: 1}, {Key: "leaseExpiresAt", Value: 1}, {Key: "outboxSequence", Value: 1}},
			Options: options.Index().SetName("idx_trip_moment_outbox_pending"),
		},
		{
			Keys:    bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}},
			Options: options.Index().SetName("uq_trip_moment_outbox_version").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "outboxSequence", Value: 1}},
			Options: options.Index().SetName("uq_trip_moment_outbox_sequence").SetUnique(true),
		},
	})
	return err
}

func (store *MongoStore) Get(ctx context.Context, tripID, momentID string) (model.Moment, error) {
	var moment model.Moment
	err := store.moments.FindOne(ctx, bson.M{
		"_id": strings.TrimSpace(momentID), "tripId": strings.TrimSpace(tripID),
	}).Decode(&moment)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Moment{}, ports.ErrNotFound
	}
	return moment, err
}

func (store *MongoStore) ListActive(ctx context.Context, tripID string) ([]model.Moment, error) {
	cursor, err := store.moments.Find(
		ctx,
		bson.M{"tripId": strings.TrimSpace(tripID), "status": model.StatusActive},
		options.Find().SetSort(bson.D{{Key: "capturedAt", Value: 1}, {Key: "_id", Value: 1}}),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var moments []model.Moment
	if err := cursor.All(ctx, &moments); err != nil {
		return nil, err
	}
	if moments == nil {
		moments = []model.Moment{}
	}
	return moments, nil
}

type receiptDocument struct {
	ID            string       `bson:"_id"`
	CommandDigest string       `bson:"commandDigest"`
	Moment        model.Moment `bson:"moment"`
	ExpiresAt     time.Time    `bson:"expiresAt"`
}

func (document receiptDocument) receipt() ports.Receipt {
	return ports.Receipt{
		IdempotencyKey: document.ID, CommandDigest: document.CommandDigest,
		Result: ports.CommandResult{Moment: document.Moment}, ExpiresAt: document.ExpiresAt,
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
	session, err := store.moments.Database().Client().StartSession()
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
		if err := store.persistMoment(txCtx, commit); err != nil {
			return nil, err
		}
		if err := store.appendOutbox(txCtx, commit); err != nil {
			return nil, err
		}
		_, insertErr := store.receipts.InsertOne(txCtx, receiptDocument{
			ID: commit.Receipt.IdempotencyKey, CommandDigest: commit.Receipt.CommandDigest,
			Moment: commit.Receipt.Result.Moment, ExpiresAt: commit.Receipt.ExpiresAt.UTC(),
		})
		if mongo.IsDuplicateKeyError(insertErr) {
			return nil, ports.ErrIdempotencyConflict
		}
		return nil, insertErr
	})
	return err
}

func (store *MongoStore) persistMoment(ctx context.Context, commit ports.Commit) error {
	if commit.ExpectedVersion == 0 {
		if _, err := store.moments.InsertOne(ctx, commit.Moment); err != nil {
			if mongo.IsDuplicateKeyError(err) {
				return ports.ErrCommitConflict
			}
			return err
		}
		return nil
	}
	result, err := store.moments.ReplaceOne(ctx, bson.M{
		"_id": commit.Moment.MomentID, "version": commit.ExpectedVersion,
	}, commit.Moment)
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
		bson.M{"_id": "TripMoment"},
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

func validateCommit(commit ports.Commit) error {
	if commit.Moment.Validate() != nil || strings.TrimSpace(commit.Receipt.IdempotencyKey) == "" ||
		strings.TrimSpace(commit.Receipt.CommandDigest) == "" || commit.Receipt.ExpiresAt.IsZero() ||
		strings.TrimSpace(commit.Event.EventID) == "" || commit.Event.EventType != "TripMomentChanged" ||
		commit.Event.AggregateID != commit.Moment.MomentID ||
		commit.Event.AggregateVersion != commit.Moment.Version || commit.Event.OccurredAt.IsZero() {
		return model.ErrInvalidArgument
	}
	return nil
}

var _ ports.Store = (*MongoStore)(nil)
