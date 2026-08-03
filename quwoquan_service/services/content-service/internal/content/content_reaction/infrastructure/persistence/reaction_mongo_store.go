package persistence

// This package is the ContentReaction object's Mongo adapter.

import (
	"context"
	"encoding/json"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
)

const (
	contentReactionAggregateCollection  = "content_reaction_aggregates"
	contentReactionReceiptCollection    = "content_reaction_command_receipts"
	contentReactionOutboxCollection     = "content_reaction_outbox"
	contentReactionSequenceCollection   = "content_reaction_outbox_sequences"
	contentReactionCheckpointCollection = "content_reaction_projection_checkpoints"
)

type contentReactionDocument struct {
	ID             string     `bson:"_id"`
	Version        int64      `bson:"version"`
	TargetKind     string     `bson:"targetKind"`
	TargetID       string     `bson:"targetId"`
	ActorDimension string     `bson:"actorDimension"`
	ActorID        string     `bson:"actorId"`
	Reaction       string     `bson:"reaction"`
	ReactedAt      *time.Time `bson:"reactedAt,omitempty"`
	CreatedAt      time.Time  `bson:"createdAt"`
	UpdatedAt      time.Time  `bson:"updatedAt"`
}

type contentReactionReceiptDocument struct {
	ID               string                  `bson:"_id"`
	AggregateID      string                  `bson:"aggregateId"`
	AggregateVersion int64                   `bson:"aggregateVersion"`
	CommandName      string                  `bson:"commandName"`
	CommandDigest    string                  `bson:"commandDigest"`
	Result           contentReactionDocument `bson:"result"`
	Changed          bool                    `bson:"changed"`
	CreatedAt        time.Time               `bson:"createdAt"`
	ExpiresAt        time.Time               `bson:"expiresAt"`
}

type contentReactionOutboxDocument struct {
	ID               string          `bson:"_id"`
	OutboxSequence   int64           `bson:"outboxSequence"`
	EventType        string          `bson:"eventType"`
	AggregateID      string          `bson:"aggregateId"`
	AggregateVersion int64           `bson:"aggregateVersion"`
	PayloadJSON      json.RawMessage `bson:"payloadJson"`
	OccurredAt       time.Time       `bson:"occurredAt"`
}

type contentReactionStateProjection struct {
	TargetID  string    `bson:"targetId"`
	Reaction  string    `bson:"reaction"`
	Version   int64     `bson:"version"`
	UpdatedAt time.Time `bson:"updatedAt"`
}

// MongoContentReactionStore 是 ContentReaction 聚合、receipt、outbox 和状态 Slice 的生产 adapter。
type MongoContentReactionStore struct {
	aggregates  *mongo.Collection
	receipts    *mongo.Collection
	outbox      *mongo.Collection
	sequences   *mongo.Collection
	checkpoints *mongo.Collection
}

var _ reactionports.AggregateStore = (*MongoContentReactionStore)(nil)
var _ reactionapp.ContentReactionStateReader = (*MongoContentReactionStore)(nil)
var _ reactionapp.CommentReactionCountReader = (*MongoContentReactionStore)(nil)
var _ reactionports.CommentReactionValueReader = (*MongoContentReactionStore)(nil)
var _ commentapp.CommentReactionProjectionReader = (*MongoContentReactionStore)(nil)

func NewMongoContentReactionStore(db *mongo.Database) *MongoContentReactionStore {
	return &MongoContentReactionStore{
		aggregates:  db.Collection(contentReactionAggregateCollection),
		receipts:    db.Collection(contentReactionReceiptCollection),
		outbox:      db.Collection(contentReactionOutboxCollection),
		sequences:   db.Collection(contentReactionSequenceCollection),
		checkpoints: db.Collection(contentReactionCheckpointCollection),
	}
}

