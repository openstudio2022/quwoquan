package persistence

import (
	"context"
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
	outbox      *mongo.Collection
	checkpoints *mongo.Collection
	posts       *mongo.Collection
}

func NewMongoCommentDataAdapter(db *mongo.Database) *MongoCommentDataAdapter {
	return &MongoCommentDataAdapter{
		comments:    db.Collection(commentAggregateCollection),
		receipts:    db.Collection(commentReceiptsCollection),
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

// EnsureIndexes creates exactly the named indexes declared by
// contracts/metadata/content/comment/storage.yaml.
func (s *MongoCommentDataAdapter) EnsureIndexes(ctx context.Context) error {
	if _, err := s.comments.Indexes().CreateMany(ctx, commentMongoIndexes()); err != nil {
		return fmt.Errorf("create comment aggregate indexes: %w", err)
	}
	if _, err := s.receipts.Indexes().CreateMany(ctx, commentReceiptMongoIndexes()); err != nil {
		return fmt.Errorf("create comment receipt indexes: %w", err)
	}
	if _, err := s.outbox.Indexes().CreateMany(ctx, commentOutboxMongoIndexes()); err != nil {
		return fmt.Errorf("create comment outbox indexes: %w", err)
	}
	if _, err := s.checkpoints.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "updatedAt", Value: -1}},
		Options: options.Index().SetName("idx_comment_projection_checkpoint_updated"),
	}); err != nil {
		return fmt.Errorf("create comment checkpoint indexes: %w", err)
	}
	return nil
}

func commentMongoIndexes() []mongo.IndexModel {
	return []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "postId", Value: 1},
				{Key: "parentCommentId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "isPinned", Value: -1},
				{Key: "pinnedAt", Value: -1},
				{Key: "createdAt", Value: -1},
				{Key: "_id", Value: -1},
			},
			Options: options.Index().SetName("idx_comments_post_page"),
		},
		{
			Keys: bson.D{
				{Key: "postId", Value: 1},
				{Key: "parentCommentId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "createdAt", Value: -1},
				{Key: "_id", Value: -1},
			},
			Options: options.Index().SetName("idx_comments_reply_page"),
		},
		{
			Keys: bson.D{
				{Key: "parentCommentId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "createdAt", Value: -1},
				{Key: "_id", Value: -1},
			},
			Options: options.Index().SetName("idx_comments_parent_summary"),
		},
		{
			Keys: bson.D{
				{Key: "authorId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "createdAt", Value: -1},
				{Key: "_id", Value: -1},
			},
			Options: options.Index().SetName("idx_comments_author_page"),
		},
		{
			Keys: bson.D{
				{Key: "postId", Value: 1},
				{Key: "createdAt", Value: 1},
			},
			Options: options.Index().SetName("idx_comments_post_created_at"),
		},
		{
			Keys: bson.D{
				{Key: "postId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "deletedAt", Value: 1},
			},
			Options: options.Index().SetName("idx_comments_post_deleted_at"),
		},
		{
			Keys:    bson.D{{Key: "_id", Value: 1}, {Key: "version", Value: 1}},
			Options: options.Index().SetName("idx_comments_version").SetUnique(true),
		},
	}
}

func commentReceiptMongoIndexes() []mongo.IndexModel {
	return []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: -1}},
			Options: options.Index().SetName("idx_comment_command_receipts_aggregate"),
		},
		{
			Keys:    bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().SetName("idx_comment_command_receipts_expire").SetExpireAfterSeconds(0),
		},
	}
}

