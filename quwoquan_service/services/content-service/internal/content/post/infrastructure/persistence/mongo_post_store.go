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

	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	mediaerrors "quwoquan_service/services/content-service/generated/media/media_asset"
	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/mediareferencefence"
)

type postCommandReceiptDocument struct {
	ID               string         `bson:"_id"`
	AggregateID      string         `bson:"aggregateId"`
	AggregateVersion int64          `bson:"aggregateVersion"`
	CommandName      string         `bson:"commandName"`
	CommandDigest    string         `bson:"commandDigest"`
	Result           postmodel.Post `bson:"result"`
	CreatedAt        time.Time      `bson:"createdAt"`
	ExpiresAt        time.Time      `bson:"expiresAt"`
}

// MongoPostStore 是 Post 聚合、幂等 receipt 与 content outbox 的同库 adapter。
type MongoPostStore struct {
	coll            *mongo.Collection
	receipts        *mongo.Collection
	outbox          *mongo.Collection
	sequences       *mongo.Collection
	checkpoints     *mongo.Collection
	tombstones      *mongo.Collection
	mediaReferences *mediareferencefence.Manager
}

func NewMongoPostStore(coll *mongo.Collection) *MongoPostStore {
	db := coll.Database()
	mediaReferences, err := mediareferencefence.New(db)
	if err != nil {
		panic(err)
	}
	return &MongoPostStore{
		coll:            coll,
		receipts:        db.Collection("post_command_receipts"),
		outbox:          db.Collection("content_outbox"),
		sequences:       db.Collection("content_outbox_sequences"),
		checkpoints:     db.Collection("projection_checkpoints"),
		tombstones:      db.Collection("deleted_post_tombstones"),
		mediaReferences: mediaReferences,
	}
}

// deletedPostTombstoneDocument 是 content.DeletedPostTombstone 的持久化形态：
// _id 复用 postId 作唯一 dedupe key，expireAt TTL 索引承载保留期自动清理。
type deletedPostTombstoneDocument struct {
	ID        string    `bson:"_id"`
	PostID    string    `bson:"postId"`
	AuthorID  string    `bson:"authorId"`
	Reason    string    `bson:"reason"`
	DeletedAt time.Time `bson:"deletedAt"`
	ExpireAt  time.Time `bson:"expireAt"`
}

