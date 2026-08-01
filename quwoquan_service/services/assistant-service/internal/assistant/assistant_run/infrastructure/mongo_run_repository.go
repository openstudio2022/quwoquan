package infrastructure

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

const runJournalRetention = 7 * 24 * time.Hour

type runDocument struct {
	ID              string         `bson:"_id"`
	UserID          string         `bson:"userId"`
	SessionID       string         `bson:"sessionId"`
	ClientRequestID string         `bson:"clientRequestId"`
	Revision        int64          `bson:"runRevision"`
	State           string         `bson:"status"`
	Snapshot        runruntime.Run `bson:"snapshot"`
	CreatedAt       time.Time      `bson:"createdAt"`
	UpdatedAt       time.Time      `bson:"updatedAt"`
}

type journalDocument struct {
	ID        string         `bson:"_id"`
	RunID     string         `bson:"runId"`
	Sequence  int64          `bson:"seq"`
	Revision  int64          `bson:"runRevision"`
	Kind      string         `bson:"eventType"`
	Payload   map[string]any `bson:"payload"`
	CreatedAt time.Time      `bson:"createdAt"`
	ExpiresAt time.Time      `bson:"expiresAt"`
}

type commandReceiptDocument struct {
	ID            string    `bson:"_id"`
	RunID         string    `bson:"runId"`
	CommandID     string    `bson:"commandId"`
	CommandKind   string    `bson:"commandKind"`
	PayloadDigest string    `bson:"payloadDigest"`
	Revision      int64     `bson:"runRevision"`
	CreatedAt     time.Time `bson:"createdAt"`
}

type leaseDocument struct {
	ID           string    `bson:"_id"`
	LeaseID      string    `bson:"leaseId"`
	WorkerID     string    `bson:"workerId"`
	FencingToken int64     `bson:"fencingToken"`
	AcquiredAt   time.Time `bson:"acquiredAt"`
	HeartbeatAt  time.Time `bson:"heartbeatAt"`
	ExpiresAt    time.Time `bson:"expiresAt"`
}

type workDocument struct {
	ID           string    `bson:"_id"`
	Status       string    `bson:"status"`
	WorkerID     string    `bson:"workerId,omitempty"`
	FencingToken int64     `bson:"fencingToken"`
	AvailableAt  time.Time `bson:"availableAt"`
	ClaimedAt    time.Time `bson:"claimedAt,omitempty"`
	ExpiresAt    time.Time `bson:"expiresAt,omitempty"`
	UpdatedAt    time.Time `bson:"updatedAt"`
}

// MongoRunRepository is the authoritative AssistantRun snapshot, ordered
// journal, and worker-lease store. Snapshot and journal changes commit in one
// Mongo transaction so a reconnect never observes a state without its events.
type MongoRunRepository struct {
	runs     *mongo.Collection
	events   *mongo.Collection
	receipts *mongo.Collection
	leases   *mongo.Collection
	work     *mongo.Collection
}

func NewMongoRunRepository(database *mongo.Database) *MongoRunRepository {
	if database == nil {
		panic("assistant run database is required")
	}
	return &MongoRunRepository{
		runs:     database.Collection("assistant_runs"),
		events:   database.Collection("assistant_run_events"),
		receipts: database.Collection("assistant_run_command_receipts"),
		leases:   database.Collection("assistant_run_worker_leases"),
		work:     database.Collection("assistant_run_work_queue"),
	}
}

