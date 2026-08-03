package persistence

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	commentmodel "quwoquan_service/services/content-service/internal/content/comment/domain/model"
)

const (
	commentViewerRelationshipCollection = "comment_viewer_relationship_projection"
	commentViewerRelationshipInbox      = "comment_viewer_relationship_inbox"
)

// CommentViewerRelationshipMongoProjection is Comment's sole persisted view
// of User PersonaRelationship facts. It owns both projection writes and the
// bounded reads required by Comment pages; no Content object reads User or
// Recommendation storage directly.
type CommentViewerRelationshipMongoProjection struct {
	relationships *mongo.Collection
	inbox         *mongo.Collection
}

func NewCommentViewerRelationshipMongoProjection(
	db *mongo.Database,
) *CommentViewerRelationshipMongoProjection {
	return &CommentViewerRelationshipMongoProjection{
		relationships: db.Collection(commentViewerRelationshipCollection),
		inbox:         db.Collection(commentViewerRelationshipInbox),
	}
}

func (projection *CommentViewerRelationshipMongoProjection) EnsureIndexes(
	ctx context.Context,
) error {
	if projection == nil || projection.relationships == nil || projection.inbox == nil {
		return fmt.Errorf("comment viewer relationship projection is not configured")
	}
	if _, err := projection.relationships.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "sourcePersonaId", Value: 1},
			{Key: "targetPersonaId", Value: 1},
		},
		Options: options.Index().SetUnique(true).
			SetName("uq_comment_viewer_relationship_direction"),
	}); err != nil {
		return fmt.Errorf("create comment viewer relationship direction index: %w", err)
	}
	for _, model := range []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "sourcePersonaId", Value: 1},
				{Key: "blocked", Value: 1},
				{Key: "targetPersonaId", Value: 1},
			},
			Options: options.Index().SetName("idx_comment_viewer_block_source"),
		},
		{
			Keys: bson.D{
				{Key: "targetPersonaId", Value: 1},
				{Key: "blocked", Value: 1},
				{Key: "sourcePersonaId", Value: 1},
			},
			Options: options.Index().SetName("idx_comment_viewer_block_target"),
		},
	} {
		if _, err := projection.relationships.Indexes().CreateOne(ctx, model); err != nil {
			return fmt.Errorf("create comment viewer block index: %w", err)
		}
	}
	if _, err := projection.inbox.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "eventId", Value: 1}},
		Options: options.Index().SetUnique(true).
			SetName("uq_comment_viewer_relationship_event"),
	}); err != nil {
		return fmt.Errorf("create comment viewer relationship inbox index: %w", err)
	}
	return nil
}

func (projection *CommentViewerRelationshipMongoProjection) ApplyFollowState(
	ctx context.Context,
	event commentapp.ViewerRelationshipEvent,
) error {
	filter := relationshipVersionFilter(
		event.SourcePersonaID,
		event.TargetPersonaID,
		"version",
		event.Version,
	)
	_, err := projection.relationships.UpdateOne(ctx, filter, bson.M{
		"$set": bson.M{
			"sourcePersonaId": event.SourcePersonaID,
			"targetPersonaId": event.TargetPersonaID,
			"following":       event.Following,
			"pairId":          event.PairID,
			"version":         event.Version,
			"eventId":         event.EventID,
			"updatedAt":       event.OccurredAt.UTC(),
		},
	}, options.UpdateOne().SetUpsert(true))
	if mongo.IsDuplicateKeyError(err) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("project comment viewer follow state: %w", err)
	}
	return nil
}

func (projection *CommentViewerRelationshipMongoProjection) ApplyBlockState(
	ctx context.Context,
	event commentapp.ViewerRelationshipEvent,
	blocked bool,
) error {
	filter := relationshipVersionFilter(
		event.SourcePersonaID,
		event.TargetPersonaID,
		"blockVersion",
		event.Version,
	)
	_, err := projection.relationships.UpdateOne(ctx, filter, bson.M{
		"$set": bson.M{
			"sourcePersonaId": event.SourcePersonaID,
			"targetPersonaId": event.TargetPersonaID,
			"blocked":         blocked,
			"pairId":          event.PairID,
			"blockVersion":    event.Version,
			"eventId":         event.EventID,
			"updatedAt":       event.OccurredAt.UTC(),
		},
	}, options.UpdateOne().SetUpsert(true))
	if mongo.IsDuplicateKeyError(err) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("project comment viewer block state: %w", err)
	}
	return nil
}

