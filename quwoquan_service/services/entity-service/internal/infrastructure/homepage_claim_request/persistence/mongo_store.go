// Package persistence 实现 HomepageClaimRequest 的 Mongo CAS、receipt 与 outbox Store。
package persistence

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	claimmodel "quwoquan_service/services/entity-service/internal/domain/homepage_claim_request/model"
	claimports "quwoquan_service/services/entity-service/internal/domain/homepage_claim_request/ports"
	"quwoquan_service/services/entity-service/internal/generated"
)

const (
	claimCollection      = "homepage_claim_requests"
	receiptCollection    = "homepage_claim_request_command_receipts"
	outboxCollection     = "homepage_claim_request_outbox"
	checkpointCollection = "homepage_claim_request_projection_checkpoints"
)

type MongoStore struct {
	claims      *mongo.Collection
	receipts    *mongo.Collection
	outbox      *mongo.Collection
	checkpoints *mongo.Collection
	supportsTxn bool
}

func NewMongoStore(db *mongo.Database, supportsTransactions bool) *MongoStore {
	return &MongoStore{
		claims:      db.Collection(claimCollection),
		receipts:    db.Collection(receiptCollection),
		outbox:      db.Collection(outboxCollection),
		checkpoints: db.Collection(checkpointCollection),
		supportsTxn: supportsTransactions,
	}
}

var (
	_ claimports.AggregateStore            = (*MongoStore)(nil)
	_ claimports.QueueReader               = (*MongoStore)(nil)
	_ claimports.ReceiptStore              = (*MongoStore)(nil)
	_ claimports.OutboxReader              = (*MongoStore)(nil)
	_ claimports.ProjectionCheckpointStore = (*MongoStore)(nil)
)

func (s *MongoStore) EnsureIndexes(ctx context.Context) error {
	if _, err := s.claims.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "homepageId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "createdAt", Value: -1},
			},
			Options: options.Index().SetName("idx_claim_requests_homepage_status"),
		},
		{
			Keys: bson.D{
				{Key: "requesterPersonaId", Value: 1},
				{Key: "createdAt", Value: -1},
			},
			Options: options.Index().SetName("idx_claim_requests_requester"),
		},
		{
			Keys: bson.D{
				{Key: "status", Value: 1},
				{Key: "createdAt", Value: -1},
				{Key: "_id", Value: -1},
			},
			Options: options.Index().SetName("idx_claim_requests_governance_queue"),
		},
		{
			Keys: bson.D{
				{Key: "homepageId", Value: 1},
				{Key: "requesterPersonaId", Value: 1},
			},
			Options: options.Index().
				SetName("idx_claim_requests_pending_unique").
				SetUnique(true).
				SetPartialFilterExpression(bson.M{
					"status": string(claimmodel.StatusPendingReview),
				}),
		},
		{
			Keys: bson.D{{Key: "_id", Value: 1}, {Key: "version", Value: 1}},
			Options: options.Index().
				SetName("idx_claim_requests_version").
				SetUnique(true),
		},
	}); err != nil {
		return err
	}
	if _, err := s.receipts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "aggregateId", Value: 1},
				{Key: "aggregateVersion", Value: -1},
			},
			Options: options.Index().SetName("idx_claim_request_receipts_aggregate"),
		},
		{
			Keys: bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().
				SetName("idx_claim_request_receipts_expire").
				SetExpireAfterSeconds(0),
		},
	}); err != nil {
		return err
	}
	if _, err := s.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "occurredAt", Value: 1}, {Key: "_id", Value: 1}},
			Options: options.Index().SetName("idx_claim_request_outbox_replay"),
		},
		{
			Keys: bson.D{
				{Key: "aggregateId", Value: 1},
				{Key: "aggregateVersion", Value: 1},
			},
			Options: options.Index().
				SetName("idx_claim_request_outbox_aggregate_version").
				SetUnique(true),
		},
	}); err != nil {
		return err
	}
	// checkpoint 的 _id 唯一约束由 Mongo 内建 _id_ 索引提供。
	return nil
}