func (r *MongoRunRepository) EnsureIndexes(ctx context.Context) error {
	if _, err := r.runs.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "userId", Value: 1},
				{Key: "sessionId", Value: 1},
				{Key: "clientRequestId", Value: 1},
			},
			Options: options.Index().SetName("uq_runs_client_request").
				SetUnique(true).
				SetPartialFilterExpression(bson.M{
					"clientRequestId": bson.M{"$type": "string"},
				}),
		},
		{
			Keys:    bson.D{{Key: "userId", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_runs_user_created"),
		},
		{
			Keys:    bson.D{{Key: "sessionId", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_runs_session"),
		},
		{
			Keys:    bson.D{{Key: "status", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_runs_status"),
		},
	}); err != nil {
		return fmt.Errorf("create assistant run indexes: %w", err)
	}
	if _, err := r.events.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "runId", Value: 1}, {Key: "seq", Value: 1}},
			Options: options.Index().SetName("uq_run_events_run_seq").SetUnique(true),
		},
		{
			Keys: bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().SetName("idx_run_events_expire").
				SetExpireAfterSeconds(0),
		},
	}); err != nil {
		return fmt.Errorf("create assistant run event indexes: %w", err)
	}
	if _, err := r.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "runId", Value: 1},
			{Key: "commandId", Value: 1},
		},
		Options: options.Index().
			SetName("uq_run_command_receipt").
			SetUnique(true),
	}); err != nil {
		return fmt.Errorf("create assistant run command receipt index: %w", err)
	}
	if _, err := r.leases.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "expiresAt", Value: 1}},
		Options: options.Index().SetName("idx_run_worker_lease_expiry"),
	}); err != nil {
		return fmt.Errorf("create assistant run lease indexes: %w", err)
	}
	if _, err := r.work.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "status", Value: 1},
			{Key: "availableAt", Value: 1},
			{Key: "expiresAt", Value: 1},
		},
		Options: options.Index().SetName("idx_run_work_ready"),
	}); err != nil {
		return fmt.Errorf("create assistant run work queue indexes: %w", err)
	}
	return nil
}

func (r *MongoRunRepository) Load(
	ctx context.Context,
	runID string,
) (runruntime.Run, error) {
	return r.load(ctx, bson.M{"_id": strings.TrimSpace(runID)})
}

func (r *MongoRunRepository) LoadByRequest(
	ctx context.Context,
	userID string,
	sessionID string,
	clientRequestID string,
) (runruntime.Run, error) {
	return r.load(ctx, bson.M{
		"userId":          strings.TrimSpace(userID),
		"sessionId":       strings.TrimSpace(sessionID),
		"clientRequestId": strings.TrimSpace(clientRequestID),
	})
}

func (r *MongoRunRepository) LoadCommandReceipt(
	ctx context.Context,
	runID string,
	commandID string,
) (runruntime.CommandReceipt, error) {
	var document commandReceiptDocument
	err := r.receipts.FindOne(ctx, bson.M{
		"runId":     strings.TrimSpace(runID),
		"commandId": strings.TrimSpace(commandID),
	}).Decode(&document)
	if err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return runruntime.CommandReceipt{}, runruntime.ErrRunNotFound
		}
		return runruntime.CommandReceipt{}, fmt.Errorf(
			"load assistant run command receipt: %w",
			err,
		)
	}
	return runruntime.CommandReceipt{
		RunID:         document.RunID,
		CommandID:     document.CommandID,
		CommandKind:   document.CommandKind,
		PayloadDigest: document.PayloadDigest,
		Revision:      document.Revision,
		CreatedAt:     document.CreatedAt,
	}, nil
}

func (r *MongoRunRepository) load(
	ctx context.Context,
	filter bson.M,
) (runruntime.Run, error) {
	var document runDocument
	if err := r.runs.FindOne(ctx, filter).Decode(&document); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return runruntime.Run{}, runruntime.ErrRunNotFound
		}
		return runruntime.Run{}, fmt.Errorf("load assistant run: %w", err)
	}
	return document.Snapshot, nil
}

