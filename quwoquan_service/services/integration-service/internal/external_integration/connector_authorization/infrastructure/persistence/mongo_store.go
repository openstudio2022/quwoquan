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

	"quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/domain/model"
)

type MongoStore struct {
	authorizations *mongo.Collection
	receipts       *mongo.Collection
	grantReceipts  *mongo.Collection
	outbox         *mongo.Collection
}

type commandReceipt struct {
	ID             string               `bson:"_id"`
	AccountID      string               `bson:"accountId"`
	IdempotencyKey string               `bson:"idempotencyKey"`
	CommandKind    string               `bson:"commandKind"`
	CommandDigest  string               `bson:"commandDigest"`
	Result         model.MutationResult `bson:"result"`
	CreatedAt      time.Time            `bson:"createdAt"`
}

type outboxRecord struct {
	ID                    string    `bson:"_id"`
	EventType             string    `bson:"eventType"`
	AuthorizationID       string    `bson:"authorizationId"`
	AccountID             string    `bson:"accountId"`
	ConnectorID           string    `bson:"connectorId"`
	AuthorizationMode     string    `bson:"authorizationMode"`
	RequestedCapabilities []string  `bson:"requestedCapabilities,omitempty"`
	GrantedCapabilities   []string  `bson:"grantedCapabilities,omitempty"`
	Status                string    `bson:"status"`
	ExpiresAt             time.Time `bson:"expiresAt"`
	Revision              int64     `bson:"revision"`
	OccurredAt            time.Time `bson:"occurredAt"`
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		return &MongoStore{}
	}
	return &MongoStore{
		authorizations: database.Collection("connector_authorizations"),
		receipts:       database.Collection("connector_authorization_command_receipts"),
		grantReceipts:  database.Collection("connector_authorization_grant_receipts"),
		outbox:         database.Collection("connector_authorization_outbox"),
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if !store.available() {
		return model.ErrStorageUnavailable
	}
	if _, err := store.authorizations.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "authorizationId", Value: 1}}, Options: options.Index().SetName("uq_connector_authorizations_id").SetUnique(true)},
		{Keys: bson.D{{Key: "accountId", Value: 1}, {Key: "createdAt", Value: -1}}, Options: options.Index().SetName("idx_connector_authorizations_account_created")},
		{Keys: bson.D{{Key: "status", Value: 1}, {Key: "expiresAt", Value: 1}}, Options: options.Index().SetName("idx_connector_authorizations_status_expiry")},
	}); err != nil {
		return fmt.Errorf("ensure connector authorization indexes: %w", err)
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "accountId", Value: 1}, {Key: "idempotencyKey", Value: 1}},
		Options: options.Index().SetName("uq_connector_authorization_receipt_owner_key").SetUnique(true),
	}); err != nil {
		return fmt.Errorf("ensure connector authorization receipt index: %w", err)
	}
	if _, err := store.grantReceipts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "grantReceiptDigest", Value: 1}}, Options: options.Index().SetName("uq_connector_authorization_grant_receipt_digest").SetUnique(true)},
		{Keys: bson.D{{Key: "expiresAt", Value: 1}}, Options: options.Index().SetName("ttl_connector_authorization_grant_receipts").SetExpireAfterSeconds(0)},
	}); err != nil {
		return fmt.Errorf("ensure connector authorization grant receipt indexes: %w", err)
	}
	return nil
}

func (store *MongoStore) Get(
	ctx context.Context,
	accountID string,
	authorizationID string,
) (model.Authorization, error) {
	if !store.available() {
		return model.Authorization{}, model.ErrStorageUnavailable
	}
	var authorization model.Authorization
	err := store.authorizations.FindOne(ctx, bson.M{
		"accountId":       strings.TrimSpace(accountID),
		"authorizationId": strings.TrimSpace(authorizationID),
	}).Decode(&authorization)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Authorization{}, model.ErrNotFound
	}
	if err != nil {
		return model.Authorization{}, fmt.Errorf("get connector authorization: %w", err)
	}
	return authorization, nil
}