type claimDocument struct {
	ID                   string     `bson:"_id"`
	Version              int64      `bson:"version"`
	HomepageID           string     `bson:"homepageId"`
	RequesterPersonaID   string     `bson:"requesterPersonaId"`
	ClaimTier            string     `bson:"claimTier"`
	BusinessLicenseURL   string     `bson:"businessLicenseUrl,omitempty"`
	ContactPhone         string     `bson:"contactPhone,omitempty"`
	IdentityCardFrontURL string     `bson:"identityCardFrontUrl,omitempty"`
	IdentityCardBackURL  string     `bson:"identityCardBackUrl,omitempty"`
	Note                 string     `bson:"note,omitempty"`
	Status               string     `bson:"status"`
	ReviewerAccountID    string     `bson:"reviewerAccountId,omitempty"`
	ReviewNote           string     `bson:"reviewNote,omitempty"`
	CreatedAt            time.Time  `bson:"createdAt"`
	UpdatedAt            time.Time  `bson:"updatedAt"`
	ReviewedAt           *time.Time `bson:"reviewedAt,omitempty"`
}

func documentFromSnapshot(snapshot claimmodel.Snapshot) claimDocument {
	return claimDocument{
		ID:                   snapshot.ID,
		Version:              snapshot.Version,
		HomepageID:           snapshot.HomepageID,
		RequesterPersonaID:   snapshot.RequesterPersonaID,
		ClaimTier:            string(snapshot.ClaimTier),
		BusinessLicenseURL:   snapshot.BusinessLicenseURL,
		ContactPhone:         snapshot.ContactPhone,
		IdentityCardFrontURL: snapshot.IdentityCardFrontURL,
		IdentityCardBackURL:  snapshot.IdentityCardBackURL,
		Note:                 snapshot.Note,
		Status:               string(snapshot.Status),
		ReviewerAccountID:    snapshot.ReviewerAccountID,
		ReviewNote:           snapshot.ReviewNote,
		CreatedAt:            snapshot.CreatedAt.UTC(),
		UpdatedAt:            snapshot.UpdatedAt.UTC(),
		ReviewedAt:           cloneTime(snapshot.ReviewedAt),
	}
}

func (d claimDocument) aggregate() (*claimmodel.HomepageClaimRequest, error) {
	return claimmodel.Restore(claimmodel.Snapshot{
		ID:                   d.ID,
		Version:              d.Version,
		HomepageID:           d.HomepageID,
		RequesterPersonaID:   d.RequesterPersonaID,
		ClaimTier:            claimmodel.ClaimTier(d.ClaimTier),
		BusinessLicenseURL:   d.BusinessLicenseURL,
		ContactPhone:         d.ContactPhone,
		IdentityCardFrontURL: d.IdentityCardFrontURL,
		IdentityCardBackURL:  d.IdentityCardBackURL,
		Note:                 d.Note,
		Status:               claimmodel.Status(d.Status),
		ReviewerAccountID:    d.ReviewerAccountID,
		ReviewNote:           d.ReviewNote,
		CreatedAt:            d.CreatedAt,
		UpdatedAt:            d.UpdatedAt,
		ReviewedAt:           cloneTime(d.ReviewedAt),
	})
}

func (s *MongoStore) ListQueue(
	ctx context.Context,
	query claimports.QueueQuery,
) (claimports.QueuePage, error) {
	limit := query.Limit
	if limit <= 0 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}
	filter := bson.M{}
	if homepageID := strings.TrimSpace(query.HomepageID); homepageID != "" {
		filter["homepageId"] = homepageID
	}
	if query.Status != "" {
		filter["status"] = string(query.Status)
	}
	if cursorValue := strings.TrimSpace(query.Cursor); cursorValue != "" {
		createdAt, id, err := decodeQueueCursor(cursorValue)
		if err != nil {
			return claimports.QueuePage{}, err
		}
		filter["$or"] = bson.A{
			bson.M{"createdAt": bson.M{"$lt": createdAt}},
			bson.M{"createdAt": createdAt, "_id": bson.M{"$lt": id}},
		}
	}
	cursor, err := s.claims.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}}).
			SetLimit(int64(limit+1)),
	)
	if err != nil {
		return claimports.QueuePage{}, err
	}
	defer func() { _ = cursor.Close(ctx) }()
	var documents []claimDocument
	if err := cursor.All(ctx, &documents); err != nil {
		return claimports.QueuePage{}, err
	}
	page := claimports.QueuePage{
		Items: make([]claimmodel.Snapshot, 0, min(limit, len(documents))),
	}
	for index, document := range documents {
		if index == limit {
			last := documents[limit-1]
			page.NextCursor = encodeQueueCursor(last.CreatedAt, last.ID)
			break
		}
		aggregate, restoreErr := document.aggregate()
		if restoreErr != nil {
			return claimports.QueuePage{}, restoreErr
		}
		page.Items = append(page.Items, aggregate.Snapshot())
	}
	return page, nil
}