func (r *MongoRunRepository) Commit(
	ctx context.Context,
	expectedRevision int64,
	run runruntime.Run,
	events []runruntime.JournalEvent,
	receipt *runruntime.CommandReceipt,
) error {
	if expectedRevision > 0 {
		var current struct {
			Revision int64 `bson:"runRevision"`
		}
		err := r.runs.FindOne(
			ctx,
			bson.M{"_id": strings.TrimSpace(run.RunID)},
			options.FindOne().SetProjection(bson.M{"runRevision": 1}),
		).Decode(&current)
		if errors.Is(err, mongo.ErrNoDocuments) ||
			(err == nil && current.Revision != expectedRevision) {
			return runruntime.ErrRevisionConflict
		}
		if err != nil {
			return fmt.Errorf("read assistant run revision: %w", err)
		}
	}
	document, eventDocuments, err := normalizeCommit(expectedRevision, run, events)
	if err != nil {
		return err
	}
	receiptDocument, err := normalizeCommandReceipt(run, receipt)
	if err != nil {
		return err
	}
	session, err := r.runs.Database().Client().StartSession()
	if err != nil {
		return fmt.Errorf("start assistant run transaction: %w", err)
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if expectedRevision == 0 {
			if _, insertErr := r.runs.InsertOne(txCtx, document); insertErr != nil {
				if mongo.IsDuplicateKeyError(insertErr) {
					return nil, runruntime.ErrRevisionConflict
				}
				return nil, insertErr
			}
		} else {
			result, updateErr := r.runs.ReplaceOne(
				txCtx,
				bson.M{"_id": document.ID, "runRevision": expectedRevision},
				document,
			)
			if updateErr != nil {
				return nil, updateErr
			}
			if result.MatchedCount != 1 {
				return nil, runruntime.ErrRevisionConflict
			}
		}
		if len(eventDocuments) > 0 {
			values := make([]any, len(eventDocuments))
			for index := range eventDocuments {
				values[index] = eventDocuments[index]
			}
			if _, insertErr := r.events.InsertMany(txCtx, values); insertErr != nil {
				if mongo.IsDuplicateKeyError(insertErr) {
					return nil, runruntime.ErrRevisionConflict
				}
				return nil, insertErr
			}
		}
		if receiptDocument != nil {
			if _, insertErr := r.receipts.InsertOne(
				txCtx,
				*receiptDocument,
			); insertErr != nil {
				if mongo.IsDuplicateKeyError(insertErr) {
					return nil, runruntime.ErrRevisionConflict
				}
				return nil, insertErr
			}
		}
		if queueRunnable(run.State.WireName()) {
			if _, queueErr := r.work.UpdateOne(
				txCtx,
				bson.M{"_id": document.ID},
				bson.M{"$setOnInsert": bson.M{
					"status":       "ready",
					"fencingToken": int64(0),
					"availableAt":  run.UpdatedAt.UTC(),
					"updatedAt":    run.UpdatedAt.UTC(),
				}},
				options.UpdateOne().SetUpsert(true),
			); queueErr != nil {
				return nil, queueErr
			}
		} else {
			if _, queueErr := r.work.DeleteOne(
				txCtx,
				bson.M{"_id": document.ID},
			); queueErr != nil {
				return nil, queueErr
			}
		}
		return nil, nil
	})
	if err != nil {
		if errors.Is(err, runruntime.ErrRevisionConflict) {
			return err
		}
		return fmt.Errorf("commit assistant run: %w", err)
	}
	return nil
}

func normalizeCommit(
	expectedRevision int64,
	run runruntime.Run,
	events []runruntime.JournalEvent,
) (runDocument, []journalDocument, error) {
	runID := strings.TrimSpace(run.RunID)
	if runID == "" ||
		strings.TrimSpace(run.UserID) == "" ||
		strings.TrimSpace(run.SessionID) == "" ||
		strings.TrimSpace(run.ClientRequestID) == "" ||
		run.Revision <= expectedRevision ||
		run.JournalSequence <= 0 {
		return runDocument{}, nil, runruntime.ErrInvalidRun
	}
	document := runDocument{
		ID:              runID,
		UserID:          run.UserID,
		SessionID:       run.SessionID,
		ClientRequestID: run.ClientRequestID,
		Revision:        run.Revision,
		State:           run.State.WireName(),
		Snapshot:        run,
		CreatedAt:       run.CreatedAt.UTC(),
		UpdatedAt:       run.UpdatedAt.UTC(),
	}
	normalized := make([]journalDocument, 0, len(events))
	var previousSequence int64
	for _, event := range events {
		if strings.TrimSpace(event.EventID) == "" ||
			strings.TrimSpace(event.RunID) != runID ||
			event.Sequence <= previousSequence ||
			event.Revision <= expectedRevision ||
			event.Revision > run.Revision ||
			strings.TrimSpace(event.Kind) == "" ||
			event.CreatedAt.IsZero() {
			return runDocument{}, nil, runruntime.ErrInvalidRun
		}
		expiresAt := event.ExpiresAt.UTC()
		if event.ExpiresAt.IsZero() {
			expiresAt = event.CreatedAt.UTC().Add(runJournalRetention)
		}
		normalized = append(normalized, journalDocument{
			ID:        event.EventID,
			RunID:     runID,
			Sequence:  event.Sequence,
			Revision:  event.Revision,
			Kind:      strings.TrimSpace(event.Kind),
			Payload:   clonePayload(event.Payload),
			CreatedAt: event.CreatedAt.UTC(),
			ExpiresAt: expiresAt,
		})
		previousSequence = event.Sequence
	}
	if len(normalized) == 0 ||
		normalized[len(normalized)-1].Sequence != run.JournalSequence ||
		normalized[0].Sequence != run.JournalSequence-int64(len(normalized))+1 {
		return runDocument{}, nil, runruntime.ErrJournalCorrupt
	}
	return document, normalized, nil
}

