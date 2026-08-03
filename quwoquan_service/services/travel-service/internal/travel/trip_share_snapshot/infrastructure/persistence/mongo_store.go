package persistence

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/domain/ports"
)

const (
	snapshotCollection = "trip_share_snapshots"
	receiptCollection  = "trip_share_snapshot_command_receipts"
	outboxCollection   = "trip_share_snapshot_outbox"
	sequenceCollection = "trip_share_snapshot_outbox_sequences"
)

type MongoStore struct {
	snapshots *mongo.Collection
	receipts  *mongo.Collection
	outbox    *mongo.Collection
	sequences *mongo.Collection
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		panic("TripShareSnapshot MongoStore requires database")
	}
	return &MongoStore{
		snapshots: database.Collection(snapshotCollection),
		receipts:  database.Collection(receiptCollection), outbox: database.Collection(outboxCollection),
		sequences: database.Collection(sequenceCollection),
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.snapshots.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "tripId", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_trip_share_snapshot_trip_created")},
		{Keys: bson.D{{Key: "tripId", Value: 1}, {Key: "sourceRevisionNumber", Value: 1}, {Key: "sourceDigest", Value: 1}},
			Options: options.Index().SetName("idx_trip_share_snapshot_source")},
	}); err != nil {
		return err
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "expiresAt", Value: 1}},
		Options: options.Index().SetName("ttl_trip_share_snapshot_command_receipts").SetExpireAfterSeconds(0),
	}); err != nil {
		return err
	}
	_, err := store.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "publishedAt", Value: 1}, {Key: "leaseExpiresAt", Value: 1}, {Key: "outboxSequence", Value: 1}},
			Options: options.Index().SetName("idx_trip_share_snapshot_outbox_pending")},
		{Keys: bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}},
			Options: options.Index().SetName("uq_trip_share_snapshot_outbox_version").SetUnique(true)},
		{Keys: bson.D{{Key: "outboxSequence", Value: 1}},
			Options: options.Index().SetName("uq_trip_share_snapshot_outbox_sequence").SetUnique(true)},
	})
	return err
}

func (store *MongoStore) Get(ctx context.Context, snapshotID string) (model.Snapshot, error) {
	var snapshot model.Snapshot
	err := store.snapshots.FindOne(ctx, bson.M{"_id": strings.TrimSpace(snapshotID)}).Decode(&snapshot)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Snapshot{}, ports.ErrNotFound
	}
	return snapshot, err
}

type receiptDocument struct {
	ID            string         `bson:"_id"`
	CommandDigest string         `bson:"commandDigest"`
	Snapshot      model.Snapshot `bson:"snapshot"`
	ExpiresAt     time.Time      `bson:"expiresAt"`
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
	return ports.Receipt{
		IdempotencyKey: document.ID, CommandDigest: document.CommandDigest,
		Result: ports.CommandResult{Snapshot: document.Snapshot}, ExpiresAt: document.ExpiresAt,
	}, true, nil
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
	session, err := store.snapshots.Database().Client().StartSession()
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
		if _, insertErr := store.snapshots.InsertOne(txCtx, commit.Snapshot); insertErr != nil {
			if mongo.IsDuplicateKeyError(insertErr) {
				return nil, ports.ErrCommitConflict
			}
			return nil, insertErr
		}
		if err := store.appendOutbox(txCtx, commit); err != nil {
			return nil, err
		}
		_, insertErr := store.receipts.InsertOne(txCtx, receiptDocument{
			ID: commit.Receipt.IdempotencyKey, CommandDigest: commit.Receipt.CommandDigest,
			Snapshot: commit.Snapshot, ExpiresAt: commit.Receipt.ExpiresAt.UTC(),
		})
		if mongo.IsDuplicateKeyError(insertErr) {
			return nil, ports.ErrIdempotencyConflict
		}
		return nil, insertErr
	})
	return err
}

func (store *MongoStore) appendOutbox(ctx context.Context, commit ports.Commit) error {
	var sequence struct {
		Value int64 `bson:"value"`
	}
	if err := store.sequences.FindOneAndUpdate(
		ctx, bson.M{"_id": "TripShareSnapshot"}, bson.M{"$inc": bson.M{"value": int64(1)}},
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
	if commit.Snapshot.Validate() != nil || strings.TrimSpace(commit.Receipt.IdempotencyKey) == "" ||
		strings.TrimSpace(commit.Receipt.CommandDigest) == "" || commit.Receipt.ExpiresAt.IsZero() ||
		strings.TrimSpace(commit.Event.EventID) == "" || commit.Event.EventType != "TripShareSnapshotCreated" ||
		commit.Event.AggregateID != commit.Snapshot.SnapshotID ||
		commit.Event.AggregateVersion != commit.Snapshot.Version || commit.Event.OccurredAt.IsZero() {
		return model.ErrInvalidArgument
	}
	return nil
}

var _ ports.Store = (*MongoStore)(nil)