func encodeQueueCursor(createdAt time.Time, id string) string {
	return createdAt.UTC().Format(time.RFC3339Nano) + "|" + id
}

func decodeQueueCursor(cursor string) (time.Time, string, error) {
	parts := strings.SplitN(cursor, "|", 2)
	if len(parts) != 2 || strings.TrimSpace(parts[1]) == "" {
		return time.Time{}, "", generated.AppErrorFromInvalidArgument(
			"homepage claim request queue cursor is malformed",
		)
	}
	createdAt, err := time.Parse(time.RFC3339Nano, parts[0])
	if err != nil {
		return time.Time{}, "", generated.AppErrorFromInvalidArgument(
			"homepage claim request queue cursor timestamp is malformed",
		)
	}
	return createdAt.UTC(), parts[1], nil
}

type receiptDocument struct {
	ID               string        `bson:"_id"`
	AggregateID      string        `bson:"aggregateId"`
	AggregateVersion int64         `bson:"aggregateVersion"`
	CommandName      string        `bson:"commandName"`
	CommandDigest    string        `bson:"commandDigest"`
	Result           claimDocument `bson:"result"`
	CreatedAt        time.Time     `bson:"createdAt"`
	ExpiresAt        time.Time     `bson:"expiresAt"`
}

type outboxDocument struct {
	ID               string    `bson:"_id"`
	EventType        string    `bson:"eventType"`
	AggregateID      string    `bson:"aggregateId"`
	AggregateVersion int64     `bson:"aggregateVersion"`
	Payload          []byte    `bson:"payload"`
	OccurredAt       time.Time `bson:"occurredAt"`
}

func (s *MongoStore) Load(
	ctx context.Context,
	claimRequestID string,
) (*claimmodel.HomepageClaimRequest, bool, error) {
	var document claimDocument
	err := s.claims.FindOne(ctx, bson.M{"_id": strings.TrimSpace(claimRequestID)}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	aggregate, err := document.aggregate()
	return aggregate, err == nil, err
}

func (s *MongoStore) FindPending(
	ctx context.Context,
	homepageID string,
	requesterPersonaID string,
) (*claimmodel.HomepageClaimRequest, bool, error) {
	var document claimDocument
	err := s.claims.FindOne(ctx, bson.M{
		"homepageId":         strings.TrimSpace(homepageID),
		"requesterPersonaId": strings.TrimSpace(requesterPersonaID),
		"status":             string(claimmodel.StatusPendingReview),
	}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	aggregate, err := document.aggregate()
	return aggregate, err == nil, err
}

func (s *MongoStore) findReceipt(
	ctx context.Context,
	idempotencyKey string,
) (receiptDocument, bool, error) {
	var receipt receiptDocument
	err := s.receipts.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(idempotencyKey)},
	).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return receiptDocument{}, false, nil
	}
	return receipt, err == nil, err
}