func commentOutboxMongoIndexes() []mongo.IndexModel {
	return []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "occurredAt", Value: 1}, {Key: "_id", Value: 1}},
			Options: options.Index().SetName("idx_comment_outbox_replay"),
		},
		{
			Keys: bson.D{
				{Key: "aggregateId", Value: 1},
				{Key: "aggregateVersion", Value: 1},
			},
			Options: options.Index().
				SetName("idx_comment_outbox_aggregate_version").
				SetUnique(true),
		},
	}
}

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

		record := commentAggregateDocumentFromSnapshot(commit.Aggregate.Snapshot())
		if commit.ExpectedVersion == 0 {
			if _, err := s.comments.InsertOne(txCtx, record); err != nil {
				return nil, err
			}
		} else {
			replaceResult, err := s.comments.ReplaceOne(
				txCtx,
				bson.M{"_id": record.ID, "version": commit.ExpectedVersion},
				record,
			)
			if err != nil {
				return nil, err
			}
			if replaceResult.MatchedCount != 1 {
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

func (s *MongoCommentDataAdapter) ReadAfter(
	ctx context.Context,
	checkpoint string,
	limit int,
) ([]commentports.OutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	if limit > 1000 {
		limit = 1000
	}
	filter := bson.M{}
	if strings.TrimSpace(checkpoint) != "" {
		occurredAt, eventID, err := parseCommentOutboxCheckpoint(checkpoint)
		if err != nil {
			return nil, err
		}
		filter["$or"] = bson.A{
			bson.M{"occurredAt": bson.M{"$gt": occurredAt}},
			bson.M{"occurredAt": occurredAt, "_id": bson.M{"$gt": eventID}},
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
		return nil, fmt.Errorf("read comment outbox: %w", err)
	}
	defer cursor.Close(ctx)

	events := make([]commentports.OutboxEvent, 0, limit)
	for cursor.Next(ctx) {
		var document commentOutboxDocument
		if err := cursor.Decode(&document); err != nil {
			return nil, fmt.Errorf("decode comment outbox: %w", err)
		}
		events = append(events, commentports.OutboxEvent{
			EventID:          document.ID,
			EventType:        document.EventType,
			AggregateID:      document.AggregateID,
			AggregateVersion: document.AggregateVersion,
			Payload:          append([]byte(nil), document.Payload...),
			OccurredAt:       document.OccurredAt.UTC(),
			Checkpoint:       commentOutboxCheckpoint(document.OccurredAt, document.ID),
		})
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate comment outbox: %w", err)
	}
	return events, nil
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

func (s *MongoCommentDataAdapter) ListByPost(
	ctx context.Context,
	postID string,
	request commentports.PageRequest,
) (commentmodel.Page, error) {
	filter := bson.M{
		"postId":          strings.TrimSpace(postID),
		"parentCommentId": "",
		"status":          string(commentmodel.StatusActive),
	}
	cursor, hasCursor := commentmodel.DecodeCursor(request.Cursor)
	if hasCursor {
		filter["$or"] = topLevelAfter(cursor)
	}
	total, err := s.CountByPost(ctx, postID)
	if err != nil {
		return commentmodel.Page{}, err
	}
	return s.findPage(
		ctx,
		filter,
		bson.D{
			{Key: "isPinned", Value: -1},
			{Key: "pinnedAt", Value: -1},
			{Key: "createdAt", Value: -1},
			{Key: "_id", Value: -1},
		},
		request.Limit,
		total,
	)
}

func (s *MongoCommentDataAdapter) ListReplies(
	ctx context.Context,
	postID string,
	parentCommentID string,
	request commentports.PageRequest,
) (commentmodel.Page, error) {
	filter := bson.M{
		"postId":          strings.TrimSpace(postID),
		"parentCommentId": strings.TrimSpace(parentCommentID),
		"status":          string(commentmodel.StatusActive),
	}
	if cursor, ok := commentmodel.DecodeCursor(request.Cursor); ok {
		filter["$or"] = flatAfter(cursor)
	}
	total, err := s.comments.CountDocuments(ctx, filterWithoutCursor(filter))
	if err != nil {
		return commentmodel.Page{}, err
	}
	return s.findPage(
		ctx,
		filter,
		bson.D{{Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}},
		request.Limit,
		total,
	)
}

func (s *MongoCommentDataAdapter) ReadReplySummaries(
	ctx context.Context,
	parentCommentIDs []string,
	previewLimit int,
) (map[string]commentmodel.ReplySummary, error) {
	parentCommentIDs = uniqueNonEmptyStrings(parentCommentIDs)
	summaries := make(map[string]commentmodel.ReplySummary, len(parentCommentIDs))
	if len(parentCommentIDs) == 0 {
		return summaries, nil
	}
	if previewLimit <= 0 {
		previewLimit = 1
	}
	if previewLimit > 10 {
		previewLimit = 10
	}
	pipeline := mongo.Pipeline{
		{{Key: "$match", Value: bson.M{
			"parentCommentId": bson.M{"$in": parentCommentIDs},
			"status":          string(commentmodel.StatusActive),
		}}},
		{{Key: "$sort", Value: bson.D{
			{Key: "parentCommentId", Value: 1},
			{Key: "createdAt", Value: -1},
			{Key: "_id", Value: -1},
		}}},
		{{Key: "$group", Value: bson.M{
			"_id":   "$parentCommentId",
			"count": bson.M{"$sum": 1},
			"items": bson.M{"$push": "$$ROOT"},
		}}},
		{{Key: "$project", Value: bson.M{
			"count": 1,
			"items": bson.M{"$slice": []any{"$items", previewLimit}},
		}}},
	}
	cursor, err := s.comments.Aggregate(ctx, pipeline)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	for cursor.Next(ctx) {
		var row struct {
			ParentCommentID string                `bson:"_id"`
			Count           int64                 `bson:"count"`
			Items           []commentReadDocument `bson:"items"`
		}
		if err := cursor.Decode(&row); err != nil {
			return nil, err
		}
		preview := make([]commentmodel.ReadModel, 0, len(row.Items))
		for _, document := range row.Items {
			preview = append(preview, document.readModel())
		}
		nextCursor := ""
		if row.Count > int64(len(preview)) && len(preview) > 0 {
			nextCursor = commentmodel.EncodeCursor(commentmodel.CursorFor(preview[len(preview)-1]))
		}
		summaries[row.ParentCommentID] = commentmodel.ReplySummary{
			Count:      row.Count,
			Preview:    preview,
			NextCursor: nextCursor,
		}
	}
	if err := cursor.Err(); err != nil {
		return nil, err
	}
	return summaries, nil
}

func (s *MongoCommentDataAdapter) ListByAuthor(
	ctx context.Context,
	authorID string,
	request commentports.PageRequest,
) (commentmodel.Page, error) {
	filter := bson.M{
		"authorId": strings.TrimSpace(authorID),
		"status":   string(commentmodel.StatusActive),
	}
	if cursor, ok := commentmodel.DecodeCursor(request.Cursor); ok {
		filter["$or"] = flatAfter(cursor)
	}
	total, err := s.comments.CountDocuments(ctx, filterWithoutCursor(filter))
	if err != nil {
		return commentmodel.Page{}, err
	}
	return s.findPage(
		ctx,
		filter,
		bson.D{{Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}},
		request.Limit,
		total,
	)
}

func (s *MongoCommentDataAdapter) ListReceivedByPostAuthor(
	ctx context.Context,
	postAuthorID string,
	postIDs []string,
	request commentports.PageRequest,
) (commentmodel.Page, error) {
	if len(postIDs) == 0 {
		return commentmodel.Page{Items: []commentmodel.ReadModel{}}, nil
	}
	filter := bson.M{
		"postId":   bson.M{"$in": cloneStrings(postIDs)},
		"authorId": bson.M{"$ne": strings.TrimSpace(postAuthorID)},
		"status":   string(commentmodel.StatusActive),
	}
	if cursor, ok := commentmodel.DecodeCursor(request.Cursor); ok {
		filter["$or"] = flatAfter(cursor)
	}
	total, err := s.comments.CountDocuments(ctx, filterWithoutCursor(filter))
	if err != nil {
		return commentmodel.Page{}, err
	}
	return s.findPage(
		ctx,
		filter,
		bson.D{{Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}},
		request.Limit,
		total,
	)
}

func (s *MongoCommentDataAdapter) CountByPost(ctx context.Context, postID string) (int64, error) {
	return s.comments.CountDocuments(ctx, bson.M{
		"postId": strings.TrimSpace(postID),
		"status": string(commentmodel.StatusActive),
	})
}

func (s *MongoCommentDataAdapter) FindReplyTarget(
	ctx context.Context,
	commentID string,
) (commentmodel.ReplyTarget, bool, error) {
	var document commentRelationDocument
	err := s.comments.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(commentID)},
		options.FindOne().SetProjection(commentRelationProjection()),
	).Decode(&document)
	if err == mongo.ErrNoDocuments {
		return commentmodel.ReplyTarget{}, false, nil
	}
	if err != nil {
		return commentmodel.ReplyTarget{}, false, err
	}
	return commentmodel.ReplyTarget{
		ID:              document.ID,
		PostID:          document.PostID,
		AuthorID:        document.AuthorID,
		ParentCommentID: document.ParentCommentID,
		Status:          commentmodel.Status(document.Status),
	}, true, nil
}

func (s *MongoCommentDataAdapter) FindPostOwnership(
	ctx context.Context,
	postID string,
) (commentmodel.PostOwnership, bool, error) {
	var document postOwnershipDocument
	err := s.posts.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(postID)},
		options.FindOne().SetProjection(bson.D{
			{Key: "_id", Value: 1},
			{Key: "authorId", Value: 1},
			{Key: "status", Value: 1},
		}),
	).Decode(&document)
	if err == mongo.ErrNoDocuments {
		return commentmodel.PostOwnership{}, false, nil
	}
	if err != nil {
		return commentmodel.PostOwnership{}, false, err
	}
	return commentmodel.PostOwnership{
		PostID:   document.ID,
		AuthorID: document.AuthorID,
		Active:   strings.TrimSpace(document.Status) != "deleted",
	}, true, nil
}