func (store *MongoStore) GetByID(
	ctx context.Context,
	authorizationID string,
) (model.Authorization, error) {
	if !store.available() {
		return model.Authorization{}, model.ErrStorageUnavailable
	}
	var authorization model.Authorization
	err := store.authorizations.FindOne(ctx, bson.M{
		"authorizationId": strings.TrimSpace(authorizationID),
	}).Decode(&authorization)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Authorization{}, model.ErrNotFound
	}
	if err != nil {
		return model.Authorization{}, fmt.Errorf("get connector authorization by id: %w", err)
	}
	return authorization, nil
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
	return store.readReceipt(ctx, accountID, idempotencyKey, commandKind, commandDigest)
}

func (store *MongoStore) Start(
	ctx context.Context,
	command model.StartCommand,
) (model.MutationResult, error) {
	if !store.available() {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	session, err := store.authorizations.Database().Client().StartSession()
	if err != nil {
		return model.MutationResult{}, fmt.Errorf("start connector authorization transaction: %w", err)
	}
	defer session.EndSession(ctx)

	var committed model.MutationResult
	if _, err := session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		replay, found, receiptErr := store.readReceipt(
			txCtx,
			command.Authorization.AccountID,
			command.IdempotencyKey,
			"start",
			command.CommandDigest,
		)
		if receiptErr != nil {
			return nil, receiptErr
		}
		if found {
			committed = replay
			return nil, nil
		}
		if _, insertErr := store.authorizations.InsertOne(txCtx, command.Authorization); insertErr != nil {
			if mongo.IsDuplicateKeyError(insertErr) {
				return nil, model.ErrIdempotencyConflict
			}
			return nil, insertErr
		}
		result := model.MutationResult{
			Authorization:   command.Authorization,
			ContinuationRef: command.ContinuationRef,
		}
		if receiptErr := store.commitReceipt(
			txCtx,
			command.Authorization.AccountID,
			command.IdempotencyKey,
			"start",
			command.CommandDigest,
			result,
			command.Authorization.CreatedAt,
		); receiptErr != nil {
			return nil, receiptErr
		}
		// 事件行与授权状态共用同一个事务句柄：提交成功即事件已可读，任一步失败
		// 则状态与事件一起回滚。
		if outboxErr := store.insertOutbox(
			txCtx, command.Authorization, "ConnectorAuthorizationStarted",
		); outboxErr != nil {
			return nil, outboxErr
		}
		committed = result
		return nil, nil
	}); err != nil {
		return model.MutationResult{}, err
	}
	return committed, nil
}