func (s *MongoStore) FindReceipt(
	ctx context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (claimports.CommitResult, bool, error) {
	receipt, found, err := s.findReceipt(ctx, idempotencyKey)
	if err != nil || !found {
		return claimports.CommitResult{}, found, err
	}
	if !receipt.ExpiresAt.After(time.Now().UTC()) {
		if _, err := s.receipts.DeleteOne(ctx, bson.M{"_id": receipt.ID}); err != nil {
			return claimports.CommitResult{}, false, err
		}
		return claimports.CommitResult{}, false, nil
	}
	if receipt.CommandName != commandName || receipt.CommandDigest != commandDigest {
		return claimports.CommitResult{}, false, generated.AppErrorFromIdempotencyConflict(
			"idempotency key was reused with a different homepage claim command",
		)
	}
	aggregate, err := receipt.Result.aggregate()
	if err != nil {
		return claimports.CommitResult{}, false, err
	}
	return claimports.CommitResult{Aggregate: aggregate, Replayed: true}, true, nil
}

func (s *MongoStore) RecordNoopReceipt(
	ctx context.Context,
	noop claimports.NoopReceipt,
) (claimports.CommitResult, error) {
	if noop.Aggregate == nil || strings.TrimSpace(noop.IdempotencyKey) == "" ||
		strings.TrimSpace(noop.CommandName) == "" || strings.TrimSpace(noop.CommandDigest) == "" {
		return claimports.CommitResult{}, generated.AppErrorFromVersionConflict(
			"homepage claim no-op receipt is incomplete",
		)
	}
	if replayed, found, err := s.FindReceipt(
		ctx, noop.IdempotencyKey, noop.CommandName, noop.CommandDigest,
	); err != nil || found {
		return replayed, err
	}
	record := documentFromSnapshot(noop.Aggregate.Snapshot())
	expiresAt := receiptExpiry(noop.ReceiptExpiresAt)
	_, err := s.receipts.InsertOne(ctx, receiptDocument{
		ID:               strings.TrimSpace(noop.IdempotencyKey),
		AggregateID:      record.ID,
		AggregateVersion: record.Version,
		CommandName:      strings.TrimSpace(noop.CommandName),
		CommandDigest:    strings.TrimSpace(noop.CommandDigest),
		Result:           record,
		CreatedAt:        time.Now().UTC(),
		ExpiresAt:        expiresAt,
	})
	if err != nil {
		if mongo.IsDuplicateKeyError(err) {
			replayed, found, replayErr := s.FindReceipt(
				ctx, noop.IdempotencyKey, noop.CommandName, noop.CommandDigest,
			)
			if replayErr != nil || found {
				return replayed, replayErr
			}
		}
		return claimports.CommitResult{}, err
	}
	aggregate, err := record.aggregate()
	return claimports.CommitResult{Aggregate: aggregate}, err
}

func (s *MongoStore) Commit(
	ctx context.Context,
	commit claimports.Commit,
) (claimports.CommitResult, error) {
	if err := validateCommit(commit); err != nil {
		return claimports.CommitResult{}, err
	}
	if !s.supportsTxn {
		return s.commitBody(ctx, commit)
	}
	session, err := s.claims.Database().Client().StartSession()
	if err != nil {
		return claimports.CommitResult{}, err
	}
	defer session.EndSession(ctx)
	var result claimports.CommitResult
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		committed, txErr := s.commitBody(txCtx, commit)
		if txErr == nil {
			result = committed
		}
		return nil, txErr
	})
	if err == nil {
		return result, nil
	}
	replayed, found, receiptErr := s.FindReceipt(
		ctx, commit.IdempotencyKey, commit.CommandName, commit.CommandDigest,
	)
	if receiptErr != nil {
		return claimports.CommitResult{}, receiptErr
	}
	if found {
		return replayed, nil
	}
	return claimports.CommitResult{}, err
}

// commitBody 也供 alpha 单节点 Mongo 使用；CAS 仍原子，生产环境启用事务。
func (s *MongoStore) commitBody(
	ctx context.Context,
	commit claimports.Commit,
) (claimports.CommitResult, error) {
	if receipt, found, err := s.findReceipt(ctx, commit.IdempotencyKey); err != nil {
		return claimports.CommitResult{}, err
	} else if found && receipt.ExpiresAt.After(time.Now().UTC()) {
		if receipt.CommandName != commit.CommandName || receipt.CommandDigest != commit.CommandDigest {
			return claimports.CommitResult{}, generated.AppErrorFromIdempotencyConflict(
				"idempotency key was reused with a different homepage claim command",
			)
		}
		aggregate, err := receipt.Result.aggregate()
		return claimports.CommitResult{Aggregate: aggregate, Replayed: true}, err
	} else if found {
		if _, err := s.receipts.DeleteOne(ctx, bson.M{"_id": receipt.ID}); err != nil {
			return claimports.CommitResult{}, err
		}
	}

	record := documentFromSnapshot(commit.Aggregate.Snapshot())
	if commit.ExpectedVersion == 0 {
		if _, err := s.claims.InsertOne(ctx, record); err != nil {
			if mongo.IsDuplicateKeyError(err) {
				return claimports.CommitResult{}, generated.AppErrorFromDuplicatePendingClaim(
					"a pending claim request already exists for this persona and homepage",
				)
			}
			return claimports.CommitResult{}, err
		}
	} else {
		result, err := s.claims.ReplaceOne(
			ctx,
			bson.M{"_id": record.ID, "version": commit.ExpectedVersion},
			record,
		)
		if err != nil {
			return claimports.CommitResult{}, err
		}
		if result.MatchedCount != 1 {
			return claimports.CommitResult{}, generated.AppErrorFromVersionConflict(
				"homepage claim request version changed before commit",
			)
		}
	}
	for _, event := range commit.Events {
		if _, err := s.outbox.InsertOne(ctx, outboxDocument{
			ID:               event.EventID,
			EventType:        event.EventType,
			AggregateID:      event.AggregateID,
			AggregateVersion: event.AggregateVersion,
			Payload:          append([]byte(nil), event.Payload...),
			OccurredAt:       event.OccurredAt.UTC(),
		}); err != nil {
			return claimports.CommitResult{}, err
		}
	}
	if _, err := s.receipts.InsertOne(ctx, receiptDocument{
		ID:               commit.IdempotencyKey,
		AggregateID:      record.ID,
		AggregateVersion: record.Version,
		CommandName:      commit.CommandName,
		CommandDigest:    commit.CommandDigest,
		Result:           record,
		CreatedAt:        time.Now().UTC(),
		ExpiresAt:        receiptExpiry(commit.ReceiptExpiresAt),
	}); err != nil {
		return claimports.CommitResult{}, err
	}
	aggregate, err := record.aggregate()
	return claimports.CommitResult{Aggregate: aggregate}, err
}

