package infrastructure

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

type hookOutboxDocument struct {
	ID                   string         `bson:"_id"`
	RunID                string         `bson:"runId"`
	Phase                string         `bson:"phase"`
	Outcome              string         `bson:"outcome"`
	RunRevision          int64          `bson:"runRevision"`
	ProtectedFactsDigest string         `bson:"protectedFactsDigest"`
	Data                 map[string]any `bson:"data"`
	CreatedAt            time.Time      `bson:"createdAt"`
	ClaimOwner           string         `bson:"claimOwner,omitempty"`
	ClaimUntil           *time.Time     `bson:"claimUntil,omitempty"`
	NextAttemptAt        *time.Time     `bson:"nextAttemptAt,omitempty"`
	AttemptCount         int            `bson:"attemptCount,omitempty"`
	LastError            string         `bson:"lastError,omitempty"`
	ProcessedAt          *time.Time     `bson:"processedAt,omitempty"`
	ReceiptDigest        string         `bson:"receiptDigest,omitempty"`
}

func (r *MongoRunRepository) ensureHookOutboxIndexes(ctx context.Context) error {
	_, err := r.hookOutbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "runId", Value: 1},
				{Key: "phase", Value: 1},
				{Key: "runRevision", Value: 1},
			},
			Options: options.Index().SetName("uq_run_hook_outbox_invocation").
				SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "processedAt", Value: 1},
				{Key: "nextAttemptAt", Value: 1},
				{Key: "claimUntil", Value: 1},
				{Key: "createdAt", Value: 1},
			},
			Options: options.Index().SetName("idx_run_hook_outbox_claimable"),
		},
	})
	if err != nil {
		return fmt.Errorf("create assistant run hook outbox indexes: %w", err)
	}
	return nil
}

func hookOutboxFromTransition(
	previousState string,
	run runruntime.Run,
) (*hookOutboxDocument, error) {
	previousState = strings.TrimSpace(previousState)
	outcome := strings.TrimSpace(run.State.WireName())
	if previousState == "" || !queueRunnable(previousState) || !hookStopOutcome(outcome) {
		return nil, nil
	}
	invocationID := runruntime.StableHookInvocationID(
		run.RunID,
		runruntime.HookOnStop,
		run.Revision,
	)
	protectedFactsDigest := runruntime.ProtectedRunFactsDigest(run)
	if invocationID == "" || protectedFactsDigest == "" || run.UpdatedAt.IsZero() {
		return nil, runruntime.ErrInvalidRun
	}
	return &hookOutboxDocument{
		ID:                   invocationID,
		RunID:                strings.TrimSpace(run.RunID),
		Phase:                string(runruntime.HookOnStop),
		Outcome:              outcome,
		RunRevision:          run.Revision,
		ProtectedFactsDigest: protectedFactsDigest,
		Data:                 map[string]any{"outcome": outcome},
		CreatedAt:            run.UpdatedAt.UTC(),
	}, nil
}

func hookStopOutcome(value string) bool {
	switch strings.TrimSpace(value) {
	case "completed", "failed", "cancelled", "paused",
		"waiting_user", "waiting_approval", "waiting_external":
		return true
	default:
		return false
	}
}

func (r *MongoRunRepository) ClaimPendingStopHooks(
	ctx context.Context,
	ownerID string,
	now time.Time,
	lease time.Duration,
	limit int,
) ([]runruntime.StopHookInvocation, error) {
	ownerID = strings.TrimSpace(ownerID)
	now = now.UTC()
	if ownerID == "" || now.IsZero() || lease <= 0 {
		return nil, runruntime.ErrInvalidRun
	}
	if limit <= 0 || limit > 1000 {
		limit = 128
	}
	invocations := make([]runruntime.StopHookInvocation, 0, limit)
	for len(invocations) < limit {
		claimUntil := now.Add(lease)
		var document hookOutboxDocument
		err := r.hookOutbox.FindOneAndUpdate(
			ctx,
			bson.M{
				"processedAt": bson.M{"$exists": false},
				"$and": bson.A{
					bson.M{"$or": bson.A{
						bson.M{"nextAttemptAt": bson.M{"$exists": false}},
						bson.M{"nextAttemptAt": bson.M{"$lte": now}},
					}},
					bson.M{"$or": bson.A{
						bson.M{"claimUntil": bson.M{"$exists": false}},
						bson.M{"claimUntil": bson.M{"$lte": now}},
					}},
				},
			},
			bson.M{
				"$set": bson.M{
					"claimOwner": ownerID,
					"claimUntil": claimUntil,
				},
				"$inc": bson.M{"attemptCount": 1},
			},
			options.FindOneAndUpdate().
				SetSort(bson.D{{Key: "createdAt", Value: 1}, {Key: "_id", Value: 1}}).
				SetReturnDocument(options.After),
		).Decode(&document)
		if errors.Is(err, mongo.ErrNoDocuments) {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("claim assistant run hook outbox: %w", err)
		}
		invocations = append(invocations, runruntime.StopHookInvocation{
			InvocationID:         document.ID,
			RunID:                document.RunID,
			Phase:                runruntime.HookPhase(document.Phase),
			Outcome:              document.Outcome,
			RunRevision:          document.RunRevision,
			ProtectedFactsDigest: document.ProtectedFactsDigest,
			Data:                 clonePayload(document.Data),
			CreatedAt:            document.CreatedAt,
			AttemptCount:         document.AttemptCount,
		})
	}
	return invocations, nil
}