func normalizeCommandReceipt(
	run runruntime.Run,
	receipt *runruntime.CommandReceipt,
) (*commandReceiptDocument, error) {
	if receipt == nil {
		return nil, nil
	}
	runID := strings.TrimSpace(receipt.RunID)
	commandID := strings.TrimSpace(receipt.CommandID)
	commandKind := strings.TrimSpace(receipt.CommandKind)
	payloadDigest := strings.TrimSpace(receipt.PayloadDigest)
	if runID != strings.TrimSpace(run.RunID) ||
		commandID == "" ||
		commandKind == "" ||
		payloadDigest == "" ||
		receipt.Revision != run.Revision ||
		receipt.CreatedAt.IsZero() {
		return nil, runruntime.ErrInvalidRun
	}
	return &commandReceiptDocument{
		ID:            runID + ":" + commandID,
		RunID:         runID,
		CommandID:     commandID,
		CommandKind:   commandKind,
		PayloadDigest: payloadDigest,
		Revision:      receipt.Revision,
		CreatedAt:     receipt.CreatedAt.UTC(),
	}, nil
}

func (r *MongoRunRepository) EventsAfter(
	ctx context.Context,
	runID string,
	afterSequence int64,
	limit int,
) ([]runruntime.JournalEvent, error) {
	if strings.TrimSpace(runID) == "" || afterSequence < 0 {
		return nil, runruntime.ErrInvalidRun
	}
	if limit <= 0 || limit > 1000 {
		limit = 256
	}
	cursor, err := r.events.Find(
		ctx,
		bson.M{"runId": strings.TrimSpace(runID), "seq": bson.M{"$gt": afterSequence}},
		options.Find().SetSort(bson.D{{Key: "seq", Value: 1}}).SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, fmt.Errorf("read assistant run journal: %w", err)
	}
	defer cursor.Close(ctx)
	result := make([]runruntime.JournalEvent, 0)
	for cursor.Next(ctx) {
		var document journalDocument
		if err := cursor.Decode(&document); err != nil {
			return nil, fmt.Errorf("decode assistant run journal: %w", err)
		}
		result = append(result, runruntime.JournalEvent{
			EventID:   document.ID,
			RunID:     document.RunID,
			Sequence:  document.Sequence,
			Revision:  document.Revision,
			Kind:      document.Kind,
			Payload:   clonePayload(document.Payload),
			CreatedAt: document.CreatedAt,
			ExpiresAt: document.ExpiresAt,
		})
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate assistant run journal: %w", err)
	}
	run, err := r.Load(ctx, runID)
	if err != nil {
		return nil, err
	}
	if run.JournalSequence > afterSequence {
		if len(result) == 0 || result[0].Sequence != afterSequence+1 {
			return nil, runruntime.ErrJournalGap
		}
	}
	for index := 1; index < len(result); index++ {
		if result[index].Sequence != result[index-1].Sequence+1 {
			return nil, runruntime.ErrJournalCorrupt
		}
	}
	return result, nil
}

func (r *MongoRunRepository) LatestSequence(
	ctx context.Context,
	runID string,
) (int64, error) {
	run, err := r.Load(ctx, runID)
	if err != nil {
		return 0, err
	}
	return run.JournalSequence, nil
}

