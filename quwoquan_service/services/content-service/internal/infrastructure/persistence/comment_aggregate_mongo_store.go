package persistence

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	commentmodel "quwoquan_service/services/content-service/internal/domain/comment/model"
	commentports "quwoquan_service/services/content-service/internal/domain/comment/ports"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

const (
	commentAggregateCollection  = "comments"
	commentReceiptsCollection   = "comment_command_receipts"
	commentRateLocksCollection  = "comment_author_rate_limit_locks"
	commentOutboxCollection     = "comment_outbox"
	commentCheckpointCollection = "comment_projection_checkpoints"
	postsRelationCollection     = "posts"
)

// MongoCommentDataAdapter is the production Comment aggregate store and named
// reader adapter. It uses only BSON projections for read slices and relation
// checks; it never decodes or delegates to a Post aggregate/store.
type MongoCommentDataAdapter struct {
	comments    *mongo.Collection
	receipts    *mongo.Collection
	rateLocks   *mongo.Collection
	outbox      *mongo.Collection
	checkpoints *mongo.Collection
	posts       *mongo.Collection
}

func NewMongoCommentDataAdapter(db *mongo.Database) *MongoCommentDataAdapter {
	return &MongoCommentDataAdapter{
		comments:    db.Collection(commentAggregateCollection),
		receipts:    db.Collection(commentReceiptsCollection),
		rateLocks:   db.Collection(commentRateLocksCollection),
		outbox:      db.Collection(commentOutboxCollection),
		checkpoints: db.Collection(commentCheckpointCollection),
		posts:       db.Collection(postsRelationCollection),
	}
}

var (
	_ commentports.AggregateStore            = (*MongoCommentDataAdapter)(nil)
	_ commentports.OutboxReader              = (*MongoCommentDataAdapter)(nil)
	_ commentports.ProjectionCheckpointStore = (*MongoCommentDataAdapter)(nil)
	_ commentports.CommentPageReader         = (*MongoCommentDataAdapter)(nil)
	_ commentports.ReplyPageReader           = (*MongoCommentDataAdapter)(nil)
	_ commentports.ReplySummaryReader        = (*MongoCommentDataAdapter)(nil)
	_ commentports.AuthorCommentPageReader   = (*MongoCommentDataAdapter)(nil)
	_ commentports.ReceivedCommentPageReader = (*MongoCommentDataAdapter)(nil)
	_ commentports.CountReader               = (*MongoCommentDataAdapter)(nil)
	_ commentports.CommentRelationReader     = (*MongoCommentDataAdapter)(nil)
	_ commentports.PostOwnershipReader       = (*MongoCommentDataAdapter)(nil)
)

func (s *MongoCommentDataAdapter) Load(
	ctx context.Context,
	commentID string,
) (*commentmodel.Comment, bool, error) {
	var document commentAggregateDocument
	err := s.comments.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(commentID)},
	).Decode(&document)
	if err == mongo.ErrNoDocuments {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	aggregate, err := document.aggregate()
	if err != nil {
		return nil, false, err
	}
	return aggregate, true, nil
}

