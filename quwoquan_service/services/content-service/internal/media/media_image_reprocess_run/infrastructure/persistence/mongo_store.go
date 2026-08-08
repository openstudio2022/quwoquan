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

	reprocessmodel "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/domain/model"
	reprocessports "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/domain/ports"
)

// MongoStore exclusively owns MediaImageReprocessRun state, idempotency
// receipts and worker leases.
type MongoStore struct {
	runs     *mongo.Collection
	receipts *mongo.Collection
	leases   *mongo.Collection
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		panic("MediaImageReprocessRun MongoStore requires database")
	}
	return &MongoStore{
		runs:     database.Collection("media_image_reprocess_runs"),
		receipts: database.Collection("media_image_reprocess_run_receipts"),
		leases:   database.Collection("media_image_reprocess_run_leases"),
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.runs.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "status", Value: 1}, {Key: "updatedAt", Value: 1}}, Options: options.Index().SetName("idx_media_image_reprocess_run_status_updated")},
		{Keys: bson.D{{Key: "_id", Value: 1}, {Key: "version", Value: 1}}, Options: options.Index().SetName("idx_media_image_reprocess_run_version").SetUnique(true)},
	}); err != nil {
		return fmt.Errorf("create media image reprocess run indexes: %w", err)
	}
	if _, err := store.receipts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: -1}}, Options: options.Index().SetName("idx_media_image_reprocess_run_receipts_aggregate")},
		{Keys: bson.D{{Key: "expiresAt", Value: 1}}, Options: options.Index().SetName("idx_media_image_reprocess_run_receipts_expire").SetExpireAfterSeconds(0)},
	}); err != nil {
		return fmt.Errorf("create media image reprocess receipt indexes: %w", err)
	}
	if _, err := store.leases.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "leaseUntil", Value: 1}},
		Options: options.Index().SetName("idx_media_image_reprocess_run_lease_until"),
	}); err != nil {
		return fmt.Errorf("create media image reprocess lease indexes: %w", err)
	}
	return nil
}

type mediaImageReprocessRunDocument struct {
	ID                            string                      `bson:"_id"`
	Version                       int64                       `bson:"version"`
	TargetDerivativePolicyVersion int                         `bson:"targetDerivativePolicyVersion"`
	Status                        reprocessmodel.Status       `bson:"status"`
	AssetIDs                      []string                    `bson:"assetIds"`
	NextAssetIndex                int                         `bson:"nextAssetIndex"`
	ProcessedCount                int                         `bson:"processedCount"`
	FailedCount                   int                         `bson:"failedCount"`
	RollbackIndex                 int                         `bson:"rollbackIndex"`
	Activations                   []reprocessmodel.Activation `bson:"activations"`
	FailureReason                 string                      `bson:"failureReason,omitempty"`
	StartedAt                     time.Time                   `bson:"startedAt"`
	PausedAt                      *time.Time                  `bson:"pausedAt,omitempty"`
	CompletedAt                   *time.Time                  `bson:"completedAt,omitempty"`
	RolledBackAt                  *time.Time                  `bson:"rolledBackAt,omitempty"`
	UpdatedAt                     time.Time                   `bson:"updatedAt"`
}

type mediaImageReprocessRunReceiptDocument struct {
	ID               string                         `bson:"_id"`
	AggregateID      string                         `bson:"aggregateId"`
	AggregateVersion int64                          `bson:"aggregateVersion"`
	CommandName      string                         `bson:"commandName"`
	CommandDigest    string                         `bson:"commandDigest"`
	Result           mediaImageReprocessRunDocument `bson:"result"`
	CreatedAt        time.Time                      `bson:"createdAt"`
	ExpiresAt        time.Time                      `bson:"expiresAt"`
}

func (s *MongoStore) LoadMediaImageReprocessRun(
	ctx context.Context,
	runID string,
) (*reprocessmodel.Run, bool, error) {
	var document mediaImageReprocessRunDocument
	err := s.runs.FindOne(
		ctx,
		bson.D{{Key: "_id", Value: strings.TrimSpace(runID)}},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, fmt.Errorf("load media image reprocess run: %w", err)
	}
	run, err := mediaImageReprocessRunFromDocument(document)
	if err != nil {
		return nil, false, err
	}
	return run, true, nil
}

func (s *MongoStore) FindMediaImageReprocessRunReceipt(
	ctx context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (reprocessports.CommitResult, bool, error) {
	var receipt mediaImageReprocessRunReceiptDocument
	err := s.receipts.FindOne(
		ctx,
		bson.D{{Key: "_id", Value: strings.TrimSpace(idempotencyKey)}},
	).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return reprocessports.CommitResult{}, false, nil
	}
	if err != nil {
		return reprocessports.CommitResult{}, false, fmt.Errorf("find media image reprocess run receipt: %w", err)
	}
	if !receipt.ExpiresAt.After(time.Now().UTC()) {
		return reprocessports.CommitResult{}, false, nil
	}
	if receipt.CommandName != strings.TrimSpace(commandName) ||
		receipt.CommandDigest != strings.TrimSpace(commandDigest) {
		return reprocessports.CommitResult{}, false, fmt.Errorf(
			"%w: idempotency key conflicts with prior command",
			reprocessmodel.ErrRunVersionConflict,
		)
	}
	run, err := mediaImageReprocessRunFromDocument(receipt.Result)
	if err != nil {
		return reprocessports.CommitResult{}, false, err
	}
	return reprocessports.CommitResult{Aggregate: run, Replayed: true}, true, nil
}

