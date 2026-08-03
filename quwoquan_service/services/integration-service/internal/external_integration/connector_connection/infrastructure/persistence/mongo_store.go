package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	authorizationports "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/domain/ports"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/model"
)

type MongoStore struct {
	connections   *mongo.Collection
	receipts      *mongo.Collection
	outbox        *mongo.Collection
	grantConsumer authorizationports.GrantConsumer
}

type commandReceipt struct {
	ID             string           `bson:"_id"`
	AccountID      string           `bson:"accountId"`
	IdempotencyKey string           `bson:"idempotencyKey"`
	CommandKind    string           `bson:"commandKind"`
	CommandDigest  string           `bson:"commandDigest"`
	Connection     model.Connection `bson:"connection"`
	CreatedAt      time.Time        `bson:"createdAt"`
}

type outboxRecord struct {
	ID           string    `bson:"_id"`
	EventType    string    `bson:"eventType"`
	ConnectionID string    `bson:"connectionId"`
	AccountID    string    `bson:"accountId"`
	ConnectorID  string    `bson:"connectorId"`
	Status       string    `bson:"status"`
	Revision     int64     `bson:"revision"`
	OccurredAt   time.Time `bson:"occurredAt"`
}

func NewMongoStore(database *mongo.Database, grantConsumer authorizationports.GrantConsumer) *MongoStore {
	if database == nil {
		return &MongoStore{grantConsumer: grantConsumer}
	}
	return &MongoStore{
		connections:   database.Collection("connector_connections"),
		receipts:      database.Collection("connector_connection_command_receipts"),
		outbox:        database.Collection("connector_connection_outbox"),
		grantConsumer: grantConsumer,
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if !store.available() {
		return model.ErrStorageUnavailable
	}
	if _, err := store.connections.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "accountId", Value: 1}, {Key: "connectorId", Value: 1}}, Options: options.Index().SetName("uq_connector_connections_account_connector").SetUnique(true)},
		{Keys: bson.D{{Key: "accountId", Value: 1}, {Key: "status", Value: 1}, {Key: "updatedAt", Value: -1}}, Options: options.Index().SetName("idx_connector_connections_account_status")},
		{Keys: bson.D{{Key: "grantReceiptDigest", Value: 1}}, Options: options.Index().SetName("uq_connector_connections_grant_receipt").SetUnique(true)},
	}); err != nil {
		return fmt.Errorf("ensure connector connection indexes: %w", err)
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "accountId", Value: 1}, {Key: "idempotencyKey", Value: 1}},
		Options: options.Index().SetName("uq_connector_connection_receipt_owner_key").SetUnique(true),
	}); err != nil {
		return fmt.Errorf("ensure connector connection receipt index: %w", err)
	}
	return nil
}

func (store *MongoStore) Get(ctx context.Context, accountID, connectionID string) (model.Connection, error) {
	if !store.available() {
		return model.Connection{}, model.ErrStorageUnavailable
	}
	var connection model.Connection
	err := store.connections.FindOne(ctx, bson.M{
		"accountId": strings.TrimSpace(accountID), "connectionId": strings.TrimSpace(connectionID),
	}).Decode(&connection)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Connection{}, model.ErrNotFound
	}
	if err != nil {
		return model.Connection{}, fmt.Errorf("get connector connection: %w", err)
	}
	return connection, nil
}

func (store *MongoStore) List(ctx context.Context, accountID string, limit int) ([]model.Connection, error) {
	if !store.available() {
		return nil, model.ErrStorageUnavailable
	}
	cursor, err := store.connections.Find(ctx, bson.M{"accountId": strings.TrimSpace(accountID)}, options.Find().SetSort(bson.D{{Key: "updatedAt", Value: -1}}).SetLimit(int64(limit)))
	if err != nil {
		return nil, fmt.Errorf("list connector connections: %w", err)
	}
	defer cursor.Close(ctx)
	var connections []model.Connection
	if err := cursor.All(ctx, &connections); err != nil {
		return nil, fmt.Errorf("decode connector connections: %w", err)
	}
	return connections, nil
}