func (s *MongoCommentDataAdapter) FindReceipt(
	ctx context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (commentports.CommitResult, bool, error) {
	receipt, found, err := s.findReceipt(
		ctx,
		strings.TrimSpace(idempotencyKey),
	)
	if err != nil || !found {
		return commentports.CommitResult{}, found, err
	}
	if !receipt.ExpiresAt.After(time.Now().UTC()) {
		if _, err := s.receipts.DeleteOne(ctx, bson.M{"_id": receipt.ID}); err != nil {
			return commentports.CommitResult{}, false, err
		}
		return commentports.CommitResult{}, false, nil
	}
	if receipt.CommandName != commandName || receipt.CommandDigest != commandDigest {
		return commentports.CommitResult{}, false,
			contentgenerated.AppErrorFromIdempotencyConflict(
				"idempotency key was reused with a different comment command",
			)
	}
	aggregate, err := receipt.Result.aggregate()
	if err != nil {
		return commentports.CommitResult{}, false, err
	}
	return commentports.CommitResult{Aggregate: aggregate, Replayed: true}, true, nil
}

func (s *MongoCommentDataAdapter) RecordIdempotentReceipt(
	ctx context.Context,
	idempotent commentports.IdempotentReceipt,
) (commentports.CommitResult, error) {
	if idempotent.Aggregate == nil ||
		strings.TrimSpace(idempotent.IdempotencyKey) == "" ||
		strings.TrimSpace(idempotent.CommandName) == "" ||
		strings.TrimSpace(idempotent.CommandDigest) == "" {
		return commentports.CommitResult{},
			contentgenerated.AppErrorFromVersionConflict(
				"comment no-op receipt is incomplete",
			)
	}
	if replayed, found, err := s.FindReceipt(
		ctx,
		idempotent.IdempotencyKey,
		idempotent.CommandName,
		idempotent.CommandDigest,
	); err != nil || found {
		return replayed, err
	}
	record := commentAggregateDocumentFromSnapshot(idempotent.Aggregate.Snapshot())
	expiresAt := idempotent.ReceiptExpiresAt.UTC()
	if expiresAt.IsZero() {
		expiresAt = time.Now().UTC().Add(24 * time.Hour)
	}
	_, err := s.receipts.InsertOne(ctx, commentCommandReceiptDocument{
		ID:               strings.TrimSpace(idempotent.IdempotencyKey),
		AggregateID:      record.ID,
		AggregateVersion: record.Version,
		CommandName:      strings.TrimSpace(idempotent.CommandName),
		CommandDigest:    strings.TrimSpace(idempotent.CommandDigest),
		Result:           record,
		CreatedAt:        time.Now().UTC(),
		ExpiresAt:        expiresAt,
	})
	if err != nil {
		if mongo.IsDuplicateKeyError(err) {
			replayed, found, replayErr := s.FindReceipt(
				ctx,
				idempotent.IdempotencyKey,
				idempotent.CommandName,
				idempotent.CommandDigest,
			)
			if replayErr != nil {
				return commentports.CommitResult{}, replayErr
			}
			if found {
				return replayed, nil
			}
		}
		return commentports.CommitResult{}, err
	}
	aggregate, err := record.aggregate()
	if err != nil {
		return commentports.CommitResult{}, err
	}
	return commentports.CommitResult{Aggregate: aggregate}, nil
}

func (s *MongoCommentDataAdapter) Commit(
	ctx context.Context,
	commit commentports.Commit,
) (commentports.CommitResult, error) {
	if err := validateCommentCommit(commit); err != nil {
		return commentports.CommitResult{}, err
	}
	session, err := s.comments.Database().Client().StartSession()
	if err != nil {
		return commentports.CommitResult{}, err
	}
	defer session.EndSession(ctx)

	var result commentports.CommitResult
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		receipt, receiptFound, receiptErr := s.findReceipt(txCtx, commit.IdempotencyKey)
		if receiptErr != nil {
			return nil, receiptErr
		}
		if receiptFound {
			if !receipt.ExpiresAt.After(time.Now().UTC()) {
				if _, err := s.receipts.DeleteOne(txCtx, bson.M{"_id": receipt.ID}); err != nil {
					return nil, err
				}
			} else {
				if receipt.CommandName != commit.CommandName ||
					receipt.CommandDigest != commit.CommandDigest {
					return nil, contentgenerated.AppErrorFromIdempotencyConflict(
						"idempotency key was reused with a different comment command",
					)
				}
				replayed, err := receipt.Result.aggregate()
				if err != nil {
					return nil, err
				}
				result = commentports.CommitResult{Aggregate: replayed, Replayed: true}
				return nil, nil
			}
		}

		if err := s.enforceAuthorRateLimit(txCtx, commit.AuthorRateLimit); err != nil {
			return nil, err
		}

		record := commentAggregateDocumentFromSnapshot(commit.Aggregate.Snapshot())
		if commit.ExpectedVersion == 0 {
			// 创建时 hotScore 以 0 分落库，保证 sort=hot keyset 谓词无需缺失字段兼容。
			if _, err := s.comments.InsertOne(txCtx, record); err != nil {
				return nil, err
			}
		} else {
			// 只 $set 聚合拥有的字段；hotScore 是 relay 维护的投影字段，
			// 聚合命令不得覆盖（整文档 Replace 会把投影分抹为缺失）。
			aggregateFields, err := commentAggregateSetFields(record)
			if err != nil {
				return nil, err
			}
			updateResult, err := s.comments.UpdateOne(
				txCtx,
				bson.M{"_id": record.ID, "version": commit.ExpectedVersion},
				bson.M{"$set": aggregateFields},
			)
			if err != nil {
				return nil, err
			}
			if updateResult.MatchedCount != 1 {
				return nil, contentgenerated.AppErrorFromVersionConflict(
					"comment version changed before commit",
				)
			}
		}

		for _, event := range commit.Events {
			if _, err := s.outbox.InsertOne(txCtx, commentOutboxDocument{
				ID:               event.EventID,
				EventType:        event.EventType,
				AggregateID:      event.AggregateID,
				AggregateVersion: event.AggregateVersion,
				Payload:          append([]byte(nil), event.Payload...),
				OccurredAt:       event.OccurredAt.UTC(),
			}); err != nil {
				return nil, err
			}
		}

		expiresAt := commit.ReceiptExpiresAt.UTC()
		if expiresAt.IsZero() {
			expiresAt = time.Now().UTC().Add(24 * time.Hour)
		}
		if _, err := s.receipts.InsertOne(txCtx, commentCommandReceiptDocument{
			ID:               commit.IdempotencyKey,
			AggregateID:      record.ID,
			AggregateVersion: record.Version,
			CommandName:      commit.CommandName,
			CommandDigest:    commit.CommandDigest,
			Result:           record,
			CreatedAt:        time.Now().UTC(),
			ExpiresAt:        expiresAt,
		}); err != nil {
			return nil, err
		}
		aggregate, err := record.aggregate()
		if err != nil {
			return nil, err
		}
		result = commentports.CommitResult{Aggregate: aggregate}
		return nil, nil
	})
	if err != nil {
		replayed, found, receiptErr := s.FindReceipt(
			ctx,
			commit.IdempotencyKey,
			commit.CommandName,
			commit.CommandDigest,
		)
		if receiptErr != nil {
			return commentports.CommitResult{}, receiptErr
		}
		if found {
			return replayed, nil
		}
		return commentports.CommitResult{}, err
	}
	return result, nil
}

