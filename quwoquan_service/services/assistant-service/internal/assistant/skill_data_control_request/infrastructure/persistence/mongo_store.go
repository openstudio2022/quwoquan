package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/ports"
)

type Store struct {
	requests *mongo.Collection
	receipts *mongo.Collection
	outbox   *mongo.Collection
}

var _ ports.Store = (*Store)(nil)

type commandReceiptDocument struct {
	ID            string    `bson:"_id"`
	AccountID     string    `bson:"accountId"`
	CommandID     string    `bson:"commandId"`
	CommandKind   string    `bson:"commandKind"`
	RequestDigest string    `bson:"requestDigest"`
	RequestID     string    `bson:"requestId"`
	CreatedAt     time.Time `bson:"createdAt"`
}

type outboxDocument struct {
	ID                string        `bson:"_id"`
	EventType         string        `bson:"eventType"`
	RequestID         string        `bson:"requestId"`
	AggregateRevision int64         `bson:"aggregateRevision"`
	Payload           model.Request `bson:"payload"`
	OccurredAt        time.Time     `bson:"occurredAt"`
	PublishedAt       *time.Time    `bson:"publishedAt,omitempty"`
}

func NewStore(database *mongo.Database) *Store {
	if database == nil {
		panic("skill data control database is required")
	}
	return &Store{
		requests: database.Collection("skill_data_control_requests"),
		receipts: database.Collection("skill_data_control_command_receipts"),
		outbox:   database.Collection("skill_data_control_outbox"),
	}
}

func (store *Store) EnsureIndexes(ctx context.Context) error {
	if _, err := store.requests.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "accountId", Value: 1},
				{Key: "skillId", Value: 1},
				{Key: "updatedAt", Value: -1},
			},
			Options: options.Index().SetName("idx_skill_data_control_owner_skill_updated"),
		},
		{
			Keys: bson.D{
				{Key: "status", Value: 1},
				{Key: "leaseExpiresAt", Value: 1},
				{Key: "updatedAt", Value: 1},
			},
			Options: options.Index().SetName("idx_skill_data_control_execution_recovery"),
		},
	}); err != nil {
		return unavailable("create request indexes", err)
	}
	if _, err := store.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "accountId", Value: 1}, {Key: "commandId", Value: 1}},
		Options: options.Index().
			SetName("uq_skill_data_control_command_receipt").
			SetUnique(true),
	}); err != nil {
		return unavailable("create receipt index", err)
	}
	if _, err := store.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "requestId", Value: 1},
				{Key: "aggregateRevision", Value: 1},
				{Key: "eventType", Value: 1},
			},
			Options: options.Index().
				SetName("uq_skill_data_control_outbox_revision").
				SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "publishedAt", Value: 1}, {Key: "occurredAt", Value: 1}},
			Options: options.Index().SetName("idx_skill_data_control_outbox_pending"),
		},
		{
			Keys: bson.D{
				{Key: "payload.accountId", Value: 1},
				{Key: "payload.skillId", Value: 1},
				{Key: "occurredAt", Value: -1},
				{Key: "_id", Value: -1},
			},
			Options: options.Index().SetName("idx_skill_data_control_outbox_activity"),
		},
	}); err != nil {
		return unavailable("create outbox indexes", err)
	}
	return nil
}

func (store *Store) Create(
	ctx context.Context,
	command model.CreateCommand,
) (model.MutationResult, error) {
	if err := command.Request.Validate(); err != nil ||
		strings.TrimSpace(command.IdempotencyKey) == "" ||
		strings.TrimSpace(command.RequestDigest) == "" {
		return model.MutationResult{}, model.ErrInvalidArgument
	}
	return store.withCommandTransaction(
		ctx,
		command.Request.AccountID,
		command.IdempotencyKey,
		model.CommandCreate,
		command.RequestDigest,
		func(txCtx context.Context) (model.Request, error) {
			if _, err := store.requests.InsertOne(txCtx, command.Request); err != nil {
				return model.Request{}, err
			}
			if err := store.insertOutbox(txCtx, model.EventRequested, command.Request); err != nil {
				return model.Request{}, err
			}
			return command.Request, nil
		},
	)
}