func (s *MongoStore) CommitMediaImageReprocessRun(
	ctx context.Context,
	commit reprocessports.Commit,
) (reprocessports.CommitResult, error) {
	if err := validateMediaImageReprocessRunCommit(commit); err != nil {
		return reprocessports.CommitResult{}, err
	}
	session, err := s.runs.Database().Client().StartSession()
	if err != nil {
		return reprocessports.CommitResult{}, fmt.Errorf("start media image reprocess run transaction: %w", err)
	}
	defer session.EndSession(ctx)

	var result reprocessports.CommitResult
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		replayed, found, err := s.findMediaImageReprocessRunReceiptTx(
			txCtx,
			commit.IdempotencyKey,
			commit.CommandName,
			commit.CommandDigest,
		)
		if err != nil {
			return nil, err
		}
		if found {
			result = replayed
			return nil, nil
		}
		next := mediaImageReprocessRunDocumentFromModel(commit.Aggregate)
		if commit.ExpectedVersion == 0 {
			if _, err := s.runs.InsertOne(txCtx, next); err != nil {
				return nil, err
			}
		} else {
			replaceResult, err := s.runs.ReplaceOne(
				txCtx,
				bson.D{{Key: "_id", Value: next.ID}, {Key: "version", Value: commit.ExpectedVersion}},
				next,
			)
			if err != nil {
				return nil, err
			}
			if replaceResult.MatchedCount != 1 {
				return nil, fmt.Errorf(
					"%w: version changed before commit",
					reprocessmodel.ErrRunVersionConflict,
				)
			}
		}
		receiptExpiry := commit.ReceiptExpiresAt.UTC()
		if receiptExpiry.IsZero() {
			receiptExpiry = time.Now().UTC().Add(24 * time.Hour)
		}
		if _, err := s.receipts.InsertOne(txCtx, mediaImageReprocessRunReceiptDocument{
			ID:               strings.TrimSpace(commit.IdempotencyKey),
			AggregateID:      next.ID,
			AggregateVersion: next.Version,
			CommandName:      strings.TrimSpace(commit.CommandName),
			CommandDigest:    strings.TrimSpace(commit.CommandDigest),
			Result:           next,
			CreatedAt:        time.Now().UTC(),
			ExpiresAt:        receiptExpiry,
		}); err != nil {
			return nil, err
		}
		persisted, err := mediaImageReprocessRunFromDocument(next)
		if err != nil {
			return nil, err
		}
		result = reprocessports.CommitResult{Aggregate: persisted}
		return nil, nil
	})
	if err != nil {
		return reprocessports.CommitResult{}, fmt.Errorf("commit media image reprocess run: %w", err)
	}
	return result, nil
}

func (s *MongoStore) ListRunnableMediaImageReprocessRuns(
	ctx context.Context,
	limit int,
) ([]*reprocessmodel.Run, error) {
	if limit <= 0 || limit > reprocessmodel.MaxRunAssets {
		limit = reprocessmodel.MaxRunAssets
	}
	cursor, err := s.runs.Find(
		ctx,
		bson.D{{Key: "status", Value: bson.D{{Key: "$in", Value: bson.A{
			reprocessmodel.StatusRunning,
			reprocessmodel.StatusRollingBack,
		}}}}},
		options.Find().SetSort(bson.D{{Key: "updatedAt", Value: 1}, {Key: "_id", Value: 1}}).SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, fmt.Errorf("list runnable media image reprocess runs: %w", err)
	}
	defer cursor.Close(ctx)
	runs := make([]*reprocessmodel.Run, 0)
	for cursor.Next(ctx) {
		var document mediaImageReprocessRunDocument
		if err := cursor.Decode(&document); err != nil {
			return nil, fmt.Errorf("decode media image reprocess run: %w", err)
		}
		run, err := mediaImageReprocessRunFromDocument(document)
		if err != nil {
			return nil, err
		}
		runs = append(runs, run)
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate runnable media image reprocess runs: %w", err)
	}
	return runs, nil
}

func (s *MongoStore) TryAcquireMediaImageReprocessRunLease(
	ctx context.Context,
	runID string,
	owner string,
	now time.Time,
	ttl time.Duration,
) (bool, error) {
	return s.updateMediaImageReprocessRunLease(ctx, runID, owner, now, ttl, false)
}

func (s *MongoStore) RenewMediaImageReprocessRunLease(
	ctx context.Context,
	runID string,
	owner string,
	now time.Time,
	ttl time.Duration,
) (bool, error) {
	return s.updateMediaImageReprocessRunLease(ctx, runID, owner, now, ttl, true)
}

