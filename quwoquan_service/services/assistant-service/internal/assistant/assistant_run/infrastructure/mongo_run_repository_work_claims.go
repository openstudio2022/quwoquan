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