func (store *Store) Confirm(
	ctx context.Context,
	command model.ConfirmCommand,
) (model.MutationResult, error) {
	return store.withCommandTransaction(
		ctx,
		command.AccountID,
		command.IdempotencyKey,
		model.CommandConfirm,
		command.RequestDigest,
		func(txCtx context.Context) (model.Request, error) {
			current, err := store.get(txCtx, command.AccountID, command.RequestID)
			if err != nil {
				return model.Request{}, err
			}
			if current.Revision != command.ExpectedRevision {
				return model.Request{}, model.ErrRevisionConflict
			}
			if current.Status != model.StatusPendingConfirmation &&
				current.Status != model.StatusFailed {
				return model.Request{}, model.ErrRevisionConflict
			}
			next := current
			next.Revision++
			next.UpdatedAt = command.OccurredAt.UTC()
			eventType := model.EventConfirmed
			if command.Confirmed {
				next.Status = model.StatusExecuting
				confirmedAt := command.OccurredAt.UTC()
				next.ConfirmedAt = &confirmedAt
				next.CompletedAt = nil
				next.FailedAction = ""
				next.FailureCode = ""
				next.LeaseOwner = ""
				next.LeaseExpiresAt = nil
				next.LeaseHeartbeatAt = nil
			} else {
				next.Status = model.StatusCancelled
				next.FailedAction = ""
				next.FailureCode = ""
				next.LeaseOwner = ""
				next.LeaseExpiresAt = nil
				next.LeaseHeartbeatAt = nil
				completedAt := command.OccurredAt.UTC()
				next.CompletedAt = &completedAt
				eventType = model.EventCancelled
			}
			if err := store.replaceAtRevision(txCtx, next, current.Revision); err != nil {
				return model.Request{}, err
			}
			if err := store.insertOutbox(txCtx, eventType, next); err != nil {
				return model.Request{}, err
			}
			return next, nil
		},
	)
}

func (store *Store) withCommandTransaction(
	ctx context.Context,
	accountID string,
	commandID string,
	commandKind string,
	requestDigest string,
	mutate func(context.Context) (model.Request, error),
) (model.MutationResult, error) {
	accountID = strings.TrimSpace(accountID)
	commandID = strings.TrimSpace(commandID)
	commandKind = strings.TrimSpace(commandKind)
	requestDigest = strings.TrimSpace(requestDigest)
	if accountID == "" || commandID == "" || commandKind == "" || requestDigest == "" {
		return model.MutationResult{}, model.ErrInvalidArgument
	}
	session, err := store.requests.Database().Client().StartSession()
	if err != nil {
		return model.MutationResult{}, unavailable("start command transaction", err)
	}
	defer session.EndSession(ctx)
	var result model.Request
	replayed := false
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		receipt, found, err := store.readReceipt(txCtx, accountID, commandID)
		if err != nil {
			return nil, err
		}
		if found {
			if receipt.CommandKind != commandKind || receipt.RequestDigest != requestDigest {
				return nil, model.ErrIdempotencyConflict
			}
			result, err = store.get(txCtx, accountID, receipt.RequestID)
			if err != nil {
				return nil, err
			}
			replayed = true
			return nil, nil
		}
		result, err = mutate(txCtx)
		if err != nil {
			return nil, err
		}
		_, err = store.receipts.InsertOne(txCtx, commandReceiptDocument{
			ID:            uuid.NewString(),
			AccountID:     accountID,
			CommandID:     commandID,
			CommandKind:   commandKind,
			RequestDigest: requestDigest,
			RequestID:     result.RequestID,
			CreatedAt:     result.UpdatedAt.UTC(),
		})
		return nil, err
	})
	if err != nil {
		switch {
		case errors.Is(err, model.ErrInvalidArgument),
			errors.Is(err, model.ErrNotFound),
			errors.Is(err, model.ErrRevisionConflict),
			errors.Is(err, model.ErrIdempotencyConflict):
			return model.MutationResult{}, err
		default:
			return model.MutationResult{}, unavailable("commit command transaction", err)
		}
	}
	return model.MutationResult{Request: result, Replayed: replayed}, nil
}

func (store *Store) Get(
	ctx context.Context,
	accountID string,
	requestID string,
) (model.Request, error) {
	return store.get(ctx, strings.TrimSpace(accountID), strings.TrimSpace(requestID))
}