func (store *MongoStore) Replay(
	ctx context.Context,
	accountID string,
	idempotencyKey string,
	commandKind string,
	commandDigest string,
) (model.MutationResult, bool, error) {
	if !store.available() {
		return model.MutationResult{}, false, model.ErrStorageUnavailable
	}
	return store.readReceipt(
		ctx,
		strings.TrimSpace(accountID),
		strings.TrimSpace(idempotencyKey),
		strings.TrimSpace(commandKind),
		strings.TrimSpace(commandDigest),
	)
}

func (store *MongoStore) Create(ctx context.Context, command model.CreateCommand) (model.MutationResult, error) {
	if !store.available() {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	return store.withTransaction(ctx, func(txCtx context.Context) (model.MutationResult, error) {
		if replay, found, err := store.readReceipt(txCtx, command.AccountID, command.IdempotencyKey, "create", command.CommandDigest); found || err != nil {
			return replay, err
		}
		var current model.Connection
		err := store.connections.FindOne(txCtx, bson.M{
			"accountId": command.AccountID, "connectorId": command.ConnectorID,
		}).Decode(&current)
		if err != nil && !errors.Is(err, mongo.ErrNoDocuments) {
			return model.MutationResult{}, err
		}
		next := model.Connection{
			ConnectionID: uuid.NewString(), AccountID: command.AccountID,
			ConnectorID: command.ConnectorID, GrantedCapabilities: command.GrantedCapabilities,
			Status: model.StatusActive, CredentialRef: command.CredentialRef,
			GrantReceiptDigest: command.GrantReceiptDigest, FreshnessAt: command.OccurredAt,
			ExpiresAt: command.ExpiresAt, Revision: 1,
			CreatedAt: command.OccurredAt, UpdatedAt: command.OccurredAt,
		}
		if err == nil {
			next.ConnectionID = current.ConnectionID
			next.Revision = current.Revision + 1
			next.CreatedAt = current.CreatedAt
		}
		if store.grantConsumer == nil {
			return model.MutationResult{}, model.ErrGrantReceiptInvalid
		}
		if err := store.grantConsumer.Consume(
			txCtx,
			command.AccountID,
			command.ConnectorID,
			command.AuthorizationID,
			command.GrantReceiptDigest,
			next.ConnectionID,
			command.OccurredAt,
		); err != nil {
			return model.MutationResult{}, model.ErrGrantReceiptInvalid
		}
		if _, err := store.connections.ReplaceOne(txCtx, bson.M{
			"accountId": command.AccountID, "connectorId": command.ConnectorID,
		}, next, options.Replace().SetUpsert(true)); err != nil {
			if mongo.IsDuplicateKeyError(err) {
				return model.MutationResult{}, model.ErrGrantReceiptInvalid
			}
			return model.MutationResult{}, err
		}
		return store.commitReceiptAndOutbox(txCtx, command.AccountID, command.IdempotencyKey, "create", command.CommandDigest, next, "ConnectorConnectionChanged")
	})
}

func (store *MongoStore) Revoke(ctx context.Context, input model.RevokeInput) (model.MutationResult, error) {
	if !store.available() {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	commandDigest := hash(strings.Join([]string{input.AccountID, input.ConnectionID, fmt.Sprint(input.ExpectedRevision)}, "\x00"))
	return store.withTransaction(ctx, func(txCtx context.Context) (model.MutationResult, error) {
		if replay, found, err := store.readReceipt(txCtx, input.AccountID, input.IdempotencyKey, "revoke", commandDigest); found || err != nil {
			return replay, err
		}
		current, err := store.Get(txCtx, input.AccountID, input.ConnectionID)
		if err != nil {
			return model.MutationResult{}, err
		}
		if current.Revision != input.ExpectedRevision {
			return model.MutationResult{}, model.ErrRevisionConflict
		}
		next := current
		next.Status = model.StatusRevoked
		next.CredentialRef = ""
		next.RevokedAt = timePointer(input.OccurredAt)
		next.Revision++
		next.UpdatedAt = input.OccurredAt
		if store.grantConsumer == nil {
			return model.MutationResult{}, model.ErrStorageUnavailable
		}
		if err := store.grantConsumer.Revoke(
			txCtx,
			current.AccountID,
			current.ConnectorID,
			current.GrantReceiptDigest,
			input.OccurredAt,
		); err != nil {
			return model.MutationResult{}, model.ErrStorageUnavailable
		}
		updated, err := store.connections.ReplaceOne(txCtx, bson.M{
			"accountId": input.AccountID, "connectionId": input.ConnectionID,
			"revision": input.ExpectedRevision,
		}, next)
		if err != nil {
			return model.MutationResult{}, err
		}
		if updated.MatchedCount != 1 {
			return model.MutationResult{}, model.ErrRevisionConflict
		}
		return store.commitReceiptAndOutbox(txCtx, input.AccountID, input.IdempotencyKey, "revoke", commandDigest, next, "ConnectorConnectionRevoked")
	})
}

func (store *MongoStore) commitReceiptAndOutbox(ctx context.Context, accountID, key, kind, digest string, connection model.Connection, eventType string) (model.MutationResult, error) {
	receipt := commandReceipt{
		ID: accountID + ":" + key, AccountID: accountID, IdempotencyKey: key,
		CommandKind: kind, CommandDigest: digest, Connection: connection,
		CreatedAt: connection.UpdatedAt,
	}
	if _, err := store.receipts.InsertOne(ctx, receipt); err != nil {
		return model.MutationResult{}, err
	}
	if _, err := store.outbox.InsertOne(ctx, outboxRecord{
		ID:        fmt.Sprintf("%s:%d", connection.ConnectionID, connection.Revision),
		EventType: eventType, ConnectionID: connection.ConnectionID,
		AccountID: connection.AccountID, ConnectorID: connection.ConnectorID,
		Status: connection.Status, Revision: connection.Revision, OccurredAt: connection.UpdatedAt,
	}); err != nil {
		return model.MutationResult{}, err
	}
	return model.MutationResult{Connection: connection}, nil
}

func (store *MongoStore) readReceipt(ctx context.Context, accountID, key, kind, digest string) (model.MutationResult, bool, error) {
	var receipt commandReceipt
	err := store.receipts.FindOne(ctx, bson.M{"accountId": accountID, "idempotencyKey": key}).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.MutationResult{}, false, nil
	}
	if err != nil {
		return model.MutationResult{}, false, err
	}
	if receipt.CommandKind != kind || receipt.CommandDigest != digest {
		return model.MutationResult{}, true, model.ErrIdempotencyConflict
	}
	return model.MutationResult{Connection: receipt.Connection, Replayed: true}, true, nil
}

func (store *MongoStore) withTransaction(ctx context.Context, action func(context.Context) (model.MutationResult, error)) (model.MutationResult, error) {
	session, err := store.connections.Database().Client().StartSession()
	if err != nil {
		return model.MutationResult{}, fmt.Errorf("start connector connection transaction: %w", err)
	}
	defer session.EndSession(ctx)
	var result model.MutationResult
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		var actionErr error
		result, actionErr = action(txCtx)
		return nil, actionErr
	})
	if err != nil {
		return model.MutationResult{}, err
	}
	return result, nil
}

func hash(value string) string {
	sum := sha256.Sum256([]byte(value))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func timePointer(value time.Time) *time.Time {
	normalized := value.UTC()
	return &normalized
}

func (store *MongoStore) available() bool {
	return store != nil && store.connections != nil && store.receipts != nil && store.outbox != nil
}