func (s *MongoCommentDataAdapter) enforceAuthorRateLimit(
	ctx context.Context,
	policy *commentports.AuthorRateLimit,
) error {
	if policy == nil {
		return nil
	}
	authorID := strings.TrimSpace(policy.AuthorID)
	evaluatedAt := policy.EvaluatedAt.UTC()
	if authorID == "" || evaluatedAt.IsZero() || len(policy.Windows) == 0 {
		return contentgenerated.AppErrorFromCommentRateLimited(
			"comment author rate limit policy is incomplete",
		)
	}
	oldestSince := evaluatedAt
	for _, window := range policy.Windows {
		if window.Max > 0 && !window.Since.IsZero() &&
			window.Since.UTC().Before(oldestSince) {
			oldestSince = window.Since.UTC()
		}
	}
	lockTTL := evaluatedAt.Sub(oldestSince)
	if lockTTL <= 0 {
		lockTTL = 24 * time.Hour
	}
	_, err := s.rateLocks.UpdateOne(
		ctx,
		bson.M{"_id": authorID},
		bson.M{
			"$inc": bson.M{"revision": 1},
			"$set": bson.M{
				"updatedAt": evaluatedAt,
				"expiresAt": evaluatedAt.Add(lockTTL),
			},
		},
		options.UpdateOne().SetUpsert(true),
	)
	if err != nil {
		return err
	}
	for _, window := range policy.Windows {
		if window.Max <= 0 || window.Since.IsZero() {
			continue
		}
		count, err := s.comments.CountDocuments(ctx, bson.M{
			"authorId":  authorID,
			"createdAt": bson.M{"$gte": window.Since.UTC()},
		})
		if err != nil {
			return err
		}
		if count >= window.Max {
			return contentgenerated.AppErrorFromCommentRateLimited(
				fmt.Sprintf(
					"comment author rate window exceeded: count=%d max=%d",
					count,
					window.Max,
				),
			)
		}
	}
	return nil
}