func (s *MongoStore) updateMediaImageReprocessRunLease(
	ctx context.Context,
	runID string,
	owner string,
	now time.Time,
	ttl time.Duration,
	renewOnly bool,
) (bool, error) {
	runID = strings.TrimSpace(runID)
	owner = strings.TrimSpace(owner)
	now = now.UTC()
	if runID == "" || owner == "" || now.IsZero() || ttl <= 0 {
		return false, fmt.Errorf("media image reprocess run lease is invalid")
	}
	filter := bson.D{{Key: "_id", Value: runID}}
	if renewOnly {
		filter = append(filter,
			bson.E{Key: "leaseOwner", Value: owner},
			bson.E{Key: "leaseUntil", Value: bson.D{{Key: "$gt", Value: now}}},
		)
	} else {
		filter = append(filter, bson.E{Key: "$or", Value: bson.A{
			bson.D{{Key: "leaseOwner", Value: owner}},
			bson.D{{Key: "leaseUntil", Value: bson.D{{Key: "$exists", Value: false}}}},
			bson.D{{Key: "leaseUntil", Value: bson.D{{Key: "$lte", Value: now}}}}}})
	}
	result, err := s.leases.UpdateOne(
		ctx,
		filter,
		bson.D{{Key: "$set", Value: bson.D{
			{Key: "leaseOwner", Value: owner},
			{Key: "leaseUntil", Value: now.Add(ttl)},
			{Key: "updatedAt", Value: now},
		}}},
		options.UpdateOne().SetUpsert(!renewOnly),
	)
	if err != nil {
		if mongo.IsDuplicateKeyError(err) {
			return false, nil
		}
		return false, fmt.Errorf("update media image reprocess run lease: %w", err)
	}
	return result.MatchedCount == 1 || result.UpsertedCount == 1, nil
}

func (s *MongoStore) findMediaImageReprocessRunReceiptTx(
	ctx context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (reprocessports.CommitResult, bool, error) {
	return s.FindMediaImageReprocessRunReceipt(ctx, idempotencyKey, commandName, commandDigest)
}

func mediaImageReprocessRunDocumentFromModel(
	run *reprocessmodel.Run,
) mediaImageReprocessRunDocument {
	snapshot := run.Snapshot()
	return mediaImageReprocessRunDocument{
		ID:                            snapshot.RunID,
		Version:                       snapshot.Version,
		TargetDerivativePolicyVersion: snapshot.TargetDerivativePolicyVersion,
		Status:                        snapshot.Status,
		AssetIDs:                      snapshot.AssetIDs,
		NextAssetIndex:                snapshot.NextAssetIndex,
		ProcessedCount:                snapshot.ProcessedCount,
		FailedCount:                   snapshot.FailedCount,
		RollbackIndex:                 snapshot.RollbackIndex,
		Activations:                   snapshot.Activations,
		FailureReason:                 snapshot.FailureReason,
		StartedAt:                     snapshot.StartedAt,
		PausedAt:                      snapshot.PausedAt,
		CompletedAt:                   snapshot.CompletedAt,
		RolledBackAt:                  snapshot.RolledBackAt,
		UpdatedAt:                     snapshot.UpdatedAt,
	}
}

func mediaImageReprocessRunFromDocument(
	document mediaImageReprocessRunDocument,
) (*reprocessmodel.Run, error) {
	run, err := reprocessmodel.Restore(reprocessmodel.Snapshot{
		RunID:                         document.ID,
		Version:                       document.Version,
		TargetDerivativePolicyVersion: document.TargetDerivativePolicyVersion,
		Status:                        document.Status,
		AssetIDs:                      document.AssetIDs,
		NextAssetIndex:                document.NextAssetIndex,
		ProcessedCount:                document.ProcessedCount,
		FailedCount:                   document.FailedCount,
		RollbackIndex:                 document.RollbackIndex,
		Activations:                   document.Activations,
		FailureReason:                 document.FailureReason,
		StartedAt:                     document.StartedAt,
		PausedAt:                      document.PausedAt,
		CompletedAt:                   document.CompletedAt,
		RolledBackAt:                  document.RolledBackAt,
		UpdatedAt:                     document.UpdatedAt,
	})
	if err != nil {
		return nil, fmt.Errorf("restore media image reprocess run: %w", err)
	}
	return run, nil
}

func validateMediaImageReprocessRunCommit(commit reprocessports.Commit) error {
	if commit.Aggregate == nil || commit.ExpectedVersion < 0 ||
		commit.Aggregate.Version() != commit.ExpectedVersion+1 ||
		strings.TrimSpace(commit.IdempotencyKey) == "" ||
		strings.TrimSpace(commit.CommandName) == "" ||
		strings.TrimSpace(commit.CommandDigest) == "" {
		return fmt.Errorf("media image reprocess run commit is incomplete")
	}
	return nil
}

var _ reprocessports.RunStore = (*MongoStore)(nil)
