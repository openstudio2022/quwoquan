package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/domain/model"
)

type MongoStore struct {
	invocations *mongo.Collection
	payloadRefs *mongo.Collection
	receipts    *mongo.Collection
	outbox      *mongo.Collection
}

type payloadReference struct {
	ID           string    `bson:"_id"`
	InvocationID string    `bson:"invocationId"`
	PayloadRef   string    `bson:"payloadRef"`
	ExpiresAt    time.Time `bson:"expiresAt"`
}

type commandReceipt struct {
	ID             string           `bson:"_id"`
	AccountID      string           `bson:"accountId"`
	IdempotencyKey string           `bson:"idempotencyKey"`
	CommandKind    string           `bson:"commandKind"`
	CommandDigest  string           `bson:"commandDigest"`
	Invocation     model.Invocation `bson:"invocation"`
	CreatedAt      time.Time        `bson:"createdAt"`
}

type outboxRecord struct {
	ID             string    `bson:"_id"`
	EventType      string    `bson:"eventType"`
	InvocationID   string    `bson:"invocationId"`
	AccountID      string    `bson:"accountId"`
	ConnectionID   string    `bson:"connectionId"`
	AssistantRunID string    `bson:"assistantRunId"`
	Capability     string    `bson:"capability"`
	Status         string    `bson:"status"`
	Revision       int64     `bson:"revision"`
	OccurredAt     time.Time `bson:"occurredAt"`
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		return &MongoStore{}
	}
	return &MongoStore{
		invocations: database.Collection("connector_invocations"),
		payloadRefs: database.Collection("connector_invocation_payload_refs"),
		receipts:    database.Collection("connector_invocation_command_receipts"),
		outbox:      database.Collection("connector_invocation_outbox"),
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if !store.available() {
		return model.ErrStorageUnavailable
	}
	if _, err := store.invocations.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "invocationId", Value: 1}}, Options: options.Index().SetName("uq_connector_invocations_identity").SetUnique(true)},
		{Keys: bson.D{{Key: "accountId", Value: 1}, {Key: "createdAt", Value: -1}}, Options: options.Index().SetName("idx_connector_invocations_account_created")},
		{Keys: bson.D{{Key: "connectionId", Value: 1}, {Key: "createdAt", Value: -1}}, Options: options.Index().SetName("idx_connector_invocations_connection_created")},
		{Keys: bson.D{{Key: "status", Value: 1}, {Key: "updatedAt", Value: 1}}, Options: options.Index().SetName("idx_connector_invocations_status_updated")},
		{Keys: bson.D{{Key: "status", Value: 1}, {Key: "leaseExpiresAt", Value: 1}, {Key: "updatedAt", Value: 1}}, Options: options.Index().SetName("idx_connector_invocations_worker_claim")},
	}); err != nil {
		return fmt.Errorf("ensure connector invocation indexes: %w", err)
	}
	if _, err := store.payloadRefs.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "invocationId", Value: 1}}, Options: options.Index().SetName("uq_connector_invocation_payload_ref").SetUnique(true)},
		{Keys: bson.D{{Key: "expiresAt", Value: 1}}, Options: options.Index().SetName("ttl_connector_invocation_payload_refs").SetExpireAfterSeconds(0)},
	}); err != nil {
		return fmt.Errorf("ensure connector invocation payload indexes: %w", err)
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "accountId", Value: 1}, {Key: "idempotencyKey", Value: 1}},
		Options: options.Index().SetName("uq_connector_invocation_receipt_owner_key").SetUnique(true),
	}); err != nil {
		return fmt.Errorf("ensure connector invocation receipt index: %w", err)
	}
	return nil
}

func (store *MongoStore) Get(ctx context.Context, accountID, invocationID string) (model.Invocation, error) {
	if !store.available() {
		return model.Invocation{}, model.ErrStorageUnavailable
	}
	var invocation model.Invocation
	err := store.invocations.FindOne(ctx, bson.M{
		"accountId": strings.TrimSpace(accountID), "invocationId": strings.TrimSpace(invocationID),
	}).Decode(&invocation)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Invocation{}, model.ErrNotFound
	}
	if err != nil {
		return model.Invocation{}, fmt.Errorf("get connector invocation: %w", err)
	}
	return invocation, nil
}

func (store *MongoStore) List(ctx context.Context, accountID, connectionID string, limit int) ([]model.Invocation, error) {
	if !store.available() {
		return nil, model.ErrStorageUnavailable
	}
	filter := bson.M{"accountId": strings.TrimSpace(accountID)}
	if connectionID = strings.TrimSpace(connectionID); connectionID != "" {
		filter["connectionId"] = connectionID
	}
	cursor, err := store.invocations.Find(ctx, filter, options.Find().SetSort(bson.D{{Key: "createdAt", Value: -1}}).SetLimit(int64(limit)))
	if err != nil {
		return nil, fmt.Errorf("list connector invocations: %w", err)
	}
	defer cursor.Close(ctx)
	var invocations []model.Invocation
	if err := cursor.All(ctx, &invocations); err != nil {
		return nil, fmt.Errorf("decode connector invocations: %w", err)
	}
	return invocations, nil
}