func validateCommit(commit claimports.Commit) error {
	if commit.Aggregate == nil || strings.TrimSpace(commit.Aggregate.ID()) == "" {
		return generated.AppErrorFromVersionConflict("homepage claim commit requires aggregate")
	}
	if commit.ExpectedVersion < 0 ||
		commit.Aggregate.Version() != commit.ExpectedVersion+1 {
		return generated.AppErrorFromVersionConflict(
			"homepage claim aggregate version does not follow expected version",
		)
	}
	if strings.TrimSpace(commit.IdempotencyKey) == "" ||
		strings.TrimSpace(commit.CommandName) == "" ||
		strings.TrimSpace(commit.CommandDigest) == "" {
		return generated.AppErrorFromIdempotencyConflict(
			"homepage claim commit requires idempotency identity",
		)
	}
	if len(commit.Events) != 1 {
		return generated.AppErrorFromVersionConflict(
			"homepage claim commit requires exactly one outbox fact",
		)
	}
	event := commit.Events[0]
	if event.EventID == "" || event.EventType == "" || len(event.Payload) == 0 ||
		event.AggregateID != commit.Aggregate.ID() ||
		event.AggregateVersion != commit.Aggregate.Version() ||
		event.OccurredAt.IsZero() {
		return generated.AppErrorFromVersionConflict(
			"homepage claim outbox fact does not match aggregate commit",
		)
	}
	return nil
}

func (s *MongoStore) ReadAfter(
	ctx context.Context,
	checkpoint string,
	limit int,
) ([]claimports.OutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	filter := bson.M{}
	if checkpoint = strings.TrimSpace(checkpoint); checkpoint != "" {
		var previous outboxDocument
		if err := s.outbox.FindOne(ctx, bson.M{"_id": checkpoint}).Decode(&previous); err != nil {
			return nil, err
		}
		filter["$or"] = bson.A{
			bson.M{"occurredAt": bson.M{"$gt": previous.OccurredAt}},
			bson.M{"occurredAt": previous.OccurredAt, "_id": bson.M{"$gt": previous.ID}},
		}
	}
	cursor, err := s.outbox.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "occurredAt", Value: 1}, {Key: "_id", Value: 1}}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, err
	}
	defer func() { _ = cursor.Close(ctx) }()
	var documents []outboxDocument
	if err := cursor.All(ctx, &documents); err != nil {
		return nil, err
	}
	events := make([]claimports.OutboxEvent, 0, len(documents))
	for _, document := range documents {
		events = append(events, claimports.OutboxEvent{
			EventID:          document.ID,
			EventType:        document.EventType,
			AggregateID:      document.AggregateID,
			AggregateVersion: document.AggregateVersion,
			Payload:          append([]byte(nil), document.Payload...),
			OccurredAt:       document.OccurredAt,
		})
	}
	return events, nil
}

type checkpointDocument struct {
	ID         string    `bson:"_id"`
	Checkpoint string    `bson:"checkpoint"`
	UpdatedAt  time.Time `bson:"updatedAt"`
}

func (s *MongoStore) LoadCheckpoint(ctx context.Context, consumer string) (string, error) {
	var document checkpointDocument
	err := s.checkpoints.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(consumer)},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return "", nil
	}
	return document.Checkpoint, err
}

func (s *MongoStore) SaveCheckpoint(ctx context.Context, consumer, checkpoint string) error {
	_, err := s.checkpoints.UpdateOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(consumer)},
		bson.M{"$set": bson.M{
			"checkpoint": strings.TrimSpace(checkpoint),
			"updatedAt":  time.Now().UTC(),
		}},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

func receiptExpiry(value time.Time) time.Time {
	if value.IsZero() {
		return time.Now().UTC().Add(24 * time.Hour)
	}
	return value.UTC()
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}