func (s *MongoContentReactionStore) EnsureIndexes(ctx context.Context) error {
	if _, err := s.aggregates.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "targetKind", Value: 1},
				{Key: "targetId", Value: 1},
				{Key: "actorDimension", Value: 1},
				{Key: "actorId", Value: 1},
			},
			Options: options.Index().SetName("idx_content_reaction_unique_actor").SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "targetKind", Value: 1},
				{Key: "targetId", Value: 1},
				{Key: "reaction", Value: 1},
				{Key: "updatedAt", Value: -1},
			},
			Options: options.Index().SetName("idx_content_reaction_target_value"),
		},
		{
			Keys: bson.D{
				{Key: "actorDimension", Value: 1},
				{Key: "actorId", Value: 1},
				{Key: "updatedAt", Value: -1},
			},
			Options: options.Index().SetName("idx_content_reaction_actor_history"),
		},
		{
			Keys:    bson.D{{Key: "_id", Value: 1}, {Key: "version", Value: 1}},
			Options: options.Index().SetName("idx_content_reaction_version").SetUnique(true),
		},
	}); err != nil {
		return err
	}
	if _, err := s.receipts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: -1}},
			Options: options.Index().SetName("idx_content_reaction_receipt_aggregate"),
		},
		{
			Keys:    bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().SetName("idx_content_reaction_receipt_expire").SetExpireAfterSeconds(0),
		},
	}); err != nil {
		return err
	}
	_, err := s.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{{Key: "outboxSequence", Value: 1}},
			Options: options.Index().
				SetName("idx_content_reaction_outbox_sequence").
				SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "aggregateId", Value: 1},
				{Key: "aggregateVersion", Value: 1},
			},
			Options: options.Index().
				SetName("idx_content_reaction_outbox_aggregate_version").
				SetUnique(true),
		},
	})
	return err
}