func (r *MongoRunRepository) AcknowledgeStopHook(
	ctx context.Context,
	invocationID string,
	ownerID string,
	processedAt time.Time,
	receiptDigest string,
) error {
	invocationID = strings.TrimSpace(invocationID)
	ownerID = strings.TrimSpace(ownerID)
	receiptDigest = strings.TrimSpace(receiptDigest)
	if invocationID == "" || ownerID == "" || processedAt.IsZero() ||
		!validHookOutboxDigest(receiptDigest) {
		return runruntime.ErrInvalidRun
	}
	processedAt = processedAt.UTC()
	result, err := r.hookOutbox.UpdateOne(
		ctx,
		bson.M{
			"_id":         invocationID,
			"claimOwner":  ownerID,
			"claimUntil":  bson.M{"$gt": processedAt},
			"processedAt": bson.M{"$exists": false},
		},
		bson.M{
			"$set": bson.M{
				"processedAt":   processedAt,
				"receiptDigest": receiptDigest,
			},
			"$unset": bson.M{
				"claimOwner": "", "claimUntil": "", "nextAttemptAt": "",
				"lastError": "",
			},
		},
	)
	if err != nil {
		return fmt.Errorf("mark assistant run hook outbox processed: %w", err)
	}
	if result.MatchedCount == 1 {
		return nil
	}
	// If the server committed the acknowledgement but the caller lost its
	// response, the exact receipt replay is success. A different digest remains
	// fenced instead of hiding double execution.
	var existing struct {
		ProcessedAt   *time.Time `bson:"processedAt"`
		ReceiptDigest string     `bson:"receiptDigest"`
	}
	err = r.hookOutbox.FindOne(
		ctx,
		bson.M{"_id": invocationID},
		options.FindOne().SetProjection(bson.M{"processedAt": 1, "receiptDigest": 1}),
	).Decode(&existing)
	if err == nil && existing.ProcessedAt != nil &&
		strings.TrimSpace(existing.ReceiptDigest) == receiptDigest {
		return nil
	}
	if err != nil && !errors.Is(err, mongo.ErrNoDocuments) {
		return fmt.Errorf("verify assistant run hook receipt: %w", err)
	}
	return runruntime.ErrStopHookClaimLost
}

func (r *MongoRunRepository) ScheduleStopHookRetry(
	ctx context.Context,
	invocationID string,
	ownerID string,
	failedAt time.Time,
	nextAttemptAt time.Time,
	failureCode string,
) error {
	invocationID = strings.TrimSpace(invocationID)
	ownerID = strings.TrimSpace(ownerID)
	if invocationID == "" || ownerID == "" || failedAt.IsZero() ||
		nextAttemptAt.IsZero() || nextAttemptAt.Before(failedAt) {
		return runruntime.ErrInvalidRun
	}
	result, err := r.hookOutbox.UpdateOne(
		ctx,
		bson.M{
			"_id":         invocationID,
			"claimOwner":  ownerID,
			"claimUntil":  bson.M{"$gt": failedAt.UTC()},
			"processedAt": bson.M{"$exists": false},
		},
		bson.M{
			"$set": bson.M{
				"nextAttemptAt": nextAttemptAt.UTC(),
				"lastError":     boundedHookFailure(failureCode),
			},
			"$unset": bson.M{"claimOwner": "", "claimUntil": ""},
		},
	)
	if err != nil {
		return fmt.Errorf("schedule assistant run hook retry: %w", err)
	}
	if result.MatchedCount != 1 {
		return runruntime.ErrStopHookClaimLost
	}
	return nil
}

func (r *MongoRunRepository) ReleaseStopHookClaim(
	ctx context.Context,
	invocationID string,
	ownerID string,
) error {
	invocationID = strings.TrimSpace(invocationID)
	ownerID = strings.TrimSpace(ownerID)
	if invocationID == "" || ownerID == "" {
		return runruntime.ErrInvalidRun
	}
	result, err := r.hookOutbox.UpdateOne(
		ctx,
		bson.M{
			"_id":         invocationID,
			"claimOwner":  ownerID,
			"processedAt": bson.M{"$exists": false},
		},
		bson.M{"$unset": bson.M{"claimOwner": "", "claimUntil": ""}},
	)
	if err != nil {
		return fmt.Errorf("release assistant run hook claim: %w", err)
	}
	if result.MatchedCount != 1 {
		return runruntime.ErrStopHookClaimLost
	}
	return nil
}

func boundedHookFailure(value string) string {
	value = strings.TrimSpace(value)
	if value == "" || len(value) > 64 {
		return "delivery_failed"
	}
	return value
}

func validHookOutboxDigest(value string) bool {
	value = strings.TrimSpace(value)
	if len(value) != 71 || !strings.HasPrefix(value, "sha256:") {
		return false
	}
	for _, char := range strings.TrimPrefix(value, "sha256:") {
		if (char < '0' || char > '9') && (char < 'a' || char > 'f') {
			return false
		}
	}
	return true
}

var _ runruntime.StopHookStore = (*MongoRunRepository)(nil)
