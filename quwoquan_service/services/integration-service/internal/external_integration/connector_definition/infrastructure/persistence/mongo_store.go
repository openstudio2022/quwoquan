package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
)

type MongoStore struct {
	definitions *mongo.Collection
	receipts    *mongo.Collection
	outbox      *mongo.Collection
}

type commandReceipt struct {
	ID             string           `bson:"_id"`
	IdempotencyKey string           `bson:"idempotencyKey"`
	CommandDigest  string           `bson:"commandDigest"`
	Definition     model.Definition `bson:"definition"`
	CreatedAt      time.Time        `bson:"createdAt"`
}

type outboxRecord struct {
	ID            string    `bson:"_id"`
	EventType     string    `bson:"eventType"`
	ConnectorID   string    `bson:"connectorId"`
	ReleaseDigest string    `bson:"releaseDigest"`
	OccurredAt    time.Time `bson:"occurredAt"`
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		return &MongoStore{}
	}
	return &MongoStore{
		definitions: database.Collection("connector_definitions"),
		receipts:    database.Collection("connector_definition_command_receipts"),
		outbox:      database.Collection("connector_definition_outbox"),
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if !store.available() {
		return model.ErrStorageUnavailable
	}
	if _, err := store.definitions.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{{Key: "connectorId", Value: 1}},
			Options: options.Index().SetName("uq_connector_definitions_connector").
				SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "status", Value: 1}, {Key: "publishedAt", Value: -1}},
			Options: options.Index().SetName("idx_connector_definitions_status"),
		},
	}); err != nil {
		return fmt.Errorf("ensure connector definition indexes: %w", err)
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "idempotencyKey", Value: 1}},
		Options: options.Index().SetName("uq_connector_definition_receipt_key").
			SetUnique(true),
	}); err != nil {
		return fmt.Errorf("ensure connector definition receipt index: %w", err)
	}
	return nil
}

func (store *MongoStore) Get(
	ctx context.Context,
	connectorID string,
) (model.Definition, error) {
	if !store.available() {
		return model.Definition{}, model.ErrStorageUnavailable
	}
	var definition model.Definition
	err := store.definitions.FindOne(ctx, bson.M{
		"connectorId": strings.TrimSpace(connectorID),
		"status":      model.StatusActive,
	}).Decode(&definition)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Definition{}, model.ErrNotFound
	}
	if err != nil {
		return model.Definition{}, fmt.Errorf("get connector definition: %w", err)
	}
	return definition, nil
}

func (store *MongoStore) List(
	ctx context.Context,
	capability string,
	limit int,
) ([]model.Definition, error) {
	if !store.available() {
		return nil, model.ErrStorageUnavailable
	}
	filter := bson.M{"status": model.StatusActive}
	if capability = strings.TrimSpace(capability); capability != "" {
		filter["capabilities"] = capability
	}
	cursor, err := store.definitions.Find(
		ctx,
		filter,
		options.Find().SetSort(bson.D{{Key: "connectorId", Value: 1}}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, fmt.Errorf("list connector definitions: %w", err)
	}
	defer cursor.Close(ctx)
	var definitions []model.Definition
	if err := cursor.All(ctx, &definitions); err != nil {
		return nil, fmt.Errorf("decode connector definitions: %w", err)
	}
	return definitions, nil
}

func (store *MongoStore) Publish(
	ctx context.Context,
	command model.PublishCommand,
) (model.MutationResult, error) {
	if !store.available() {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	session, err := store.definitions.Database().Client().StartSession()
	if err != nil {
		return model.MutationResult{}, fmt.Errorf("start connector definition transaction: %w", err)
	}
	defer session.EndSession(ctx)

	result := model.MutationResult{}
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		var receipt commandReceipt
		readErr := store.receipts.FindOne(txCtx, bson.M{
			"idempotencyKey": command.IdempotencyKey,
		}).Decode(&receipt)
		if readErr == nil {
			if receipt.CommandDigest != command.CommandDigest {
				return nil, model.ErrIdempotencyConflict
			}
			result = model.MutationResult{Definition: receipt.Definition, Replayed: true}
			return nil, nil
		}
		if !errors.Is(readErr, mongo.ErrNoDocuments) {
			return nil, readErr
		}
		_, replaceErr := store.definitions.ReplaceOne(
			txCtx,
			bson.M{"connectorId": command.Definition.ConnectorID},
			command.Definition,
			options.Replace().SetUpsert(true),
		)
		if replaceErr != nil {
			return nil, replaceErr
		}
		if _, insertErr := store.receipts.InsertOne(txCtx, commandReceipt{
			ID:             command.IdempotencyKey,
			IdempotencyKey: command.IdempotencyKey,
			CommandDigest:  command.CommandDigest,
			Definition:     command.Definition,
			CreatedAt:      command.Definition.PublishedAt,
		}); insertErr != nil {
			return nil, insertErr
		}
		outboxID := command.Definition.ConnectorID + ":" + command.Definition.ReleaseDigest
		if _, insertErr := store.outbox.InsertOne(txCtx, outboxRecord{
			ID:            outboxID,
			EventType:     "ConnectorDefinitionPublished",
			ConnectorID:   command.Definition.ConnectorID,
			ReleaseDigest: command.Definition.ReleaseDigest,
			OccurredAt:    command.Definition.PublishedAt,
		}); insertErr != nil {
			return nil, insertErr
		}
		result = model.MutationResult{Definition: command.Definition}
		return nil, nil
	})
	if err != nil {
		switch {
		case errors.Is(err, model.ErrIdempotencyConflict):
			return model.MutationResult{}, err
		default:
			return model.MutationResult{}, fmt.Errorf("publish connector definition: %w", err)
		}
	}
	return result, nil
}

func (store *MongoStore) available() bool {
	return store != nil && store.definitions != nil && store.receipts != nil &&
		store.outbox != nil
}