func (s *MongoContentReactionStore) Load(
	ctx context.Context,
	aggregateID string,
) (*reactiondomain.ContentReaction, bool, error) {
	var document contentReactionDocument
	err := s.aggregates.FindOne(
		ctx,
		bson.D{{Key: "_id", Value: strings.TrimSpace(aggregateID)}},
	).Decode(&document)
	if err == mongo.ErrNoDocuments {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	aggregate, err := ReactionFromDocument(document)
	if err != nil {
		return nil, false, err
	}
	return aggregate, true, nil
}

func (s *MongoContentReactionStore) FindReceipt(
	ctx context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (reactionports.CommitResult, bool, error) {
	var receipt contentReactionReceiptDocument
	err := s.receipts.FindOne(
		ctx,
		bson.D{{Key: "_id", Value: strings.TrimSpace(idempotencyKey)}},
	).Decode(&receipt)
	if err == mongo.ErrNoDocuments {
		return reactionports.CommitResult{}, false, nil
	}
	if err != nil {
		return reactionports.CommitResult{}, false, err
	}
	if !receipt.ExpiresAt.After(time.Now().UTC()) {
		return reactionports.CommitResult{}, false, nil
	}
	if receipt.CommandName != commandName || receipt.CommandDigest != commandDigest {
		return reactionports.CommitResult{},
			false,
			contentgenerated.AppErrorFromIdempotencyConflict("reaction receipt command mismatch")
	}
	aggregate, err := ReactionFromDocument(receipt.Result)
	if err != nil {
		return reactionports.CommitResult{}, false, err
	}
	return reactionports.CommitResult{
		Aggregate: aggregate,
		Changed:   receipt.Changed,
		Replayed:  true,
	}, true, nil
}

func (s *MongoContentReactionStore) Commit(
	ctx context.Context,
	commit reactionports.Commit,
) (reactionports.CommitResult, error) {
	if err := ValidateReactionCommit(commit); err != nil {
		return reactionports.CommitResult{}, err
	}
	session, err := s.aggregates.Database().Client().StartSession()
	if err != nil {
		return reactionports.CommitResult{}, err
	}
	defer session.EndSession(ctx)

	var result reactionports.CommitResult
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		var receipt contentReactionReceiptDocument
		receiptErr := s.receipts.FindOne(
			txCtx,
			bson.D{{Key: "_id", Value: commit.IdempotencyKey}},
		).Decode(&receipt)
		if receiptErr == nil {
			if receipt.ExpiresAt.After(time.Now().UTC()) {
				if receipt.CommandName != commit.CommandName ||
					receipt.CommandDigest != commit.CommandDigest {
					return nil, contentgenerated.AppErrorFromIdempotencyConflict(
						"reaction receipt command mismatch",
					)
				}
				replayed, restoreErr := ReactionFromDocument(receipt.Result)
				if restoreErr != nil {
					return nil, restoreErr
				}
				result = reactionports.CommitResult{
					Aggregate: replayed,
					Changed:   receipt.Changed,
					Replayed:  true,
				}
				return nil, nil
			}
			if _, deleteErr := s.receipts.DeleteOne(
				txCtx,
				bson.D{{Key: "_id", Value: commit.IdempotencyKey}},
			); deleteErr != nil {
				return nil, deleteErr
			}
		} else if receiptErr != mongo.ErrNoDocuments {
			return nil, receiptErr
		}

		snapshot := commit.Aggregate.Snapshot()
		document := ReactionDocumentFromSnapshot(snapshot)
		mutatesAggregate := snapshot.Version == commit.ExpectedVersion+1
		if mutatesAggregate {
			if commit.ExpectedVersion == 0 {
				if _, insertErr := s.aggregates.InsertOne(txCtx, document); insertErr != nil {
					if mongo.IsDuplicateKeyError(insertErr) {
						return nil, contentgenerated.AppErrorFromVersionConflict(
							"reaction aggregate already exists",
						)
					}
					return nil, insertErr
				}
			} else {
				replaceResult, replaceErr := s.aggregates.ReplaceOne(
					txCtx,
					bson.D{
						{Key: "_id", Value: document.ID},
						{Key: "version", Value: commit.ExpectedVersion},
					},
					document,
				)
				if replaceErr != nil {
					return nil, replaceErr
				}
				if replaceResult.MatchedCount != 1 {
					return nil, contentgenerated.AppErrorFromVersionConflict(
						"reaction version changed before commit",
					)
				}
			}
		} else {
			count, countErr := s.aggregates.CountDocuments(
				txCtx,
				bson.D{
					{Key: "_id", Value: document.ID},
					{Key: "version", Value: commit.ExpectedVersion},
				},
				options.Count().SetLimit(1),
			)
			if countErr != nil {
				return nil, countErr
			}
			if count != 1 {
				return nil, contentgenerated.AppErrorFromVersionConflict(
					"reaction noop command used stale version",
				)
			}
		}

		firstSequence := int64(0)
		if len(commit.Events) > 0 {
			var sequenceCounter struct {
				Value int64 `bson:"value"`
			}
			if sequenceErr := s.sequences.FindOneAndUpdate(
				txCtx,
				bson.M{"_id": "ContentReaction"},
				bson.M{"$inc": bson.M{"value": int64(len(commit.Events))}},
				options.FindOneAndUpdate().
					SetUpsert(true).
					SetReturnDocument(options.After),
			).Decode(&sequenceCounter); sequenceErr != nil {
				return nil, sequenceErr
			}
			firstSequence = sequenceCounter.Value - int64(len(commit.Events)) + 1
		}
		for index, fact := range commit.Events {
			if _, insertErr := s.outbox.InsertOne(txCtx, contentReactionOutboxDocument{
				ID:               fact.EventID,
				OutboxSequence:   firstSequence + int64(index),
				EventType:        fact.EventType,
				AggregateID:      fact.AggregateID,
				AggregateVersion: fact.AggregateVersion,
				PayloadJSON:      append(json.RawMessage(nil), fact.Payload...),
				OccurredAt:       fact.OccurredAt,
			}); insertErr != nil {
				return nil, insertErr
			}
		}

		expiresAt := commit.ReceiptExpiresAt
		if expiresAt.IsZero() {
			expiresAt = time.Now().UTC().Add(24 * time.Hour)
		}
		if _, insertErr := s.receipts.InsertOne(txCtx, contentReactionReceiptDocument{
			ID:               commit.IdempotencyKey,
			AggregateID:      document.ID,
			AggregateVersion: document.Version,
			CommandName:      commit.CommandName,
			CommandDigest:    commit.CommandDigest,
			Result:           document,
			Changed:          commit.Changed,
			CreatedAt:        time.Now().UTC(),
			ExpiresAt:        expiresAt,
		}); insertErr != nil {
			if mongo.IsDuplicateKeyError(insertErr) {
				return nil, contentgenerated.AppErrorFromIdempotencyConflict(
					"reaction receipt already exists",
				)
			}
			return nil, insertErr
		}
		aggregate, restoreErr := ReactionFromDocument(document)
		if restoreErr != nil {
			return nil, restoreErr
		}
		result = reactionports.CommitResult{
			Aggregate: aggregate,
			Changed:   commit.Changed,
		}
		return nil, nil
	})
	if err != nil {
		return reactionports.CommitResult{}, err
	}
	return result, nil
}

