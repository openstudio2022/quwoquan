package persistence

// This package is the ContentReaction object's Mongo adapter.

import (
	"context"
	"fmt"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
)

type contentReactionProfileActivityDocument struct {
	ID        string        `bson:"_id"`
	TargetID  string        `bson:"targetId"`
	ActorID   string        `bson:"actorId"`
	UpdatedAt bson.DateTime `bson:"updatedAt"`
}

type activePostReactionIdentityDocument struct {
	TargetID       string `bson:"targetId"`
	ActorDimension string `bson:"actorDimension"`
	ActorID        string `bson:"actorId"`
}

func (s *MongoContentReactionStore) ListActiveReactionsForPost(
	ctx context.Context,
	postID string,
	limit int,
) ([]reactiondomain.Identity, error) {
	postID = strings.TrimSpace(postID)
	if postID == "" {
		return nil, fmt.Errorf("Post id is required")
	}
	if limit <= 0 || limit > 1000 {
		limit = 500
	}
	cursor, err := s.aggregates.Find(
		ctx,
		bson.M{
			"targetKind": string(reactiondomain.TargetKindPost),
			"targetId":   postID,
			"reaction":   string(reactiondomain.ValueLike),
		},
		options.Find().
			SetProjection(bson.M{
				"targetId":       1,
				"actorDimension": 1,
				"actorId":        1,
			}).
			SetSort(bson.D{{Key: "_id", Value: 1}}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var rows []activePostReactionIdentityDocument
	if err := cursor.All(ctx, &rows); err != nil {
		return nil, err
	}
	identities := make([]reactiondomain.Identity, 0, len(rows))
	for _, row := range rows {
		actor, err := reactiondomain.NewActor(
			reactiondomain.ActorDimension(row.ActorDimension),
			row.ActorID,
		)
		if err != nil {
			return nil, err
		}
		identity, err := reactiondomain.NewPostIdentity(row.TargetID, actor)
		if err != nil {
			return nil, err
		}
		identities = append(identities, identity)
	}
	return identities, nil
}

// ListActiveProfileReactions 只返回 persona 维度 active reaction，device actor
// 永不进入公开主页活动。actorID 非空时由索引收敛为 sent 候选。
func (s *MongoContentReactionStore) ListActiveProfileReactions(
	ctx context.Context,
	actorID string,
	limit int,
) ([]reactionports.ProfileActivitySlice, error) {
	if limit <= 0 {
		limit = 100
	}
	if limit > 1000 {
		limit = 1000
	}
	filter := bson.M{
		"targetKind":     string(reactiondomain.TargetKindPost),
		"reaction":       string(reactiondomain.ValueLike),
		"actorDimension": string(reactiondomain.ActorDimensionPersona),
	}
	if normalizedActorID := strings.TrimSpace(actorID); normalizedActorID != "" {
		filter["actorId"] = normalizedActorID
	}
	cursor, err := s.aggregates.Find(
		ctx,
		filter,
		options.Find().
			SetProjection(bson.M{
				"_id":       1,
				"targetId":  1,
				"actorId":   1,
				"updatedAt": 1,
			}).
			SetSort(bson.D{{Key: "updatedAt", Value: -1}, {Key: "_id", Value: -1}}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	rows := make([]contentReactionProfileActivityDocument, 0, limit)
	if err := cursor.All(ctx, &rows); err != nil {
		return nil, err
	}
	slices := make([]reactionports.ProfileActivitySlice, 0, len(rows))
	for _, row := range rows {
		slices = append(slices, reactionports.ProfileActivitySlice{
			ReactionID: row.ID,
			PostID:     row.TargetID,
			ActorID:    row.ActorID,
			OccurredAt: row.UpdatedAt.Time(),
		})
	}
	return slices, nil
}

var _ reactionports.ProfileActivityReader = (*MongoContentReactionStore)(nil)
