package persistence

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/ports"
)

const (
	templateCollection = "trip_plan_templates"
	receiptCollection  = "trip_plan_template_command_receipts"
	outboxCollection   = "trip_plan_template_outbox"
	sequenceCollection = "trip_plan_template_outbox_sequences"
)

type MongoStore struct{ templates, receipts, outbox, sequences *mongo.Collection }

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		panic("TripPlanTemplate MongoStore requires database")
	}
	return &MongoStore{
		templates: database.Collection(templateCollection), receipts: database.Collection(receiptCollection),
		outbox: database.Collection(outboxCollection), sequences: database.Collection(sequenceCollection),
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.templates.Indexes().CreateOne(ctx, mongo.IndexModel{Keys: bson.D{{Key: "ownerPersonaId", Value: 1}, {Key: "updatedAt", Value: -1}}, Options: options.Index().SetName("idx_trip_plan_template_owner_updated")}); err != nil {
		return err
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{Keys: bson.D{{Key: "expiresAt", Value: 1}}, Options: options.Index().SetName("ttl_trip_plan_template_receipts").SetExpireAfterSeconds(0)}); err != nil {
		return err
	}
	_, err := store.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "publishedAt", Value: 1}, {Key: "leaseExpiresAt", Value: 1}, {Key: "outboxSequence", Value: 1}}, Options: options.Index().SetName("idx_trip_plan_template_outbox_pending")},
		{Keys: bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}}, Options: options.Index().SetName("uq_trip_plan_template_outbox_version").SetUnique(true)},
		{Keys: bson.D{{Key: "outboxSequence", Value: 1}}, Options: options.Index().SetName("uq_trip_plan_template_outbox_sequence").SetUnique(true)},
	})
	return err
}

func (store *MongoStore) Get(ctx context.Context, templateID string) (model.Template, error) {
	var value model.Template
	err := store.templates.FindOne(ctx, bson.M{"_id": strings.TrimSpace(templateID)}).Decode(&value)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Template{}, ports.ErrNotFound
	}
	return value, err
}

func (store *MongoStore) ListByOwner(ctx context.Context, ownerPersonaID string) ([]model.Template, error) {
	cursor, err := store.templates.Find(ctx, bson.M{"ownerPersonaId": strings.TrimSpace(ownerPersonaID)}, options.Find().SetSort(bson.D{{Key: "updatedAt", Value: -1}}))
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var values []model.Template
	if err := cursor.All(ctx, &values); err != nil {
		return nil, err
	}
	if values == nil {
		values = []model.Template{}
	}
	return values, nil
}

type receiptDocument struct {
	ID            string         `bson:"_id"`
	CommandDigest string         `bson:"commandDigest"`
	Template      model.Template `bson:"template"`
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
	return ports.Receipt{IdempotencyKey: document.ID, CommandDigest: document.CommandDigest, Result: ports.CommandResult{Template: document.Template}, ExpiresAt: document.ExpiresAt}, true, nil
}

func (store *MongoStore) Commit(ctx context.Context, commit ports.Commit) error {
	if commit.Template.Validate() != nil || commit.Event.EventType != "TripPlanTemplateChanged" || commit.Event.AggregateID != commit.Template.TemplateID || commit.Event.AggregateVersion != commit.Template.Version || strings.TrimSpace(commit.Receipt.IdempotencyKey) == "" || strings.TrimSpace(commit.Receipt.CommandDigest) == "" || commit.Receipt.ExpiresAt.IsZero() {
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
	session, err := store.templates.Database().Client().StartSession()
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
		if err := store.persistTemplate(txCtx, commit); err != nil {
			return nil, err
		}
		if err := store.appendOutbox(txCtx, commit); err != nil {
			return nil, err
		}
		_, insertErr := store.receipts.InsertOne(txCtx, receiptDocument{ID: commit.Receipt.IdempotencyKey, CommandDigest: commit.Receipt.CommandDigest, Template: commit.Template, ExpiresAt: commit.Receipt.ExpiresAt.UTC()})
		if mongo.IsDuplicateKeyError(insertErr) {
			return nil, ports.ErrIdempotencyConflict
		}
		return nil, insertErr
	})
	return err
}

func (store *MongoStore) persistTemplate(ctx context.Context, commit ports.Commit) error {
	if commit.ExpectedVersion == 0 {
		if _, err := store.templates.InsertOne(ctx, commit.Template); err != nil {
			if mongo.IsDuplicateKeyError(err) {
				return ports.ErrCommitConflict
			}
			return err
		}
		return nil
	}
	result, err := store.templates.ReplaceOne(ctx, bson.M{"_id": commit.Template.TemplateID, "version": commit.ExpectedVersion}, commit.Template)
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
	if err := store.sequences.FindOneAndUpdate(ctx, bson.M{"_id": "TripPlanTemplate"}, bson.M{"$inc": bson.M{"value": int64(1)}}, options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After)).Decode(&sequence); err != nil {
		return err
	}
	_, err := store.outbox.InsertOne(ctx, bson.M{"_id": commit.Event.EventID, "outboxSequence": sequence.Value, "eventType": commit.Event.EventType, "aggregateId": commit.Event.AggregateID, "aggregateVersion": commit.Event.AggregateVersion, "payloadJson": commit.Event.Payload, "occurredAt": commit.Event.OccurredAt.UTC(), "publishAttempts": 0})
	if mongo.IsDuplicateKeyError(err) {
		return ports.ErrCommitConflict
	}
	return err
}

var _ ports.Store = (*MongoStore)(nil)