func (s *MongoContentReactionStore) ReadContentReactionState(
	ctx context.Context,
	identity reactiondomain.Identity,
) (reactionapp.ContentReactionStateSlice, error) {
	var projection contentReactionStateProjection
	err := s.aggregates.FindOne(
		ctx,
		reactionIdentityFilter(identity),
		options.FindOne().SetProjection(bson.D{
			{Key: "targetId", Value: 1},
			{Key: "reaction", Value: 1},
			{Key: "version", Value: 1},
			{Key: "updatedAt", Value: 1},
		}),
	).Decode(&projection)
	if err == mongo.ErrNoDocuments {
		return reactionapp.ContentReactionStateSlice{
			PostID: identity.Target.ID,
		}, nil
	}
	if err != nil {
		return reactionapp.ContentReactionStateSlice{}, err
	}
	return reactionapp.ContentReactionStateSlice{
		Found:     true,
		PostID:    projection.TargetID,
		Liked:     projection.Reaction == string(reactiondomain.ValueLike),
		Version:   projection.Version,
		UpdatedAt: projection.UpdatedAt.UTC(),
	}, nil
}

func (s *MongoContentReactionStore) CountCommentReactions(
	ctx context.Context,
	commentID string,
) (int64, int64, error) {
	base := bson.M{
		"targetKind": string(reactiondomain.TargetKindComment),
		"targetId":   strings.TrimSpace(commentID),
	}
	likeFilter := bson.M{}
	for key, value := range base {
		likeFilter[key] = value
	}
	likeFilter["reaction"] = string(reactiondomain.ValueLike)
	likeCount, err := s.aggregates.CountDocuments(ctx, likeFilter)
	if err != nil {
		return 0, 0, err
	}
	dislikeFilter := bson.M{}
	for key, value := range base {
		dislikeFilter[key] = value
	}
	dislikeFilter["reaction"] = string(reactiondomain.ValueDislike)
	dislikeCount, err := s.aggregates.CountDocuments(ctx, dislikeFilter)
	if err != nil {
		return 0, 0, err
	}
	return likeCount, dislikeCount, nil
}

func (s *MongoContentReactionStore) ReadCommentReactionCounts(
	ctx context.Context,
	commentIDs []string,
) (map[string]reactiondomain.CommentReactionCounts, error) {
	commentIDs = uniqueNonEmptyStrings(commentIDs)
	counts := make(map[string]reactiondomain.CommentReactionCounts, len(commentIDs))
	if len(commentIDs) == 0 {
		return counts, nil
	}
	cursor, err := s.aggregates.Aggregate(ctx, mongo.Pipeline{
		{{Key: "$match", Value: bson.M{
			"targetKind": string(reactiondomain.TargetKindComment),
			"targetId":   bson.M{"$in": commentIDs},
			"reaction": bson.M{"$in": []string{
				string(reactiondomain.ValueLike),
				string(reactiondomain.ValueDislike),
			}},
		}}},
		{{Key: "$group", Value: bson.M{
			"_id": bson.M{
				"targetId": "$targetId",
				"reaction": "$reaction",
			},
			"count": bson.M{"$sum": 1},
		}}},
	})
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	for cursor.Next(ctx) {
		var row struct {
			ID struct {
				TargetID string `bson:"targetId"`
				Reaction string `bson:"reaction"`
			} `bson:"_id"`
			Count int64 `bson:"count"`
		}
		if err := cursor.Decode(&row); err != nil {
			return nil, err
		}
		value := counts[row.ID.TargetID]
		switch reactiondomain.Value(row.ID.Reaction) {
		case reactiondomain.ValueLike:
			value.LikeCount = row.Count
		case reactiondomain.ValueDislike:
			value.DislikeCount = row.Count
		}
		counts[row.ID.TargetID] = value
	}
	if err := cursor.Err(); err != nil {
		return nil, err
	}
	return counts, nil
}