func relationshipVersionFilter(
	sourcePersonaID string,
	targetPersonaID string,
	versionField string,
	version int64,
) bson.M {
	return bson.M{
		"sourcePersonaId": sourcePersonaID,
		"targetPersonaId": targetPersonaID,
		"$or": []bson.M{
			{versionField: bson.M{"$exists": false}},
			{versionField: bson.M{"$lt": version}},
		},
	}
}

func (projection *CommentViewerRelationshipMongoProjection) RecordAppliedEvent(
	ctx context.Context,
	event commentapp.ViewerRelationshipEvent,
) (bool, error) {
	_, err := projection.inbox.InsertOne(ctx, bson.M{
		"eventId":   event.EventID,
		"eventName": string(event.EventName),
		"pairId":    event.PairID,
		"version":   event.Version,
		"appliedAt": time.Now().UTC(),
	})
	if mongo.IsDuplicateKeyError(err) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("record comment viewer relationship inbox: %w", err)
	}
	return true, nil
}

func (projection *CommentViewerRelationshipMongoProjection) ReadViewerRelations(
	ctx context.Context,
	viewerPersonaID string,
	authorPersonaIDs []string,
) (map[string]commentmodel.ViewerRelation, error) {
	relations := map[string]commentmodel.ViewerRelation{}
	viewerPersonaID = strings.TrimSpace(viewerPersonaID)
	authors := uniqueNonEmptyStrings(authorPersonaIDs)
	if viewerPersonaID == "" || len(authors) == 0 {
		return relations, nil
	}
	cursor, err := projection.relationships.Find(ctx, bson.M{
		"following": true,
		"$or": bson.A{
			bson.M{
				"sourcePersonaId": viewerPersonaID,
				"targetPersonaId": bson.M{"$in": authors},
			},
			bson.M{
				"sourcePersonaId": bson.M{"$in": authors},
				"targetPersonaId": viewerPersonaID,
			},
		},
	}, options.Find().SetProjection(bson.M{
		"sourcePersonaId": 1,
		"targetPersonaId": 1,
	}))
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	viewerFollows := map[string]bool{}
	followsViewer := map[string]bool{}
	for cursor.Next(ctx) {
		var row struct {
			SourcePersonaID string `bson:"sourcePersonaId"`
			TargetPersonaID string `bson:"targetPersonaId"`
		}
		if err := cursor.Decode(&row); err != nil {
			return nil, err
		}
		if row.SourcePersonaID == viewerPersonaID {
			viewerFollows[row.TargetPersonaID] = true
		} else if row.TargetPersonaID == viewerPersonaID {
			followsViewer[row.SourcePersonaID] = true
		}
	}
	if err := cursor.Err(); err != nil {
		return nil, err
	}
	for _, author := range authors {
		switch {
		case viewerFollows[author] && followsViewer[author]:
			relations[author] = commentmodel.ViewerRelationFriend
		case viewerFollows[author]:
			relations[author] = commentmodel.ViewerRelationFollowing
		}
	}
	return relations, nil
}

func (projection *CommentViewerRelationshipMongoProjection) ListBlockedPersonaIDs(
	ctx context.Context,
	viewerPersonaID string,
) ([]string, error) {
	viewerPersonaID = strings.TrimSpace(viewerPersonaID)
	if viewerPersonaID == "" {
		return []string{}, nil
	}
	cursor, err := projection.relationships.Find(ctx, bson.M{
		"blocked": true,
		"$or": []bson.M{
			{
				"sourcePersonaId": viewerPersonaID,
				"targetPersonaId": bson.M{"$ne": viewerPersonaID},
			},
			{
				"sourcePersonaId": bson.M{"$ne": viewerPersonaID},
				"targetPersonaId": viewerPersonaID,
			},
		},
	})
	if err != nil {
		return nil, fmt.Errorf("list Comment viewer block markers: %w", err)
	}
	defer cursor.Close(ctx)
	blockedSet := map[string]struct{}{}
	for cursor.Next(ctx) {
		var row struct {
			SourcePersonaID string `bson:"sourcePersonaId"`
			TargetPersonaID string `bson:"targetPersonaId"`
		}
		if err := cursor.Decode(&row); err != nil {
			return nil, fmt.Errorf("decode Comment viewer block marker: %w", err)
		}
		other := strings.TrimSpace(row.SourcePersonaID)
		if other == viewerPersonaID {
			other = strings.TrimSpace(row.TargetPersonaID)
		}
		if other != "" && other != viewerPersonaID {
			blockedSet[other] = struct{}{}
		}
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate Comment viewer block markers: %w", err)
	}
	blocked := make([]string, 0, len(blockedSet))
	for personaID := range blockedSet {
		blocked = append(blocked, personaID)
	}
	sort.Strings(blocked)
	return blocked, nil
}