func (store *MongoStore) Verify(
	ctx context.Context,
	command model.VerifyCommand,
) (model.MutationResult, error) {
	if !store.available() {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	session, err := store.authorizations.Database().Client().StartSession()
	if err != nil {
		return model.MutationResult{}, fmt.Errorf("start connector authorization transaction: %w", err)
	}
	defer session.EndSession(ctx)

	var committed model.MutationResult
	if _, err := session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		replay, found, receiptErr := store.readReceipt(
			txCtx,
			command.Authorization.AccountID,
			command.IdempotencyKey,
			"verify",
			command.CommandDigest,
		)
		if receiptErr != nil {
			return nil, receiptErr
		}
		if found {
			committed = replay
			return nil, nil
		}
		updated, replaceErr := store.authorizations.ReplaceOne(txCtx, bson.M{
			"accountId":       command.Authorization.AccountID,
			"authorizationId": command.Authorization.AuthorizationID,
			"status":          model.StatusPending,
			"revision":        command.ExpectedRevision,
			"expiresAt":       bson.M{"$gt": command.OccurredAt},
		}, command.Authorization)
		if replaceErr != nil {
			return nil, replaceErr
		}
		if updated.MatchedCount != 1 {
			return nil, model.ErrRevisionConflict
		}
		if _, insertErr := store.grantReceipts.InsertOne(txCtx, command.GrantReceipt); insertErr != nil {
			if mongo.IsDuplicateKeyError(insertErr) {
				return nil, model.ErrIdempotencyConflict
			}
			return nil, insertErr
		}
		result := model.MutationResult{
			Authorization:   command.Authorization,
			GrantReceiptRef: command.GrantReceiptRef,
		}
		if receiptErr := store.commitReceipt(
			txCtx,
			command.Authorization.AccountID,
			command.IdempotencyKey,
			"verify",
			command.CommandDigest,
			result,
			command.OccurredAt,
		); receiptErr != nil {
			return nil, receiptErr
		}
		// 事件行与授权状态共用同一个事务句柄：提交成功即事件已可读，任一步失败
		// 则状态与事件一起回滚。
		if outboxErr := store.insertOutbox(
			txCtx, command.Authorization, "ConnectorAuthorizationVerified",
		); outboxErr != nil {
			return nil, outboxErr
		}
		committed = result
		return nil, nil
	}); err != nil {
		return model.MutationResult{}, err
	}
	return committed, nil
}

func (store *MongoStore) Consume(
	ctx context.Context,
	accountID string,
	connectorID string,
	authorizationID string,
	grantReceiptDigest string,
	connectionID string,
	occurredAt time.Time,
) error {
	if !store.available() {
		return model.ErrStorageUnavailable
	}
	if mongo.SessionFromContext(ctx) == nil {
		return model.ErrStorageUnavailable
	}
	accountID = strings.TrimSpace(accountID)
	connectorID = strings.TrimSpace(connectorID)
	authorizationID = strings.TrimSpace(authorizationID)
	grantReceiptDigest = strings.TrimSpace(grantReceiptDigest)
	connectionID = strings.TrimSpace(connectionID)
	occurredAt = occurredAt.UTC()
	if accountID == "" || connectorID == "" || authorizationID == "" ||
		!model.ValidDigest(grantReceiptDigest) || connectionID == "" || occurredAt.IsZero() {
		return model.ErrInvalidArgument
	}
	result := store.grantReceipts.FindOneAndUpdate(ctx, bson.M{
		"accountId":          accountID,
		"connectorId":        connectorID,
		"authorizationId":    authorizationID,
		"grantReceiptDigest": grantReceiptDigest,
		"consumedAt":         bson.M{"$exists": false},
		"expiresAt":          bson.M{"$gt": occurredAt},
	}, bson.M{"$set": bson.M{
		"consumedByConnectionId": connectionID,
		"consumedAt":             occurredAt,
	}}, options.FindOneAndUpdate().SetReturnDocument(options.After))
	if err := result.Err(); errors.Is(err, mongo.ErrNoDocuments) {
		return model.ErrGrantAlreadyConsumed
	} else if err != nil {
		return err
	}
	updated, err := store.authorizations.UpdateOne(ctx, bson.M{
		"accountId":          accountID,
		"connectorId":        connectorID,
		"authorizationId":    authorizationID,
		"grantReceiptDigest": grantReceiptDigest,
		"status":             model.StatusVerified,
	}, bson.M{
		"$set": bson.M{
			"status":     model.StatusConsumed,
			"consumedAt": occurredAt,
			"updatedAt":  occurredAt,
		},
		"$inc": bson.M{"revision": 1},
	})
	if err != nil {
		return err
	}
	if updated.MatchedCount != 1 {
		return model.ErrGrantAlreadyConsumed
	}
	authorization, err := store.Get(ctx, accountID, authorizationID)
	if err != nil {
		return err
	}
	return store.insertOutbox(ctx, authorization, "ConnectorAuthorizationConsumed")
}