func (store *Store) ClaimNextExecution(
	ctx context.Context,
	workerID string,
	now time.Time,
	leaseTTL time.Duration,
) (model.ExecutionClaim, bool, error) {
	workerID = strings.TrimSpace(workerID)
	now = now.UTC()
	if workerID == "" || now.IsZero() || leaseTTL <= 0 {
		return model.ExecutionClaim{}, false, model.ErrInvalidArgument
	}
	filter := bson.M{
		"status": model.StatusExecuting,
		"$or": bson.A{
			bson.M{"leaseOwner": bson.M{"$exists": false}},
			bson.M{"leaseOwner": ""},
			bson.M{"leaseExpiresAt": bson.M{"$exists": false}},
			bson.M{"leaseExpiresAt": bson.M{"$lte": now}},
		},
	}
	update := bson.M{
		"$set": bson.M{
			"leaseOwner":       workerID,
			"leaseHeartbeatAt": now,
			"leaseExpiresAt":   now.Add(leaseTTL),
		},
		"$inc": bson.M{"leaseToken": int64(1)},
	}
	var request model.Request
	err := store.requests.FindOneAndUpdate(
		ctx,
		filter,
		update,
		options.FindOneAndUpdate().
			SetSort(bson.D{{Key: "updatedAt", Value: 1}, {Key: "_id", Value: 1}}).
			SetReturnDocument(options.After),
	).Decode(&request)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.ExecutionClaim{}, false, nil
	}
	if err != nil {
		return model.ExecutionClaim{}, false, unavailable("claim execution", err)
	}
	fence, err := model.NewExecutionFence(request)
	if err != nil {
		return model.ExecutionClaim{}, false, unavailable("validate execution claim", err)
	}
	return model.ExecutionClaim{Request: request, Fence: fence}, true, nil
}

func (store *Store) HeartbeatExecution(
	ctx context.Context,
	fence model.ExecutionFence,
	now time.Time,
	leaseTTL time.Duration,
) (model.ExecutionFence, error) {
	now = now.UTC()
	if err := validateFenceInput(fence, now); err != nil || leaseTTL <= 0 {
		return model.ExecutionFence{}, model.ErrInvalidArgument
	}
	var request model.Request
	err := store.requests.FindOneAndUpdate(
		ctx,
		fenceFilter(fence, now),
		bson.M{"$set": bson.M{
			"leaseHeartbeatAt": now,
			"leaseExpiresAt":   now.Add(leaseTTL),
		}},
		options.FindOneAndUpdate().SetReturnDocument(options.After),
	).Decode(&request)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.ExecutionFence{}, model.ErrRevisionConflict
	}
	if err != nil {
		return model.ExecutionFence{}, unavailable("heartbeat execution", err)
	}
	next, err := model.NewExecutionFence(request)
	if err != nil {
		return model.ExecutionFence{}, unavailable("validate execution heartbeat", err)
	}
	return next, nil
}

func (store *Store) get(
	ctx context.Context,
	accountID string,
	requestID string,
) (model.Request, error) {
	var request model.Request
	err := store.requests.FindOne(ctx, bson.M{
		"_id":       requestID,
		"accountId": accountID,
	}).Decode(&request)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Request{}, model.ErrNotFound
	}
	if err != nil {
		return model.Request{}, unavailable("get request", err)
	}
	if err := request.Validate(); err != nil {
		return model.Request{}, unavailable("validate stored request", err)
	}
	return request, nil
}

func (store *Store) MarkActionCompleted(
	ctx context.Context,
	fence model.ExecutionFence,
	action string,
	expectedRevision int64,
	at time.Time,
) (model.Request, error) {
	at = at.UTC()
	if err := validateFenceInput(fence, at); err != nil || expectedRevision < 1 {
		return model.Request{}, model.ErrInvalidArgument
	}
	current, err := store.get(ctx, fence.AccountID, fence.RequestID)
	if err != nil {
		return model.Request{}, err
	}
	if current.Revision != expectedRevision || !requestOwnsFence(current, fence, at) {
		return model.Request{}, model.ErrRevisionConflict
	}
	if !contains(current.RequestedActions, action) {
		return model.Request{}, model.ErrInvalidArgument
	}
	if current.HasCompleted(action) {
		return current, nil
	}
	next := current
	next.CompletedActions = append(append([]string(nil), current.CompletedActions...), action)
	next.Revision++
	next.UpdatedAt = at
	if err := store.replaceAtFence(ctx, next, fence, expectedRevision, at); err != nil {
		return model.Request{}, err
	}
	return next, nil
}