func (store *MongoStore) Accept(ctx context.Context, command model.AcceptCommand) (model.MutationResult, error) {
	if !store.available() {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	return store.withTransaction(ctx, func(txCtx context.Context) (model.MutationResult, error) {
		if replay, found, err := store.readReceipt(txCtx, command.Invocation.AccountID, command.IdempotencyKey, "accept", command.CommandDigest); found || err != nil {
			return replay, err
		}
		if _, err := store.invocations.InsertOne(txCtx, command.Invocation); err != nil {
			return model.MutationResult{}, err
		}
		if _, err := store.payloadRefs.InsertOne(txCtx, payloadReference{
			ID: command.Invocation.InvocationID, InvocationID: command.Invocation.InvocationID,
			PayloadRef: command.PayloadRef, ExpiresAt: command.Invocation.CreatedAt.Add(24 * time.Hour),
		}); err != nil {
			return model.MutationResult{}, err
		}
		return store.commitReceiptAndOutbox(txCtx, command.Invocation.AccountID, command.IdempotencyKey, "accept", command.CommandDigest, command.Invocation)
	})
}

func (store *MongoStore) Continue(ctx context.Context, input model.ContinueInput) (model.MutationResult, error) {
	if !store.available() {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	digest := hash(strings.Join([]string{
		input.AccountID, input.InvocationID, input.ConfirmationRef,
		input.ContinuationRef, fmt.Sprint(input.ExpectedRevision),
	}, "\x00"))
	return store.withTransaction(ctx, func(txCtx context.Context) (model.MutationResult, error) {
		if replay, found, err := store.readReceipt(txCtx, input.AccountID, input.IdempotencyKey, "continue", digest); found || err != nil {
			return replay, err
		}
		current, err := store.Get(txCtx, input.AccountID, input.InvocationID)
		if err != nil {
			return model.MutationResult{}, err
		}
		if current.Revision != input.ExpectedRevision || current.Status != model.StatusAwaitingConfirmation {
			return model.MutationResult{}, model.ErrRevisionConflict
		}
		next := current
		next.Status = model.StatusAccepted
		next.ConfirmationRef = input.ConfirmationRef
		if input.ContinuationRef != "" {
			next.ContinuationRef = input.ContinuationRef
		}
		next.RecoveryAction = "none"
		next.Revision++
		next.UpdatedAt = input.OccurredAt
		updated, err := store.invocations.ReplaceOne(txCtx, bson.M{
			"accountId": input.AccountID, "invocationId": input.InvocationID,
			"revision": input.ExpectedRevision, "status": model.StatusAwaitingConfirmation,
		}, next)
		if err != nil {
			return model.MutationResult{}, err
		}
		if updated.MatchedCount != 1 {
			return model.MutationResult{}, model.ErrRevisionConflict
		}
		return store.commitReceiptAndOutbox(txCtx, input.AccountID, input.IdempotencyKey, "continue", digest, next)
	})
}

func (store *MongoStore) ClaimNext(
	ctx context.Context,
	workerID string,
	now time.Time,
	leaseTTL time.Duration,
) (model.ExecutionClaim, bool, error) {
	workerID = strings.TrimSpace(workerID)
	now = now.UTC()
	if !store.available() || workerID == "" || now.IsZero() || leaseTTL <= 0 {
		return model.ExecutionClaim{}, false, model.ErrInvalidArgument
	}
	session, err := store.invocations.Database().Client().StartSession()
	if err != nil {
		return model.ExecutionClaim{}, false, fmt.Errorf("start connector invocation claim transaction: %w", err)
	}
	defer session.EndSession(ctx)
	var claim model.ExecutionClaim
	var found bool
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		var invocation model.Invocation
		filter := bson.M{"$or": bson.A{
			bson.M{"status": model.StatusAccepted},
			bson.M{"status": model.StatusExecuting, "leaseExpiresAt": bson.M{"$lte": now}},
		}}
		update := bson.M{
			"$set": bson.M{
				"status": model.StatusExecuting, "leaseOwner": workerID,
				"leaseExpiresAt": now.Add(leaseTTL), "updatedAt": now,
			},
			"$inc": bson.M{"attempt": 1, "revision": 1},
		}
		err := store.invocations.FindOneAndUpdate(
			txCtx,
			filter,
			update,
			options.FindOneAndUpdate().SetSort(bson.D{{Key: "updatedAt", Value: 1}}).SetReturnDocument(options.After),
		).Decode(&invocation)
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, nil
		}
		if err != nil {
			return nil, err
		}
		var payload payloadReference
		if err := store.payloadRefs.FindOne(txCtx, bson.M{"invocationId": invocation.InvocationID}).Decode(&payload); err != nil {
			return nil, err
		}
		if _, err := store.outbox.InsertOne(txCtx, buildOutboxRecord(invocation)); err != nil {
			return nil, err
		}
		claim = model.ExecutionClaim{Invocation: invocation, PayloadRef: payload.PayloadRef}
		found = true
		return nil, nil
	})
	if err != nil {
		return model.ExecutionClaim{}, false, fmt.Errorf("claim connector invocation: %w", err)
	}
	return claim, found, nil
}

