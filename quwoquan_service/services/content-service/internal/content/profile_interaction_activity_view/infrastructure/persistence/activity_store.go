package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	activitymodel "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/domain/model"
	activityports "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/domain/ports"
)

const activityCollection = "profile_interaction_activity_views"

type activityDocument struct {
	ID                     string `bson:"_id"`
	activitymodel.Activity `bson:",inline"`
}

type MongoActivityStore struct {
	collection *mongo.Collection
}

func NewMongoActivityStore(db *mongo.Database) *MongoActivityStore {
	if db == nil {
		panic("ProfileInteractionActivity Mongo store requires database")
	}
	return &MongoActivityStore{collection: db.Collection(activityCollection)}
}

func (s *MongoActivityStore) EnsureIndexes(ctx context.Context) error {
	_, err := s.collection.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "ownerPersonaId", Value: 1},
				{Key: "direction", Value: 1},
				{Key: "activityId", Value: 1},
			},
			Options: options.Index().SetName("idx_profile_interaction_identity").SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "ownerPersonaId", Value: 1},
				{Key: "direction", Value: 1},
				{Key: "activityType", Value: 1},
				{Key: "active", Value: 1},
				{Key: "occurredAt", Value: -1},
				{Key: "activityId", Value: -1},
			},
			Options: options.Index().SetName("idx_profile_interaction_page"),
		},
		{
			Keys: bson.D{
				{Key: "sourceType", Value: 1},
				{Key: "sourceEventId", Value: 1},
				{Key: "direction", Value: 1},
			},
			Options: options.Index().SetName("idx_profile_interaction_source").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "targetContentId", Value: 1}, {Key: "active", Value: 1}},
			Options: options.Index().SetName("idx_profile_interaction_target"),
		},
		{
			Keys:    bson.D{{Key: "commentId", Value: 1}, {Key: "ownerPersonaId", Value: 1}},
			Options: options.Index().SetName("idx_profile_interaction_comment").SetSparse(true),
		},
	})
	return err
}

func (s *MongoActivityStore) Upsert(
	ctx context.Context,
	activity activitymodel.Activity,
) error {
	if !activity.Valid() {
		return fmt.Errorf("ProfileInteractionActivity projection row is invalid")
	}
	document, err := activitySetDocument(activity)
	if err != nil {
		return err
	}
	documentID := activityDocumentID(
		activity.OwnerPersonaID,
		activity.Direction,
		activity.ActivityID,
	)
	result, err := s.collection.UpdateOne(
		ctx,
		bson.M{
			"_id": documentID,
			"$or": bson.A{
				bson.M{"sourceVersion": bson.M{"$lt": activity.SourceVersion}},
				bson.M{"sourceVersion": bson.M{"$exists": false}},
			},
		},
		bson.M{
			"$set": document,
		},
	)
	if err != nil {
		return fmt.Errorf("upsert ProfileInteractionActivity projection: %w", err)
	}
	if result.MatchedCount == 1 {
		return nil
	}
	_, err = s.collection.InsertOne(ctx, activityDocument{
		ID:       documentID,
		Activity: activity,
	})
	if mongo.IsDuplicateKeyError(err) {
		// 已有更新版本或并发消费者率先写入；旧事件重放不得覆盖新快照。
		return nil
	}
	if err != nil {
		return fmt.Errorf("insert ProfileInteractionActivity projection: %w", err)
	}
	return nil
}

func activitySetDocument(activity activitymodel.Activity) (bson.M, error) {
	data, err := bson.Marshal(activity)
	if err != nil {
		return nil, fmt.Errorf("encode ProfileInteractionActivity projection: %w", err)
	}
	var document bson.M
	if err := bson.Unmarshal(data, &document); err != nil {
		return nil, fmt.Errorf("decode ProfileInteractionActivity projection document: %w", err)
	}
	delete(document, "seenAt")
	delete(document, "readAt")
	return document, nil
}

func (s *MongoActivityStore) DeactivateActivity(
	ctx context.Context,
	activityID string,
	sourceVersion int64,
) error {
	if strings.TrimSpace(activityID) == "" || sourceVersion <= 0 {
		return fmt.Errorf("activity id and source version are required")
	}
	_, err := s.collection.UpdateMany(
		ctx,
		bson.M{
			"activityId":    strings.TrimSpace(activityID),
			"sourceVersion": bson.M{"$lt": sourceVersion},
		},
		bson.M{
			"$set": bson.M{"active": false},
			"$max": bson.M{"sourceVersion": sourceVersion},
		},
	)
	return err
}

func (s *MongoActivityStore) SetCommentViewerReaction(
	ctx context.Context,
	commentID string,
	ownerPersonaID string,
	reaction string,
	sourceVersion int64,
) error {
	if strings.TrimSpace(commentID) == "" ||
		strings.TrimSpace(ownerPersonaID) == "" ||
		sourceVersion <= 0 {
		return fmt.Errorf("comment reaction projection identity is incomplete")
	}
	if reaction != "like" && reaction != "dislike" {
		reaction = "none"
	}
	_, err := s.collection.UpdateMany(
		ctx,
		bson.M{
			"commentId":      commentID,
			"ownerPersonaId": ownerPersonaID,
			"active":         true,
			"$or": bson.A{
				bson.M{"viewerReactionVersion": bson.M{"$lt": sourceVersion}},
				bson.M{"viewerReactionVersion": bson.M{"$exists": false}},
			},
		},
		bson.M{"$set": bson.M{
			"viewerReaction":        reaction,
			"viewerReactionVersion": sourceVersion,
		}},
	)
	return err
}