func (store *Store) MarkCompleted(
	ctx context.Context,
	fence model.ExecutionFence,
	expectedRevision int64,
	at time.Time,
) (model.Request, error) {
	return store.finish(
		ctx, fence, "", "", model.StatusCompleted,
		model.EventCompleted, expectedRevision, at,
	)
}

func (store *Store) MarkFailed(
	ctx context.Context,
	fence model.ExecutionFence,
	action string,
	failureCode string,
	expectedRevision int64,
	at time.Time,
) (model.Request, error) {
	if strings.TrimSpace(action) == "" || strings.TrimSpace(failureCode) == "" {
		return model.Request{}, model.ErrInvalidArgument
	}
	return store.finish(
		ctx, fence, action, failureCode, model.StatusFailed,
		model.EventFailed, expectedRevision, at,
	)
}

func (store *Store) finish(
	ctx context.Context,
	fence model.ExecutionFence,
	failedAction string,
	failureCode string,
	status string,
	eventType string,
	expectedRevision int64,
	at time.Time,
) (model.Request, error) {
	at = at.UTC()
	if err := validateFenceInput(fence, at); err != nil || expectedRevision < 1 {
		return model.Request{}, model.ErrInvalidArgument
	}
	session, err := store.requests.Database().Client().StartSession()
	if err != nil {
		return model.Request{}, unavailable("start finish transaction", err)
	}
	defer session.EndSession(ctx)
	var next model.Request
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		current, err := store.get(txCtx, fence.AccountID, fence.RequestID)
		if err != nil {
			return nil, err
		}
		if current.Revision != expectedRevision || !requestOwnsFence(current, fence, at) {
			return nil, model.ErrRevisionConflict
		}
		if status == model.StatusCompleted &&
			len(current.CompletedActions) != len(current.RequestedActions) {
			return nil, model.ErrInvalidArgument
		}
		next = current
		next.Status = status
		next.FailedAction = strings.TrimSpace(failedAction)
		next.FailureCode = strings.TrimSpace(failureCode)
		next.Revision++
		next.UpdatedAt = at
		next.LeaseOwner = ""
		next.LeaseExpiresAt = nil
		next.LeaseHeartbeatAt = nil
		if status == model.StatusCompleted {
			completedAt := at
			next.CompletedAt = &completedAt
		}
		if err := store.replaceAtFence(
			txCtx, next, fence, current.Revision, at,
		); err != nil {
			return nil, err
		}
		return nil, store.insertOutbox(txCtx, eventType, next)
	})
	if err != nil {
		switch {
		case errors.Is(err, model.ErrNotFound),
			errors.Is(err, model.ErrRevisionConflict),
			errors.Is(err, model.ErrInvalidArgument):
			return model.Request{}, err
		default:
			return model.Request{}, unavailable("commit finish transaction", err)
		}
	}
	return next, nil
}

func (store *Store) replaceAtFence(
	ctx context.Context,
	next model.Request,
	fence model.ExecutionFence,
	expectedRevision int64,
	now time.Time,
) error {
	if err := next.Validate(); err != nil {
		return err
	}
	filter := fenceFilter(fence, now)
	filter["revision"] = expectedRevision
	result, err := store.requests.ReplaceOne(ctx, filter, next)
	if err != nil {
		return err
	}
	if result.ModifiedCount != 1 {
		return model.ErrRevisionConflict
	}
	return nil
}

func validateFenceInput(fence model.ExecutionFence, now time.Time) error {
	if strings.TrimSpace(fence.AccountID) == "" ||
		strings.TrimSpace(fence.RequestID) == "" ||
		strings.TrimSpace(fence.WorkerID) == "" ||
		fence.Token < 1 || fence.LeaseExpiresAt.IsZero() || now.IsZero() {
		return model.ErrInvalidArgument
	}
	return nil
}