func (s *MongoPostStore) EnsureIndexes(ctx context.Context) error {
	if _, err := s.coll.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "authorId", Value: 1}, {Key: "status", Value: 1}, {Key: "publishedAt", Value: -1}},
			Options: options.Index().SetName("idx_posts_author_status"),
		},
		{
			Keys:    bson.D{{Key: "contentType", Value: 1}, {Key: "publishedAt", Value: -1}},
			Options: options.Index().SetName("idx_posts_content_type"),
		},
		{
			Keys:    bson.D{{Key: "visibility", Value: 1}, {Key: "publishedAt", Value: -1}},
			Options: options.Index().SetName("idx_posts_visibility"),
		},
		{
			Keys:    bson.D{{Key: "status", Value: 1}, {Key: "publishedAt", Value: -1}},
			Options: options.Index().SetName("idx_posts_status_published"),
		},
		{
			Keys:    bson.D{{Key: "lastActiveAt", Value: -1}},
			Options: options.Index().SetName("idx_posts_last_active").SetSparse(true),
		},
		{
			Keys:    bson.D{{Key: "tagRefs", Value: 1}},
			Options: options.Index().SetName("idx_posts_tag_refs"),
		},
		{
			Keys:    bson.D{{Key: "entityRefs", Value: 1}},
			Options: options.Index().SetName("idx_posts_entity_refs"),
		},
		{
			Keys:    bson.D{{Key: "mediaAssetIds", Value: 1}, {Key: "status", Value: 1}},
			Options: options.Index().SetName("idx_posts_media_asset_status"),
		},
		{
			Keys: bson.D{
				{Key: "illustrationAssetId", Value: 1},
				{Key: "status", Value: 1},
			},
			Options: options.Index().
				SetName("idx_posts_illustration_asset_status").
				SetSparse(true),
		},
		{
			Keys:    bson.D{{Key: "semanticMentions.candidateId", Value: 1}},
			Options: options.Index().SetName("idx_posts_semantic_candidate").SetSparse(true),
		},
		{
			Keys:    bson.D{{Key: "semanticMentions.targetRef", Value: 1}},
			Options: options.Index().SetName("idx_posts_semantic_target").SetSparse(true),
		},
		{
			Keys:    bson.D{{Key: "location", Value: "2dsphere"}},
			Options: options.Index().SetName("idx_posts_location").SetSparse(true),
		},
		{
			Keys:    bson.D{{Key: "moderationStatus", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_posts_moderation"),
		},
		{
			Keys:    bson.D{{Key: "sourceType", Value: 1}, {Key: "sourcePostId", Value: 1}},
			Options: options.Index().SetName("idx_posts_source").SetSparse(true),
		},
		{
			Keys:    bson.D{{Key: "articleMarkdownDigest", Value: 1}},
			Options: options.Index().SetName("idx_posts_article_markdown_digest").SetSparse(true),
		},
		{
			Keys:    bson.D{{Key: "canonicalEntityId", Value: 1}, {Key: "publishedAt", Value: -1}},
			Options: options.Index().SetName("idx_posts_canonical_entity").SetSparse(true),
		},
		{
			Keys: bson.D{
				{Key: "authorId", Value: 1},
				{Key: "publishIntentId", Value: 1},
			},
			Options: options.Index().
				SetName("idx_posts_publish_intent").
				SetUnique(true).
				SetPartialFilterExpression(bson.M{
					"publishIntentId": bson.M{"$type": "string"},
				}),
		},
		{
			Keys: bson.D{
				{Key: "authorId", Value: 1},
				{Key: "localDraftId", Value: 1},
			},
			Options: options.Index().
				SetName("idx_posts_local_draft").
				SetUnique(true).
				SetPartialFilterExpression(bson.M{
					"localDraftId": bson.M{"$type": "string"},
				}),
		},
		{
			Keys:    bson.D{{Key: "_id", Value: 1}, {Key: "version", Value: 1}},
			Options: options.Index().SetName("idx_posts_version").SetUnique(true),
		},
	}); err != nil {
		return err
	}
	if _, err := s.receipts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: -1}},
			Options: options.Index().SetName("idx_post_command_receipts_aggregate"),
		},
		{
			Keys:    bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().SetName("idx_post_command_receipts_expire").SetExpireAfterSeconds(0),
		},
	}); err != nil {
		return err
	}
	if _, err := s.tombstones.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "postId", Value: 1}},
			Options: options.Index().SetName("idx_tombstone_post").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "deletedAt", Value: -1}},
			Options: options.Index().SetName("idx_tombstone_deleted_at"),
		},
		{
			Keys:    bson.D{{Key: "expireAt", Value: 1}},
			Options: options.Index().SetName("idx_tombstone_expire").SetExpireAfterSeconds(0),
		},
	}); err != nil {
		return fmt.Errorf("create deleted post tombstone indexes: %w", err)
	}
	return s.ensureOutboxIndexes(ctx)
}

// FindTombstone 实现 postports.TombstoneReader：保留期内返回墓碑事实，
// TTL 到期（或从未删除）返回 found=false。
func (s *MongoPostStore) FindTombstone(
	ctx context.Context,
	postID string,
) (postports.PostDeletionTombstone, bool, error) {
	var document deletedPostTombstoneDocument
	err := s.tombstones.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(postID)},
	).Decode(&document)
	if err == mongo.ErrNoDocuments {
		return postports.PostDeletionTombstone{}, false, nil
	}
	if err != nil {
		return postports.PostDeletionTombstone{}, false, err
	}
	return postports.PostDeletionTombstone{
		PostID:    document.PostID,
		AuthorID:  document.AuthorID,
		Reason:    document.Reason,
		DeletedAt: document.DeletedAt,
		ExpireAt:  document.ExpireAt,
	}, true, nil
}