func (s *MongoActivityStore) MarkTargetUnavailable(
	ctx context.Context,
	postID string,
	targetVersion int64,
	at time.Time,
) error {
	if strings.TrimSpace(postID) == "" || targetVersion <= 0 || at.IsZero() {
		return fmt.Errorf("deleted target identity is incomplete")
	}
	_, err := s.collection.UpdateMany(
		ctx,
		bson.M{
			"targetContentId": strings.TrimSpace(postID),
			"targetVersion":   bson.M{"$lt": targetVersion},
		},
		bson.M{
			"$set": bson.M{
				"targetAvailability": "deleted",
				"previewUnavailable": true,
				"previewImageUrl":    "",
				"previewText":        "",
				"previewRouteId":     "",
			},
			"$max": bson.M{"targetVersion": targetVersion},
		},
	)
	return err
}

func (s *MongoActivityStore) ApplyReadState(
	ctx context.Context,
	ownerPersonaID string,
	activityID string,
	state string,
	at time.Time,
) error {
	if strings.TrimSpace(ownerPersonaID) == "" ||
		strings.TrimSpace(activityID) == "" ||
		at.IsZero() {
		return fmt.Errorf("ProfileInteractionReadFact target is incomplete")
	}
	update := bson.M{"seenAt": at.UTC()}
	if state == "read" {
		update["readAt"] = at.UTC()
	} else if state != "seen" {
		return fmt.Errorf("unsupported ProfileInteractionReadFact state %q", state)
	}
	result, err := s.collection.UpdateOne(
		ctx,
		bson.M{
			"ownerPersonaId": strings.TrimSpace(ownerPersonaID),
			"direction":      activitymodel.DirectionReceived,
			"activityId":     strings.TrimSpace(activityID),
			"active":         true,
		},
		bson.M{"$min": update},
	)
	if err != nil {
		return err
	}
	if result.MatchedCount != 1 {
		return fmt.Errorf("ProfileInteractionReadFact target no longer exists")
	}
	return nil
}

func (s *MongoActivityStore) List(
	ctx context.Context,
	request activityports.PageRequest,
) (activityports.Page, error) {
	limit := request.Limit
	if limit <= 0 {
		limit = 20
	}
	filter := bson.M{
		"ownerPersonaId": strings.TrimSpace(request.OwnerPersonaID),
		"direction":      strings.TrimSpace(request.Direction),
		"activityType":   strings.TrimSpace(request.ActivityType),
		"active":         true,
	}
	if !request.Cursor.OccurredAt.IsZero() {
		filter["$or"] = bson.A{
			bson.M{"occurredAt": bson.M{"$lt": request.Cursor.OccurredAt.UTC()}},
			bson.M{
				"occurredAt": request.Cursor.OccurredAt.UTC(),
				"activityId": bson.M{"$lt": request.Cursor.ActivityID},
			},
		}
	}
	cursor, err := s.collection.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "occurredAt", Value: -1}, {Key: "activityId", Value: -1}}).
			SetLimit(int64(limit+1)),
	)
	if err != nil {
		return activityports.Page{}, err
	}
	defer cursor.Close(ctx)
	documents := make([]activityDocument, 0, limit+1)
	if err := cursor.All(ctx, &documents); err != nil {
		return activityports.Page{}, err
	}
	hasMore := len(documents) > limit
	if hasMore {
		documents = documents[:limit]
	}
	items := make([]activitymodel.Activity, 0, len(documents))
	for _, document := range documents {
		items = append(items, document.Activity)
	}
	return activityports.Page{Items: items, HasMore: hasMore}, nil
}

func (s *MongoActivityStore) CanAppendReadFact(
	ctx context.Context,
	ownerPersonaID string,
	activityID string,
) (bool, error) {
	count, err := s.collection.CountDocuments(ctx, bson.M{
		"ownerPersonaId": strings.TrimSpace(ownerPersonaID),
		"direction":      activitymodel.DirectionReceived,
		"activityId":     strings.TrimSpace(activityID),
		"active":         true,
	}, options.Count().SetLimit(1))
	return count == 1, err
}

func activityDocumentID(ownerPersonaID, direction, activityID string) string {
	sum := sha256.Sum256([]byte(
		strings.TrimSpace(ownerPersonaID) + "\x00" +
			strings.TrimSpace(direction) + "\x00" +
			strings.TrimSpace(activityID),
	))
	return "pia_" + hex.EncodeToString(sum[:16])
}

var (
	_ activityports.ActivityReader           = (*MongoActivityStore)(nil)
	_ activityports.ActivityProjectionWriter = (*MongoActivityStore)(nil)
)