func validateCommentCommit(commit commentports.Commit) error {
	if commit.Aggregate == nil || strings.TrimSpace(commit.Aggregate.ID()) == "" {
		return contentgenerated.AppErrorFromVersionConflict("comment commit requires aggregate")
	}
	if commit.ExpectedVersion < 0 {
		return contentgenerated.AppErrorFromVersionConflict("comment expected version must not be negative")
	}
	if strings.TrimSpace(commit.IdempotencyKey) == "" {
		return contentgenerated.AppErrorFromIdempotencyConflict(
			"comment command requires idempotency key",
		)
	}
	if strings.TrimSpace(commit.CommandName) == "" || strings.TrimSpace(commit.CommandDigest) == "" {
		return contentgenerated.AppErrorFromIdempotencyConflict(
			"comment command requires name and digest",
		)
	}
	if commit.Aggregate.Version() != commit.ExpectedVersion+1 {
		return contentgenerated.AppErrorFromVersionConflict(
			"comment aggregate version does not follow expected version",
		)
	}
	if commit.AuthorRateLimit != nil && commit.ExpectedVersion != 0 {
		return contentgenerated.AppErrorFromVersionConflict(
			"comment author rate limit is only valid for aggregate creation",
		)
	}
	if len(commit.Events) == 0 {
		return contentgenerated.AppErrorFromVersionConflict(
			"comment aggregate commit requires an outbox fact",
		)
	}
	eventIDs := make(map[string]struct{}, len(commit.Events))
	for _, event := range commit.Events {
		if strings.TrimSpace(event.EventID) == "" ||
			strings.TrimSpace(event.EventType) == "" ||
			event.AggregateID != commit.Aggregate.ID() ||
			event.AggregateVersion != commit.Aggregate.Version() ||
			event.OccurredAt.IsZero() {
			return contentgenerated.AppErrorFromVersionConflict(
				"comment outbox event does not match aggregate commit",
			)
		}
		if _, found := eventIDs[event.EventID]; found {
			return contentgenerated.AppErrorFromVersionConflict(
				"comment aggregate commit has duplicate outbox event id",
			)
		}
		eventIDs[event.EventID] = struct{}{}
	}
	return nil
}

func (s *MongoCommentDataAdapter) LoadCheckpoint(
	ctx context.Context,
	consumer string,
) (string, error) {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return "", fmt.Errorf("Comment checkpoint consumer is required")
	}
	var document commentCheckpointDocument
	err := s.checkpoints.FindOne(ctx, bson.M{"_id": consumer}).Decode(&document)
	if err == mongo.ErrNoDocuments {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(document.Checkpoint), nil
}