func uniqueNonEmptyStrings(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	return result
}

func (s *MongoContentReactionStore) ReadCommentReactionValues(
	ctx context.Context,
	actor reactiondomain.Actor,
	commentIDs []string,
) (map[string]reactiondomain.Value, error) {
	if err := actor.Validate(); err != nil {
		return nil, err
	}
	ids := make([]string, 0, len(commentIDs))
	for _, commentID := range commentIDs {
		if commentID = strings.TrimSpace(commentID); commentID != "" {
			ids = append(ids, commentID)
		}
	}
	values := map[string]reactiondomain.Value{}
	if len(ids) == 0 {
		return values, nil
	}
	cursor, err := s.aggregates.Find(
		ctx,
		bson.M{
			"targetKind":     string(reactiondomain.TargetKindComment),
			"targetId":       bson.M{"$in": ids},
			"actorDimension": string(actor.Dimension),
			"actorId":        actor.ID,
			"reaction":       bson.M{"$ne": string(reactiondomain.ValueNone)},
		},
		options.Find().SetProjection(bson.M{"targetId": 1, "reaction": 1}),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var rows []struct {
		TargetID string `bson:"targetId"`
		Reaction string `bson:"reaction"`
	}
	if err := cursor.All(ctx, &rows); err != nil {
		return nil, err
	}
	for _, row := range rows {
		value := reactiondomain.Value(row.Reaction)
		if err := value.ValidateFor(reactiondomain.TargetKindComment); err != nil {
			return nil, err
		}
		if value != reactiondomain.ValueNone {
			values[row.TargetID] = value
		}
	}
	return values, nil
}

// ReadAuthorLikedFlags 批量返回「Post 作者赞过该评论」事实：入参按 postAuthorId
// 分组 commentIds，单次 $or 查询覆盖全部分组，返回 commentId → liked。
func (s *MongoContentReactionStore) ReadAuthorLikedFlags(
	ctx context.Context,
	commentIDsByPostAuthor map[string][]string,
) (map[string]bool, error) {
	flags := map[string]bool{}
	predicates := make(bson.A, 0, len(commentIDsByPostAuthor))
	for postAuthorID, commentIDs := range commentIDsByPostAuthor {
		postAuthorID = strings.TrimSpace(postAuthorID)
		ids := make([]string, 0, len(commentIDs))
		for _, commentID := range commentIDs {
			if commentID = strings.TrimSpace(commentID); commentID != "" {
				ids = append(ids, commentID)
			}
		}
		if postAuthorID == "" || len(ids) == 0 {
			continue
		}
		predicates = append(predicates, bson.M{
			"actorId":  postAuthorID,
			"targetId": bson.M{"$in": ids},
		})
	}
	if len(predicates) == 0 {
		return flags, nil
	}
	cursor, err := s.aggregates.Find(
		ctx,
		bson.M{
			"targetKind":     string(reactiondomain.TargetKindComment),
			"actorDimension": string(reactiondomain.ActorDimensionPersona),
			"reaction":       string(reactiondomain.ValueLike),
			"$or":            predicates,
		},
		options.Find().SetProjection(bson.M{"targetId": 1}),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var rows []struct {
		TargetID string `bson:"targetId"`
	}
	if err := cursor.All(ctx, &rows); err != nil {
		return nil, err
	}
	for _, row := range rows {
		flags[row.TargetID] = true
	}
	return flags, nil
}

func ValidateReactionCommit(commit reactionports.Commit) error {
	if commit.Aggregate == nil || strings.TrimSpace(commit.Aggregate.ID()) == "" {
		return contentgenerated.AppErrorFromVersionConflict("reaction commit requires aggregate")
	}
	if commit.ExpectedVersion < 0 || strings.TrimSpace(commit.IdempotencyKey) == "" {
		return contentgenerated.AppErrorFromIdempotencyConflict(
			"reaction commit requires non-negative version and idempotency key",
		)
	}
	snapshot := commit.Aggregate.Snapshot()
	mutatesAggregate := snapshot.Version == commit.ExpectedVersion+1
	isNoop := snapshot.Version == commit.ExpectedVersion
	if !mutatesAggregate && !isNoop {
		return contentgenerated.AppErrorFromVersionConflict("reaction version is not monotonic")
	}
	if commit.Changed && !mutatesAggregate {
		return contentgenerated.AppErrorFromVersionConflict(
			"reaction changed command did not advance aggregate version",
		)
	}
	if len(commit.Events) > 0 && (!commit.Changed || !mutatesAggregate) {
		return contentgenerated.AppErrorFromVersionConflict(
			"reaction outbox must only accompany a changed aggregate version",
		)
	}
	for _, event := range commit.Events {
		if strings.TrimSpace(event.EventID) == "" ||
			strings.TrimSpace(event.EventType) == "" ||
			event.AggregateID != snapshot.ID ||
			event.AggregateVersion != snapshot.Version ||
			event.OccurredAt.IsZero() {
			return contentgenerated.AppErrorFromVersionConflict(
				"reaction outbox fact does not match aggregate version",
			)
		}
	}
	return nil
}

func reactionIdentityFilter(identity reactiondomain.Identity) bson.D {
	return bson.D{
		{Key: "targetKind", Value: string(identity.Target.Kind)},
		{Key: "targetId", Value: identity.Target.ID},
		{Key: "actorDimension", Value: string(identity.Actor.Dimension)},
		{Key: "actorId", Value: identity.Actor.ID},
	}
}

func ReactionDocumentFromSnapshot(snapshot reactiondomain.Snapshot) contentReactionDocument {
	return contentReactionDocument{
		ID:             snapshot.ID,
		Version:        snapshot.Version,
		TargetKind:     string(snapshot.Identity.Target.Kind),
		TargetID:       snapshot.Identity.Target.ID,
		ActorDimension: string(snapshot.Identity.Actor.Dimension),
		ActorID:        snapshot.Identity.Actor.ID,
		Reaction:       string(snapshot.Value),
		ReactedAt:      copyReactionTime(snapshot.ReactedAt),
		CreatedAt:      snapshot.CreatedAt.UTC(),
		UpdatedAt:      snapshot.UpdatedAt.UTC(),
	}
}

func ReactionFromDocument(document contentReactionDocument) (*reactiondomain.ContentReaction, error) {
	actor, err := reactiondomain.NewActor(
		reactiondomain.ActorDimension(document.ActorDimension),
		document.ActorID,
	)
	if err != nil {
		return nil, err
	}
	target, err := reactiondomain.NewTarget(
		reactiondomain.TargetKind(document.TargetKind),
		document.TargetID,
	)
	if err != nil {
		return nil, err
	}
	identity, err := reactiondomain.NewIdentity(target, actor)
	if err != nil {
		return nil, err
	}
	return reactiondomain.Restore(reactiondomain.Snapshot{
		ID:        document.ID,
		Version:   document.Version,
		Identity:  identity,
		Value:     reactiondomain.Value(document.Reaction),
		ReactedAt: copyReactionTime(document.ReactedAt),
		CreatedAt: document.CreatedAt,
		UpdatedAt: document.UpdatedAt,
	})
}

func copyReactionTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	copied := value.UTC()
	return &copied
}