func (s *MongoCommentDataAdapter) ListOwnedPostIDs(
	ctx context.Context,
	postAuthorID string,
) ([]string, error) {
	cursor, err := s.posts.Find(
		ctx,
		bson.M{
			"authorId": strings.TrimSpace(postAuthorID),
			"status":   bson.M{"$ne": "deleted"},
		},
		options.Find().SetProjection(bson.D{{Key: "_id", Value: 1}}),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	postIDs := []string{}
	for cursor.Next(ctx) {
		var document postIDDocument
		if err := cursor.Decode(&document); err != nil {
			return nil, err
		}
		if id := strings.TrimSpace(document.ID); id != "" {
			postIDs = append(postIDs, id)
		}
	}
	if err := cursor.Err(); err != nil {
		return nil, err
	}
	return postIDs, nil
}

func (s *MongoCommentDataAdapter) FindPostOwnerships(
	ctx context.Context,
	postIDs []string,
) (map[string]commentmodel.PostOwnership, error) {
	postIDs = uniqueNonEmptyStrings(postIDs)
	ownerships := make(map[string]commentmodel.PostOwnership, len(postIDs))
	if len(postIDs) == 0 {
		return ownerships, nil
	}
	cursor, err := s.posts.Find(
		ctx,
		bson.M{"_id": bson.M{"$in": postIDs}},
		options.Find().SetProjection(bson.D{
			{Key: "_id", Value: 1},
			{Key: "authorId", Value: 1},
			{Key: "status", Value: 1},
		}),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	for cursor.Next(ctx) {
		var document postOwnershipDocument
		if err := cursor.Decode(&document); err != nil {
			return nil, err
		}
		ownerships[document.ID] = commentmodel.PostOwnership{
			PostID:   document.ID,
			AuthorID: document.AuthorID,
			Active:   strings.TrimSpace(document.Status) != "deleted",
		}
	}
	if err := cursor.Err(); err != nil {
		return nil, err
	}
	return ownerships, nil
}

func (s *MongoCommentDataAdapter) findPage(
	ctx context.Context,
	filter bson.M,
	sortSpec bson.D,
	limit int,
	total int64,
) (commentmodel.Page, error) {
	limit = normalizeCommentPageLimit(limit)
	cursor, err := s.comments.Find(
		ctx,
		filter,
		options.Find().
			SetProjection(commentReadProjection()).
			SetSort(sortSpec).
			SetLimit(int64(limit+1)),
	)
	if err != nil {
		return commentmodel.Page{}, err
	}
	defer cursor.Close(ctx)

	items := make([]commentmodel.ReadModel, 0, limit+1)
	for cursor.Next(ctx) {
		var document commentReadDocument
		if err := cursor.Decode(&document); err != nil {
			return commentmodel.Page{}, err
		}
		items = append(items, document.readModel())
	}
	if err := cursor.Err(); err != nil {
		return commentmodel.Page{}, err
	}
	nextCursor := ""
	if len(items) > limit {
		items = items[:limit]
		nextCursor = commentmodel.EncodeCursor(commentmodel.CursorFor(items[len(items)-1]))
	}
	return commentmodel.Page{
		Items:      cloneReadModels(items),
		NextCursor: nextCursor,
		Total:      total,
	}, nil
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

func commentReadProjection() bson.D {
	return bson.D{
		{Key: "_id", Value: 1},
		{Key: "version", Value: 1},
		{Key: "postId", Value: 1},
		{Key: "authorId", Value: 1},
		{Key: "authorDisplayNameSnapshot", Value: 1},
		{Key: "authorAvatarUrlSnapshot", Value: 1},
		{Key: "personaContextVersion", Value: 1},
		{Key: "content", Value: 1},
		{Key: "replyToCommentId", Value: 1},
		{Key: "replyToUserId", Value: 1},
		{Key: "parentCommentId", Value: 1},
		{Key: "attachmentMediaIds", Value: 1},
		{Key: "mentions", Value: 1},
		{Key: "assistantMentioned", Value: 1},
		{Key: "assistantReplySource", Value: 1},
		{Key: "assistantCorrectionStatus", Value: 1},
		{Key: "status", Value: 1},
		{Key: "isPinned", Value: 1},
		{Key: "pinnedAt", Value: 1},
		{Key: "createdAt", Value: 1},
		{Key: "updatedAt", Value: 1},
		{Key: "deletedAt", Value: 1},
	}
}

func commentRelationProjection() bson.D {
	return bson.D{
		{Key: "_id", Value: 1},
		{Key: "postId", Value: 1},
		{Key: "authorId", Value: 1},
		{Key: "parentCommentId", Value: 1},
		{Key: "status", Value: 1},
	}
}

func topLevelAfter(cursor commentmodel.Cursor) bson.A {
	createdAt := time.Unix(0, cursor.CreatedAtNano).UTC()
	if cursor.Pinned {
		pinnedAt := time.Unix(0, cursor.PinnedAtNano).UTC()
		return bson.A{
			bson.M{"isPinned": false},
			bson.M{"isPinned": true, "pinnedAt": bson.M{"$lt": pinnedAt}},
			bson.M{"isPinned": true, "pinnedAt": pinnedAt, "createdAt": bson.M{"$lt": createdAt}},
			bson.M{
				"isPinned":  true,
				"pinnedAt":  pinnedAt,
				"createdAt": createdAt,
				"_id":       bson.M{"$lt": cursor.ID},
			},
		}
	}
	return bson.A{
		bson.M{
			"isPinned":  false,
			"createdAt": bson.M{"$lt": createdAt},
		},
		bson.M{
			"isPinned":  false,
			"createdAt": createdAt,
			"_id":       bson.M{"$lt": cursor.ID},
		},
	}
}

func flatAfter(cursor commentmodel.Cursor) bson.A {
	createdAt := time.Unix(0, cursor.CreatedAtNano).UTC()
	return bson.A{
		bson.M{"createdAt": bson.M{"$lt": createdAt}},
		bson.M{"createdAt": createdAt, "_id": bson.M{"$lt": cursor.ID}},
	}
}

func filterWithoutCursor(filter bson.M) bson.M {
	out := make(bson.M, len(filter))
	for key, value := range filter {
		if key != "$or" {
			out[key] = value
		}
	}
	return out
}

func normalizeCommentPageLimit(limit int) int {
	if limit <= 0 {
		return 20
	}
	if limit > 100 {
		return 100
	}
	return limit
}

func commentOutboxCheckpoint(occurredAt time.Time, eventID string) string {
	return occurredAt.UTC().Format(time.RFC3339Nano) + "|" + eventID
}

func parseCommentOutboxCheckpoint(checkpoint string) (time.Time, string, error) {
	occurredAtValue, eventID, found := strings.Cut(strings.TrimSpace(checkpoint), "|")
	if !found || strings.TrimSpace(eventID) == "" {
		return time.Time{}, "", fmt.Errorf("invalid comment outbox checkpoint")
	}
	occurredAt, err := time.Parse(time.RFC3339Nano, occurredAtValue)
	if err != nil {
		return time.Time{}, "", fmt.Errorf("invalid comment outbox checkpoint: %w", err)
	}
	return occurredAt.UTC(), eventID, nil
}