func (store *MongoStore) Revoke(
	ctx context.Context,
	accountID string,
	connectorID string,
	grantReceiptDigest string,
	occurredAt time.Time,
) error {
	if !store.available() || mongo.SessionFromContext(ctx) == nil {
		return model.ErrStorageUnavailable
	}
	accountID = strings.TrimSpace(accountID)
	connectorID = strings.TrimSpace(connectorID)
	grantReceiptDigest = strings.TrimSpace(grantReceiptDigest)
	occurredAt = occurredAt.UTC()
	if accountID == "" || connectorID == "" ||
		!model.ValidDigest(grantReceiptDigest) || occurredAt.IsZero() {
		return model.ErrInvalidArgument
	}
	var authorization model.Authorization
	err := store.authorizations.FindOneAndUpdate(ctx, bson.M{
		"accountId":          accountID,
		"connectorId":        connectorID,
		"grantReceiptDigest": grantReceiptDigest,
		"status":             bson.M{"$in": []string{model.StatusVerified, model.StatusConsumed}},
	}, bson.M{
		"$set": bson.M{
			"status":        model.StatusRevoked,
			"credentialRef": "",
			"updatedAt":     occurredAt,
		},
		"$inc": bson.M{"revision": 1},
	}, options.FindOneAndUpdate().SetReturnDocument(options.After)).Decode(&authorization)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.ErrNotFound
	}
	if err != nil {
		return err
	}
	return store.insertOutbox(ctx, authorization, "ConnectorAuthorizationRevoked")
}

func (store *MongoStore) commitReceipt(
	ctx context.Context,
	accountID string,
	idempotencyKey string,
	commandKind string,
	commandDigest string,
	result model.MutationResult,
	createdAt time.Time,
) error {
	_, err := store.receipts.InsertOne(ctx, commandReceipt{
		ID:             accountID + ":" + idempotencyKey,
		AccountID:      accountID,
		IdempotencyKey: idempotencyKey,
		CommandKind:    commandKind,
		CommandDigest:  commandDigest,
		Result:         result,
		CreatedAt:      createdAt,
	})
	return err
}

func (store *MongoStore) readReceipt(
	ctx context.Context,
	accountID string,
	idempotencyKey string,
	commandKind string,
	commandDigest string,
) (model.MutationResult, bool, error) {
	var receipt commandReceipt
	err := store.receipts.FindOne(ctx, bson.M{
		"accountId":      strings.TrimSpace(accountID),
		"idempotencyKey": strings.TrimSpace(idempotencyKey),
	}).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.MutationResult{}, false, nil
	}
	if err != nil {
		return model.MutationResult{}, false, err
	}
	if receipt.CommandKind != commandKind || receipt.CommandDigest != commandDigest {
		return model.MutationResult{}, true, model.ErrIdempotencyConflict
	}
	result := receipt.Result
	result.Replayed = true
	return result, true, nil
}

func (store *MongoStore) insertOutbox(
	ctx context.Context,
	authorization model.Authorization,
	eventType string,
) error {
	_, err := store.outbox.InsertOne(ctx, outboxRecord{
		ID:                    fmt.Sprintf("%s:%d", authorization.AuthorizationID, authorization.Revision),
		EventType:             eventType,
		AuthorizationID:       authorization.AuthorizationID,
		AccountID:             authorization.AccountID,
		ConnectorID:           authorization.ConnectorID,
		AuthorizationMode:     authorization.AuthorizationMode,
		RequestedCapabilities: append([]string(nil), authorization.RequestedCapabilities...),
		GrantedCapabilities:   append([]string(nil), authorization.GrantedCapabilities...),
		Status:                authorization.Status,
		ExpiresAt:             authorization.ExpiresAt,
		Revision:              authorization.Revision,
		OccurredAt:            authorization.UpdatedAt,
	})
	return err
}

func (store *MongoStore) available() bool {
	return store != nil && store.authorizations != nil && store.receipts != nil &&
		store.grantReceipts != nil && store.outbox != nil
}
