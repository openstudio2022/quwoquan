package persistence

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/domain/ports"
)

const (
	assignmentCollection = "trip_guide_assignments"
	receiptCollection    = "trip_guide_assignment_command_receipts"
	outboxCollection     = "trip_guide_assignment_outbox"
	sequenceCollection   = "trip_guide_assignment_outbox_sequences"
)

type MongoStore struct{ assignments, receipts, outbox, sequences *mongo.Collection }

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		panic("TripGuideAssignment MongoStore requires database")
	}
	return &MongoStore{assignments: database.Collection(assignmentCollection), receipts: database.Collection(receiptCollection), outbox: database.Collection(outboxCollection), sequences: database.Collection(sequenceCollection)}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.assignments.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "tripId", Value: 1}, {Key: "taskKey", Value: 1}}, Options: options.Index().SetName("uq_trip_guide_assignment_task").SetUnique(true)},
		{Keys: bson.D{{Key: "assigneePersonaId", Value: 1}, {Key: "status", Value: 1}, {Key: "updatedAt", Value: -1}}, Options: options.Index().SetName("idx_trip_guide_assignment_assignee_status")},
	}); err != nil {
		return err
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{Keys: bson.D{{Key: "expiresAt", Value: 1}}, Options: options.Index().SetName("ttl_trip_guide_assignment_receipts").SetExpireAfterSeconds(0)}); err != nil {
		return err
	}
	_, err := store.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "publishedAt", Value: 1}, {Key: "leaseExpiresAt", Value: 1}, {Key: "outboxSequence", Value: 1}}, Options: options.Index().SetName("idx_trip_guide_assignment_outbox_pending")},
		{Keys: bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}}, Options: options.Index().SetName("uq_trip_guide_assignment_outbox_version").SetUnique(true)},
		{Keys: bson.D{{Key: "outboxSequence", Value: 1}}, Options: options.Index().SetName("uq_trip_guide_assignment_outbox_sequence").SetUnique(true)},
	})
	return err
}

func assignmentFilter(tripID, taskKey string) bson.M {
	return bson.M{"tripId": strings.TrimSpace(tripID), "taskKey": strings.TrimSpace(taskKey)}
}
func (store *MongoStore) Get(ctx context.Context, tripID, taskKey string) (model.Assignment, error) {
	var value model.Assignment
	err := store.assignments.FindOne(ctx, assignmentFilter(tripID, taskKey)).Decode(&value)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Assignment{}, ports.ErrNotFound
	}
	return value, err
}
func (store *MongoStore) ListByTrip(ctx context.Context, tripID string) ([]model.Assignment, error) {
	cursor, err := store.assignments.Find(ctx, bson.M{"tripId": strings.TrimSpace(tripID)}, options.Find().SetSort(bson.D{{Key: "dueAt", Value: 1}, {Key: "taskKey", Value: 1}}))
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var values []model.Assignment
	if err := cursor.All(ctx, &values); err != nil {
		return nil, err
	}
	if values == nil {
		values = []model.Assignment{}
	}
	return values, nil
}

type receiptDocument struct {
	ID            string           `bson:"_id"`
	CommandDigest string           `bson:"commandDigest"`
	Assignment    model.Assignment `bson:"assignment"`
	ExpiresAt     time.Time        `bson:"expiresAt"`
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
	return ports.Receipt{IdempotencyKey: document.ID, CommandDigest: document.CommandDigest, Result: ports.CommandResult{Assignment: document.Assignment}, ExpiresAt: document.ExpiresAt}, true, nil
}

func (store *MongoStore) Commit(ctx context.Context, commit ports.Commit) error {
	if commit.Assignment.Validate() != nil || commit.Event.EventType != "TripGuideAssignmentChanged" || commit.Event.AggregateID != commit.Assignment.AssignmentID || commit.Event.AggregateVersion != commit.Assignment.Version || strings.TrimSpace(commit.Receipt.IdempotencyKey) == "" || strings.TrimSpace(commit.Receipt.CommandDigest) == "" || commit.Receipt.ExpiresAt.IsZero() {
		return model.ErrInvalidArgument
	}
	if receipt, found, err := store.FindReceipt(ctx, commit.Receipt.IdempotencyKey); err != nil {
		return err
	} else if found {
		if receipt.CommandDigest != commit.Receipt.CommandDigest {
			return ports.ErrIdempotencyConflict
		}
		return nil
	}
	session, err := store.assignments.Database().Client().StartSession()
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
		if err := store.persistAssignment(txCtx, commit); err != nil {
			return nil, err
		}
		if err := store.appendOutbox(txCtx, commit); err != nil {
			return nil, err
		}
		_, insertErr := store.receipts.InsertOne(txCtx, receiptDocument{ID: commit.Receipt.IdempotencyKey, CommandDigest: commit.Receipt.CommandDigest, Assignment: commit.Assignment, ExpiresAt: commit.Receipt.ExpiresAt.UTC()})
		if mongo.IsDuplicateKeyError(insertErr) {
			return nil, ports.ErrIdempotencyConflict
		}
		return nil, insertErr
	})
	return err
}
func (store *MongoStore) persistAssignment(ctx context.Context, commit ports.Commit) error {
	if commit.ExpectedVersion == 0 {
		if _, err := store.assignments.InsertOne(ctx, commit.Assignment); err != nil {
			if mongo.IsDuplicateKeyError(err) {
				return ports.ErrCommitConflict
			}
			return err
		}
		return nil
	}
	result, err := store.assignments.ReplaceOne(ctx, bson.M{"_id": commit.Assignment.AssignmentID, "version": commit.ExpectedVersion}, commit.Assignment)
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
	if err := store.sequences.FindOneAndUpdate(ctx, bson.M{"_id": "TripGuideAssignment"}, bson.M{"$inc": bson.M{"value": int64(1)}}, options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After)).Decode(&sequence); err != nil {
		return err
	}
	_, err := store.outbox.InsertOne(ctx, bson.M{"_id": commit.Event.EventID, "outboxSequence": sequence.Value, "eventType": commit.Event.EventType, "aggregateId": commit.Event.AggregateID, "aggregateVersion": commit.Event.AggregateVersion, "payloadJson": commit.Event.Payload, "occurredAt": commit.Event.OccurredAt.UTC(), "publishAttempts": 0})
	if mongo.IsDuplicateKeyError(err) {
		return ports.ErrCommitConflict
	}
	return err
}

var _ ports.Store = (*MongoStore)(nil)