func fenceFilter(fence model.ExecutionFence, now time.Time) bson.M {
	return bson.M{
		"_id":            fence.RequestID,
		"accountId":      fence.AccountID,
		"status":         model.StatusExecuting,
		"leaseOwner":     fence.WorkerID,
		"leaseToken":     fence.Token,
		"leaseExpiresAt": bson.M{"$gt": now.UTC()},
	}
}

func requestOwnsFence(
	request model.Request,
	fence model.ExecutionFence,
	now time.Time,
) bool {
	return request.Status == model.StatusExecuting &&
		request.LeaseOwner == fence.WorkerID &&
		request.LeaseToken == fence.Token &&
		request.LeaseExpiresAt != nil && request.LeaseExpiresAt.After(now.UTC())
}

func (store *Store) replaceAtRevision(
	ctx context.Context,
	next model.Request,
	expectedRevision int64,
) error {
	if err := next.Validate(); err != nil {
		return err
	}
	result, err := store.requests.ReplaceOne(
		ctx,
		bson.M{
			"_id":       next.RequestID,
			"accountId": next.AccountID,
			"revision":  expectedRevision,
		},
		next,
	)
	if err != nil {
		return err
	}
	if result.ModifiedCount != 1 {
		return model.ErrRevisionConflict
	}
	return nil
}

func (store *Store) readReceipt(
	ctx context.Context,
	accountID string,
	commandID string,
) (commandReceiptDocument, bool, error) {
	var receipt commandReceiptDocument
	err := store.receipts.FindOne(ctx, bson.M{
		"accountId": accountID,
		"commandId": commandID,
	}).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return commandReceiptDocument{}, false, nil
	}
	if err != nil {
		return commandReceiptDocument{}, false, err
	}
	return receipt, true, nil
}

func (store *Store) insertOutbox(
	ctx context.Context,
	eventType string,
	request model.Request,
) error {
	_, err := store.outbox.InsertOne(ctx, outboxDocument{
		ID:                uuid.NewString(),
		EventType:         eventType,
		RequestID:         request.RequestID,
		AggregateRevision: request.Revision,
		Payload:           request,
		OccurredAt:        request.UpdatedAt.UTC(),
	})
	return err
}

func (store *Store) ListSkillDataControlActivities(
	ctx context.Context,
	accountID string,
	skillID string,
	limit int,
) ([]model.ActivityEvent, error) {
	accountID = strings.TrimSpace(accountID)
	skillID = strings.TrimSpace(skillID)
	if accountID == "" || skillID == "" {
		return nil, model.ErrInvalidArgument
	}
	if limit <= 0 || limit > 100 {
		limit = 100
	}
	cursor, err := store.outbox.Find(
		ctx,
		bson.M{"payload.accountId": accountID, "payload.skillId": skillID},
		options.Find().
			SetSort(bson.D{{Key: "occurredAt", Value: -1}, {Key: "_id", Value: -1}}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, unavailable("list data control activity", err)
	}
	defer cursor.Close(ctx)
	documents := []outboxDocument{}
	if err := cursor.All(ctx, &documents); err != nil {
		return nil, unavailable("decode data control activity", err)
	}
	events := make([]model.ActivityEvent, 0, len(documents))
	for _, document := range documents {
		request := document.Payload
		if request.AccountID != accountID || request.SkillID != skillID {
			return nil, unavailable(
				"validate data control activity",
				errors.New("stored data control event violates owner boundary"),
			)
		}
		events = append(events, model.ActivityEvent{
			EventID:      document.ID,
			EventType:    document.EventType,
			RequestID:    document.RequestID,
			AccountID:    accountID,
			SkillID:      skillID,
			Status:       request.Status,
			FailedAction: request.FailedAction,
			FailureCode:  request.FailureCode,
			Revision:     document.AggregateRevision,
			OccurredAt:   document.OccurredAt.UTC(),
		})
	}
	return events, nil
}

func unavailable(stage string, err error) error {
	return fmt.Errorf("%w: %s: %v", model.ErrStorageUnavailable, stage, err)
}

func contains(values []string, value string) bool {
	value = strings.TrimSpace(value)
	for _, candidate := range values {
		if candidate == value {
			return true
		}
	}
	return false
}