func (s *MongoCommentDataAdapter) SaveCheckpoint(
	ctx context.Context,
	consumer string,
	checkpoint string,
) error {
	consumer = strings.TrimSpace(consumer)
	checkpoint = strings.TrimSpace(checkpoint)
	if consumer == "" || checkpoint == "" {
		return fmt.Errorf("Comment checkpoint consumer and value are required")
	}
	if _, _, err := parseCommentOutboxCheckpoint(checkpoint); err != nil {
		return err
	}
	_, err := s.checkpoints.UpdateOne(
		ctx,
		bson.M{"_id": consumer},
		bson.M{"$set": bson.M{"checkpoint": checkpoint, "updatedAt": time.Now().UTC()}},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

// SetCommentHotScore 写入 hotScore 投影分；hotScore 由 relay 独占维护，
// 聚合命令路径经 commentAggregateSetFields 排除本字段。
func (s *MongoCommentDataAdapter) SetCommentHotScore(
	ctx context.Context,
	commentID string,
	score int64,
) (bool, error) {
	result, err := s.comments.UpdateOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(commentID)},
		bson.M{"$set": bson.M{"hotScore": score}},
	)
	if err != nil {
		return false, err
	}
	return result.MatchedCount == 1, nil
}

// TombstoneCommentsByPost 执行宿主 Post 删除的级联：active|hidden → tombstoned
// 批量迁移，并在同一 Mongo 事务写入按 postId 聚合的 CommentsTombstoned outbox 事实。
// 幂等：重放时候选集为空，零改动且不再追加事实。
func (s *MongoCommentDataAdapter) TombstoneCommentsByPost(
	ctx context.Context,
	postID string,
) (int64, error) {
	postID = strings.TrimSpace(postID)
	if postID == "" {
		return 0, fmt.Errorf("comment tombstone requires post id")
	}
	session, err := s.comments.Database().Client().StartSession()
	if err != nil {
		return 0, err
	}
	defer session.EndSession(ctx)
	var tombstoned int64
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		now := time.Now().UTC()
		result, err := s.comments.UpdateMany(
			txCtx,
			bson.M{
				"postId": postID,
				"status": bson.M{"$in": bson.A{
					string(commentmodel.StatusActive),
					string(commentmodel.StatusHidden),
				}},
			},
			bson.M{
				"$set": bson.M{
					"status":    string(commentmodel.StatusTombstoned),
					"isPinned":  false,
					"updatedAt": now,
				},
				"$unset": bson.M{"pinnedAt": "", "hiddenAt": ""},
				"$inc":   bson.M{"version": 1},
			},
		)
		if err != nil {
			return nil, err
		}
		tombstoned = result.ModifiedCount
		if tombstoned == 0 {
			return nil, nil
		}
		payload, err := json.Marshal(struct {
			PostID          string    `json:"postId"`
			TombstonedCount int64     `json:"tombstonedCount"`
			OccurredAt      time.Time `json:"occurredAt"`
		}{PostID: postID, TombstonedCount: tombstoned, OccurredAt: now})
		if err != nil {
			return nil, err
		}
		eventID := fmt.Sprintf("evt_tombstone_%s_%d", postID, now.UnixNano())
		if _, err := s.outbox.InsertOne(txCtx, commentOutboxDocument{
			ID:               eventID,
			EventType:        "CommentsTombstoned",
			AggregateID:      postID,
			AggregateVersion: 0,
			Payload:          payload,
			OccurredAt:       now,
		}); err != nil {
			return nil, err
		}
		return nil, nil
	})
	if err != nil {
		return 0, err
	}
	return tombstoned, nil
}

func (s *MongoCommentDataAdapter) findReceipt(
	ctx context.Context,
	idempotencyKey string,
) (commentCommandReceiptDocument, bool, error) {
	var receipt commentCommandReceiptDocument
	err := s.receipts.FindOne(ctx, bson.M{"_id": strings.TrimSpace(idempotencyKey)}).Decode(&receipt)
	if err == mongo.ErrNoDocuments {
		return commentCommandReceiptDocument{}, false, nil
	}
	if err != nil {
		return commentCommandReceiptDocument{}, false, err
	}
	return receipt, true, nil
}