func (s *MongoPostStore) Load(ctx context.Context, id string) (*postmodel.Post, bool, error) {
	var post postmodel.Post
	err := s.coll.FindOne(ctx, bson.M{"_id": strings.TrimSpace(id)}).Decode(&post)
	if err == mongo.ErrNoDocuments {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	return &post, true, nil
}

func ValidatePostCommit(commit postports.Commit) error {
	if commit.Post == nil || strings.TrimSpace(commit.Post.ID) == "" {
		return contentgenerated.AppErrorFromVersionConflict("post commit requires aggregate")
	}
	if commit.ExpectedVersion < 0 {
		return contentgenerated.AppErrorFromVersionConflict("post commit expected version must not be negative")
	}
	if strings.TrimSpace(commit.IdempotencyKey) == "" {
		return contentgenerated.AppErrorFromIdempotencyConflict("post command requires idempotency key")
	}
	nextVersion := commit.ExpectedVersion + 1
	for _, event := range commit.Events {
		if strings.TrimSpace(event.EventID) == "" ||
			strings.TrimSpace(event.EventType) == "" ||
			event.AggregateType != "Post" ||
			event.AggregateID != commit.Post.ID ||
			event.AggregateVersion != nextVersion ||
			event.OccurredAt.IsZero() {
			return contentgenerated.AppErrorFromVersionConflict(
				"post outbox event does not match aggregate commit",
			)
		}
	}
	return nil
}

func (s *MongoPostStore) Commit(ctx context.Context, commit postports.Commit) (postports.CommitResult, error) {
	if err := ValidatePostCommit(commit); err != nil {
		return postports.CommitResult{}, err
	}
	session, err := s.coll.Database().Client().StartSession()
	if err != nil {
		return postports.CommitResult{}, err
	}
	defer session.EndSession(ctx)

	var result postports.CommitResult
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		var receipt postCommandReceiptDocument
		receiptErr := s.receipts.FindOne(txCtx, bson.M{"_id": commit.IdempotencyKey}).Decode(&receipt)
		if receiptErr == nil {
			if !receipt.ExpiresAt.After(time.Now().UTC()) {
				if _, err := s.receipts.DeleteOne(txCtx, bson.M{"_id": commit.IdempotencyKey}); err != nil {
					return nil, err
				}
			} else {
				if receipt.CommandName != commit.CommandName || receipt.CommandDigest != commit.CommandDigest {
					return nil, contentgenerated.AppErrorFromIdempotencyConflict("idempotency key was reused with a different command")
				}
				replayed := receipt.Result
				result = postports.CommitResult{Post: &replayed, Replayed: true}
				return nil, nil
			}
		}
		if receiptErr != mongo.ErrNoDocuments {
			return nil, receiptErr
		}

		next := *commit.Post
		next.Version = commit.ExpectedVersion + 1
		if next.Status != "deleted" {
			if err := s.mediaReferences.AllowReferences(
				txCtx,
				postMediaReferences(next),
			); err != nil {
				if errors.Is(err, mediareferencefence.ErrDeletionInProgress) ||
					errors.Is(err, mediareferencefence.ErrReferenceUnavailable) {
					return nil, mediaerrors.AppErrorFromMediaNotFound(
						"media asset became unavailable before Post commit",
					)
				}
				return nil, err
			}
		}
		if commit.ExpectedVersion == 0 {
			if _, insertErr := s.coll.InsertOne(txCtx, &next); insertErr != nil {
				if mongo.IsDuplicateKeyError(insertErr) {
					return nil, contentgenerated.AppErrorFromIdempotencyConflict(
						"post publication identity already committed",
					)
				}
				return nil, insertErr
			}
		} else {
			replaceResult, replaceErr := s.coll.ReplaceOne(
				txCtx,
				bson.M{"_id": next.ID, "version": commit.ExpectedVersion},
				&next,
			)
			if replaceErr != nil {
				return nil, replaceErr
			}
			if replaceResult.MatchedCount != 1 {
				return nil, contentgenerated.AppErrorFromVersionConflict("post version changed before commit")
			}
		}

		if len(commit.Events) > 0 {
			var sequenceCounter struct {
				Value int64 `bson:"value"`
			}
			if sequenceErr := s.sequences.FindOneAndUpdate(
				txCtx,
				bson.M{"_id": "Post"},
				bson.M{"$inc": bson.M{"value": int64(len(commit.Events))}},
				options.FindOneAndUpdate().
					SetUpsert(true).
					SetReturnDocument(options.After),
			).Decode(&sequenceCounter); sequenceErr != nil {
				return nil, sequenceErr
			}
			firstSequence := sequenceCounter.Value - int64(len(commit.Events)) + 1
			documents := make([]any, 0, len(commit.Events))
			for index, event := range commit.Events {
				documents = append(documents, contentOutboxDocument{
					ID:               event.EventID,
					OutboxSequence:   firstSequence + int64(index),
					EventType:        event.EventType,
					AggregateType:    event.AggregateType,
					AggregateID:      next.ID,
					AggregateVersion: next.Version,
					PayloadJSON:      event.Payload,
					OccurredAt:       event.OccurredAt,
				})
			}
			if _, insertErr := s.outbox.InsertMany(txCtx, documents); insertErr != nil {
				return nil, insertErr
			}
		}

		if commit.Tombstone != nil {
			tombstone := deletedPostTombstoneDocument{
				ID:        strings.TrimSpace(commit.Tombstone.PostID),
				PostID:    strings.TrimSpace(commit.Tombstone.PostID),
				AuthorID:  strings.TrimSpace(commit.Tombstone.AuthorID),
				Reason:    strings.TrimSpace(commit.Tombstone.Reason),
				DeletedAt: commit.Tombstone.DeletedAt.UTC(),
				ExpireAt:  commit.Tombstone.ExpireAt.UTC(),
			}
			if _, upsertErr := s.tombstones.UpdateOne(
				txCtx,
				bson.M{"_id": tombstone.ID},
				bson.M{"$setOnInsert": tombstone},
				options.UpdateOne().SetUpsert(true),
			); upsertErr != nil {
				return nil, upsertErr
			}
		}

		expiresAt := commit.ReceiptExpiresAt
		if expiresAt.IsZero() {
			expiresAt = time.Now().UTC().Add(24 * time.Hour)
		}
		if _, insertErr := s.receipts.InsertOne(txCtx, postCommandReceiptDocument{
			ID:               commit.IdempotencyKey,
			AggregateID:      next.ID,
			AggregateVersion: next.Version,
			CommandName:      commit.CommandName,
			CommandDigest:    commit.CommandDigest,
			Result:           next,
			CreatedAt:        time.Now().UTC(),
			ExpiresAt:        expiresAt,
		}); insertErr != nil {
			return nil, insertErr
		}
		result = postports.CommitResult{Post: &next}
		return nil, nil
	})
	if err != nil {
		return postports.CommitResult{}, err
	}
	return result, nil
}

