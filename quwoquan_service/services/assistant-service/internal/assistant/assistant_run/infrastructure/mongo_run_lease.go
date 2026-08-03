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

// Acquire creates a fenced lease for one durable Run. An expired lease can be
// taken over, while every successful acquisition advances the fencing token.
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