func (r *MongoRunRepository) ClaimNext(
	ctx context.Context,
	workerID string,
	ttl time.Duration,
) (runruntime.WorkClaim, error) {
	workerID = strings.TrimSpace(workerID)
	if workerID == "" || ttl <= 0 {
		return runruntime.WorkClaim{}, runruntime.ErrInvalidRun
	}
	now := time.Now().UTC()
	var document workDocument
	err := r.work.FindOneAndUpdate(
		ctx,
		bson.M{"$or": []bson.M{
			{
				"status":      "ready",
				"availableAt": bson.M{"$lte": now},
			},
			{
				"status":    "claimed",
				"expiresAt": bson.M{"$lte": now},
			},
		}},
		bson.M{
			"$set": bson.M{
				"status":    "claimed",
				"workerId":  workerID,
				"claimedAt": now,
				"expiresAt": now.Add(ttl),
				"updatedAt": now,
			},
			"$inc": bson.M{"fencingToken": 1},
		},
		options.FindOneAndUpdate().
			SetSort(bson.D{{Key: "availableAt", Value: 1}, {Key: "_id", Value: 1}}).
			SetReturnDocument(options.After),
	).Decode(&document)
	if err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return runruntime.WorkClaim{}, runruntime.ErrNoWork
		}
		return runruntime.WorkClaim{}, fmt.Errorf("claim assistant run work: %w", err)
	}
	return projectWorkClaim(document), nil
}

func (r *MongoRunRepository) HeartbeatClaim(
	ctx context.Context,
	claim runruntime.WorkClaim,
	ttl time.Duration,
) (runruntime.WorkClaim, error) {
	if ttl <= 0 {
		return runruntime.WorkClaim{}, runruntime.ErrInvalidRun
	}
	now := time.Now().UTC()
	var document workDocument
	err := r.work.FindOneAndUpdate(
		ctx,
		workClaimFilter(claim, now),
		bson.M{"$set": bson.M{
			"expiresAt": now.Add(ttl),
			"updatedAt": now,
		}},
		options.FindOneAndUpdate().SetReturnDocument(options.After),
	).Decode(&document)
	if err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return runruntime.WorkClaim{}, runruntime.ErrLeaseConflict
		}
		return runruntime.WorkClaim{}, fmt.Errorf("heartbeat assistant run work: %w", err)
	}
	return projectWorkClaim(document), nil
}

func (r *MongoRunRepository) CompleteClaim(
	ctx context.Context,
	claim runruntime.WorkClaim,
	reschedule bool,
	availableAt time.Time,
) error {
	now := time.Now().UTC()
	filter := workClaimFilter(claim, now)
	if !reschedule {
		result, err := r.work.DeleteOne(ctx, filter)
		if err != nil {
			return fmt.Errorf("complete assistant run work: %w", err)
		}
		if result.DeletedCount != 1 {
			return runruntime.ErrLeaseConflict
		}
		return nil
	}
	if availableAt.IsZero() || availableAt.Before(now) {
		availableAt = now
	}
	result, err := r.work.UpdateOne(
		ctx,
		filter,
		bson.M{
			"$set": bson.M{
				"status":      "ready",
				"availableAt": availableAt.UTC(),
				"updatedAt":   now,
			},
			"$unset": bson.M{
				"workerId":  "",
				"claimedAt": "",
				"expiresAt": "",
			},
		},
	)
	if err != nil {
		return fmt.Errorf("reschedule assistant run work: %w", err)
	}
	if result.MatchedCount != 1 {
		return runruntime.ErrLeaseConflict
	}
	return nil
}

func workClaimFilter(claim runruntime.WorkClaim, now time.Time) bson.M {
	return bson.M{
		"_id":          strings.TrimSpace(claim.RunID),
		"status":       "claimed",
		"workerId":     strings.TrimSpace(claim.WorkerID),
		"fencingToken": claim.FencingToken,
		"expiresAt":    bson.M{"$gt": now},
	}
}

func projectWorkClaim(document workDocument) runruntime.WorkClaim {
	return runruntime.WorkClaim{
		RunID:        document.ID,
		WorkerID:     document.WorkerID,
		FencingToken: document.FencingToken,
		ClaimedAt:    document.ClaimedAt,
		ExpiresAt:    document.ExpiresAt,
	}
}

func queueRunnable(state string) bool {
	switch strings.TrimSpace(state) {
	case "completed", "failed", "cancelled", "paused",
		"waiting_user", "waiting_approval", "waiting_external":
		return false
	default:
		return true
	}
}