func postMediaReferences(post postmodel.Post) []mediareferencefence.Reference {
	assetIDs := append([]string(nil), post.MediaAssetIds...)
	if illustrationID := strings.TrimSpace(post.IllustrationAssetId); illustrationID != "" {
		assetIDs = append(assetIDs, illustrationID)
	}
	references := make([]mediareferencefence.Reference, 0, len(assetIDs))
	for _, assetID := range assetIDs {
		references = append(references, mediareferencefence.Reference{
			AssetID: assetID,
			OwnerID: post.AuthorId,
		})
	}
	return references
}

func (s *MongoPostStore) FindByID(ctx context.Context, id string) (*postmodel.Post, bool) {
	post, ok, err := s.Load(ctx, id)
	if err != nil || !ok {
		return nil, false
	}
	return post, true
}

func (s *MongoPostStore) FindByPublicationIntent(
	ctx context.Context,
	authorID string,
	publishIntentID string,
) (*postmodel.Post, bool) {
	var post postmodel.Post
	err := s.coll.FindOne(ctx, bson.M{
		"authorId":        strings.TrimSpace(authorID),
		"publishIntentId": strings.TrimSpace(publishIntentID),
	}).Decode(&post)
	if err != nil {
		return nil, false
	}
	return &post, true
}

func (s *MongoPostStore) AdjustCommentCount(ctx context.Context, id string, delta int64) (int64, bool, error) {
	var updated postmodel.Post
	err := s.coll.FindOneAndUpdate(
		ctx,
		bson.M{"_id": id},
		bson.M{
			"$inc": bson.M{"commentCount": delta},
			"$set": bson.M{"updatedAt": time.Now().UTC()},
		},
		options.FindOneAndUpdate().
			SetReturnDocument(options.After).
			SetProjection(bson.M{"commentCount": 1}),
	).Decode(&updated)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return 0, false, nil
		}
		return 0, false, err
	}
	return updated.CommentCount, true, nil
}

func (s *MongoPostStore) SetCommentCount(ctx context.Context, id string, count int64) (bool, error) {
	res, err := s.coll.UpdateOne(
		ctx,
		bson.M{"_id": id},
		bson.M{"$set": bson.M{"commentCount": count, "updatedAt": time.Now().UTC()}},
	)
	if err != nil {
		return false, err
	}
	return res.MatchedCount > 0, nil
}