func (store *MongoStore) Complete(ctx context.Context, input model.CompleteInput) (model.MutationResult, error) {
	if !store.available() {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	normalized, err := model.NewCompleteInput(input)
	if err != nil {
		return model.MutationResult{}, err
	}
	return store.withTransaction(ctx, func(txCtx context.Context) (model.MutationResult, error) {
		set := bson.M{
			"status": normalized.Status, "resultRef": normalized.ResultRef,
			"resultDigest":          normalized.ResultDigest,
			"normalizedFailureCode": normalized.NormalizedFailureCode,
			"recoveryAction":        normalized.RecoveryAction,
			"completedAt":           normalized.OccurredAt, "updatedAt": normalized.OccurredAt,
		}
		update := bson.M{
			"$set":   set,
			"$unset": bson.M{"leaseOwner": "", "leaseExpiresAt": ""},
			"$inc":   bson.M{"revision": 1},
		}
		var invocation model.Invocation
		err := store.invocations.FindOneAndUpdate(
			txCtx,
			bson.M{
				"accountId": normalized.AccountID, "invocationId": normalized.InvocationID,
				"status": model.StatusExecuting, "leaseOwner": normalized.LeaseOwner,
				"revision": normalized.ExpectedRevision,
			},
			update,
			options.FindOneAndUpdate().SetReturnDocument(options.After),
		).Decode(&invocation)
		if errors.Is(err, mongo.ErrNoDocuments) {
			return model.MutationResult{}, model.ErrRevisionConflict
		}
		if err != nil {
			return model.MutationResult{}, err
		}
		if _, err := store.outbox.InsertOne(txCtx, buildOutboxRecord(invocation)); err != nil {
			return model.MutationResult{}, err
		}
		if _, err := store.payloadRefs.DeleteOne(txCtx, bson.M{"invocationId": invocation.InvocationID}); err != nil {
			return model.MutationResult{}, err
		}
		return model.MutationResult{Invocation: invocation}, nil
	})
}

func (store *MongoStore) commitReceiptAndOutbox(ctx context.Context, accountID, key, kind, digest string, invocation model.Invocation) (model.MutationResult, error) {
	if _, err := store.receipts.InsertOne(ctx, commandReceipt{
		ID: accountID + ":" + key, AccountID: accountID, IdempotencyKey: key,
		CommandKind: kind, CommandDigest: digest, Invocation: invocation,
		CreatedAt: invocation.UpdatedAt,
	}); err != nil {
		return model.MutationResult{}, err
	}
	if _, err := store.outbox.InsertOne(ctx, buildOutboxRecord(invocation)); err != nil {
		return model.MutationResult{}, err
	}
	return model.MutationResult{Invocation: invocation}, nil
}

func buildOutboxRecord(invocation model.Invocation) outboxRecord {
	return outboxRecord{
		ID:        fmt.Sprintf("%s:%d", invocation.InvocationID, invocation.Revision),
		EventType: "ConnectorInvocationChanged", InvocationID: invocation.InvocationID,
		AccountID: invocation.AccountID, ConnectionID: invocation.ConnectionID,
		AssistantRunID: invocation.AssistantRunID, Capability: invocation.Capability,
		Status: invocation.Status, Revision: invocation.Revision, OccurredAt: invocation.UpdatedAt,
	}
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
	return model.MutationResult{Invocation: receipt.Invocation, Replayed: true}, true, nil
}

func (store *MongoStore) withTransaction(ctx context.Context, action func(context.Context) (model.MutationResult, error)) (model.MutationResult, error) {
	session, err := store.invocations.Database().Client().StartSession()
	if err != nil {
		return model.MutationResult{}, fmt.Errorf("start connector invocation transaction: %w", err)
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

func (store *MongoStore) available() bool {
	return store != nil && store.invocations != nil && store.payloadRefs != nil &&
		store.receipts != nil && store.outbox != nil
}