func (r *MongoRunRepository) Acquire(
	ctx context.Context,
	runID string,
	workerID string,
	ttl time.Duration,
) (runruntime.WorkerLease, error) {
	runID = strings.TrimSpace(runID)
	workerID = strings.TrimSpace(workerID)
	if runID == "" || workerID == "" || ttl <= 0 {
		return runruntime.WorkerLease{}, runruntime.ErrInvalidRun
	}
	now := time.Now().UTC()
	leaseID, err := randomLeaseID()
	if err != nil {
		return runruntime.WorkerLease{}, err
	}
	var document leaseDocument
	err = r.leases.FindOneAndUpdate(
		ctx,
		bson.M{
			"_id": runID,
			"$or": []bson.M{
				{"expiresAt": bson.M{"$lte": now}},
				{"workerId": workerID},
			},
		},
		bson.M{
			"$set": bson.M{
				"leaseId":     leaseID,
				"workerId":    workerID,
				"acquiredAt":  now,
				"heartbeatAt": now,
				"expiresAt":   now.Add(ttl),
			},
			"$inc": bson.M{"fencingToken": 1},
		},
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&document)
	if err != nil {
		if mongo.IsDuplicateKeyError(err) || errors.Is(err, mongo.ErrNoDocuments) {
			return runruntime.WorkerLease{}, runruntime.ErrLeaseConflict
		}
		return runruntime.WorkerLease{}, fmt.Errorf("acquire assistant run lease: %w", err)
	}
	return projectLease(document), nil
}

func (r *MongoRunRepository) Heartbeat(
	ctx context.Context,
	lease runruntime.WorkerLease,
	ttl time.Duration,
) (runruntime.WorkerLease, error) {
	if ttl <= 0 {
		return runruntime.WorkerLease{}, runruntime.ErrInvalidRun
	}
	now := time.Now().UTC()
	var document leaseDocument
	err := r.leases.FindOneAndUpdate(
		ctx,
		bson.M{
			"_id":          strings.TrimSpace(lease.RunID),
			"leaseId":      strings.TrimSpace(lease.LeaseID),
			"workerId":     strings.TrimSpace(lease.WorkerID),
			"fencingToken": lease.FencingToken,
			"expiresAt":    bson.M{"$gt": now},
		},
		bson.M{"$set": bson.M{"heartbeatAt": now, "expiresAt": now.Add(ttl)}},
		options.FindOneAndUpdate().SetReturnDocument(options.After),
	).Decode(&document)
	if err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return runruntime.WorkerLease{}, runruntime.ErrLeaseConflict
		}
		return runruntime.WorkerLease{}, fmt.Errorf("heartbeat assistant run lease: %w", err)
	}
	return projectLease(document), nil
}

func (r *MongoRunRepository) Release(
	ctx context.Context,
	lease runruntime.WorkerLease,
) error {
	result, err := r.leases.DeleteOne(ctx, bson.M{
		"_id":          strings.TrimSpace(lease.RunID),
		"leaseId":      strings.TrimSpace(lease.LeaseID),
		"workerId":     strings.TrimSpace(lease.WorkerID),
		"fencingToken": lease.FencingToken,
	})
	if err != nil {
		return fmt.Errorf("release assistant run lease: %w", err)
	}
	if result.DeletedCount != 1 {
		return runruntime.ErrLeaseConflict
	}
	return nil
}

func projectLease(document leaseDocument) runruntime.WorkerLease {
	return runruntime.WorkerLease{
		LeaseID:      document.LeaseID,
		RunID:        document.ID,
		WorkerID:     document.WorkerID,
		FencingToken: document.FencingToken,
		AcquiredAt:   document.AcquiredAt,
		HeartbeatAt:  document.HeartbeatAt,
		ExpiresAt:    document.ExpiresAt,
	}
}

func randomLeaseID() (string, error) {
	buffer := make([]byte, 16)
	if _, err := rand.Read(buffer); err != nil {
		return "", fmt.Errorf("create assistant run lease id: %w", err)
	}
	return "arl_" + hex.EncodeToString(buffer), nil
}

func clonePayload(value map[string]any) map[string]any {
	if value == nil {
		return nil
	}
	result := make(map[string]any, len(value))
	for key, item := range value {
		result[key] = item
	}
	return result
}