// SetLikeCount 只写由 ContentReaction 权威集合重建的 projection。
func (s *MongoPostStore) SetLikeCount(ctx context.Context, id string, count int64) (bool, error) {
	if count < 0 {
		return false, fmt.Errorf("Post likeCount cannot be negative")
	}
	res, err := s.coll.UpdateOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(id)},
		bson.M{"$set": bson.M{"likeCount": count, "updatedAt": time.Now().UTC()}},
	)
	if err != nil {
		return false, err
	}
	return res.MatchedCount == 1, nil
}

// SetShareCount 只写由 OutboundShareFact 权威集合重建的 projection。
func (s *MongoPostStore) SetShareCount(ctx context.Context, id string, count int64) (bool, error) {
	if count < 0 {
		return false, fmt.Errorf("Post shareCount cannot be negative")
	}
	res, err := s.coll.UpdateOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(id)},
		bson.M{"$set": bson.M{"shareCount": count, "updatedAt": time.Now().UTC()}},
	)
	if err != nil {
		return false, err
	}
	return res.MatchedCount == 1, nil
}

func (s *MongoPostStore) ListAll(ctx context.Context) ([]postmodel.Post, error) {
	opts := options.Find().SetSort(bson.D{{Key: "createdAt", Value: -1}})
	cur, err := s.coll.Find(ctx, bson.M{}, opts)
	if err != nil {
		return nil, fmt.Errorf("find posts: %w", err)
	}
	defer cur.Close(ctx)

	// 主键、字段类型和读取模型必须同源。任一文档无法解码时，reconcile
	// 必须失败并暴露损坏记录，不能以部分列表继续生成派生读模型。
	var posts []postmodel.Post
	for cur.Next(ctx) {
		var post postmodel.Post
		if err := cur.Decode(&post); err != nil {
			return nil, fmt.Errorf("decode post: %w", err)
		}
		posts = append(posts, post)
	}
	if err := cur.Err(); err != nil {
		return nil, fmt.Errorf("iterate posts: %w", err)
	}
	return posts, nil
}

// ListPublished returns published/public posts in reverse-chronological order.
// cursor is the ID of the last item from the previous page; when set, only
// posts with createdAt earlier than the cursor document are returned.
func (s *MongoPostStore) ListPublished(ctx context.Context, limit int, cursor string) []postmodel.Post {
	if limit <= 0 {
		limit = 20
	}

	filter := bson.M{
		"status":           "published",
		"visibility":       "public",
		"moderationStatus": "approved",
	}

	if cursor != "" {
		var cursorDoc postmodel.Post
		if err := s.coll.FindOne(ctx, bson.M{"_id": cursor}).Decode(&cursorDoc); err == nil {
			filter["createdAt"] = bson.M{"$lt": cursorDoc.CreatedAt}
		}
	}

	opts := options.Find().
		SetSort(bson.D{{Key: "createdAt", Value: -1}}).
		SetLimit(int64(limit))

	cur, err := s.coll.Find(ctx, filter, opts)
	if err != nil {
		return nil
	}
	defer cur.Close(ctx)

	var posts []postmodel.Post
	if err := cur.All(ctx, &posts); err != nil {
		return nil
	}
	return posts
}

func (s *MongoPostStore) ListByAuthor(ctx context.Context, authorID string, limit int, cursor string) []postmodel.Post {
	if limit <= 0 {
		limit = 20
	}
	filter := bson.M{
		"authorId":         authorID,
		"status":           "published",
		"moderationStatus": "approved",
	}
	if cursor != "" {
		var cursorDoc postmodel.Post
		if err := s.coll.FindOne(ctx, bson.M{"_id": cursor}).Decode(&cursorDoc); err == nil {
			filter["publishedAt"] = bson.M{"$lt": cursorDoc.PublishedAt}
		}
	}
	opts := options.Find().
		SetSort(bson.D{{Key: "publishedAt", Value: -1}}).
		SetLimit(int64(limit))

	cur, err := s.coll.Find(ctx, filter, opts)
	if err != nil {
		return nil
	}
	defer cur.Close(ctx)
	var posts []postmodel.Post
	if err := cur.All(ctx, &posts); err != nil {
		return nil
	}
	return posts
}
