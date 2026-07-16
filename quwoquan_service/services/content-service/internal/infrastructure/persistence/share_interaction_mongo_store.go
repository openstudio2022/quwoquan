package persistence

import (
	"context"
	"log/slog"
	"strings"
	"time"

	postdomain "quwoquan_service/services/content-service/internal/domain/post"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const shareInteractionCollection = "rm_profile_share_interactions"

type MongoShareInteractionStore struct {
	coll   *mongo.Collection
	logger *slog.Logger
}

func NewMongoShareInteractionStore(
	db *mongo.Database,
	logger *slog.Logger,
) *MongoShareInteractionStore {
	store := &MongoShareInteractionStore{
		coll:   db.Collection(shareInteractionCollection),
		logger: logger,
	}
	store.ensureIndexes()
	return store
}

func (s *MongoShareInteractionStore) ensureIndexes() {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	indexes := []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "targetSubAccountId", Value: 1},
				{Key: "occurredAt", Value: -1},
				{Key: "interactionId", Value: -1},
			},
		},
		{
			Keys: bson.D{
				{Key: "actorSubAccountId", Value: 1},
				{Key: "occurredAt", Value: -1},
				{Key: "interactionId", Value: -1},
			},
		},
		{
			Keys:    bson.D{{Key: "interactionId", Value: 1}},
			Options: options.Index().SetUnique(true),
		},
	}
	for _, index := range indexes {
		if _, err := s.coll.Indexes().CreateOne(ctx, index); err != nil {
			s.logger.Warn("profile_share_interaction: index creation failed", slog.String("error", err.Error()))
		}
	}
}

func (s *MongoShareInteractionStore) Save(
	ctx context.Context,
	item postdomain.ShareInteractionOccurrence,
) error {
	if strings.TrimSpace(item.InteractionID) == "" {
		return nil
	}
	_, err := s.coll.UpdateOne(
		ctx,
		bson.M{"interactionId": item.InteractionID},
		bson.M{"$setOnInsert": item},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

func (s *MongoShareInteractionStore) List(
	ctx context.Context,
	query postdomain.ShareInteractionQuery,
) ([]postdomain.ShareInteractionOccurrence, bool, error) {
	subjectField := "targetSubAccountId"
	if query.Direction == "sent" {
		subjectField = "actorSubAccountId"
	}
	filter := bson.M{subjectField: strings.TrimSpace(query.SubAccountID)}
	if !query.CursorTime.IsZero() {
		filter["$or"] = bson.A{
			bson.M{"occurredAt": bson.M{"$lt": query.CursorTime.UTC()}},
			bson.M{
				"occurredAt":    query.CursorTime.UTC(),
				"interactionId": bson.M{"$lt": query.CursorID},
			},
		}
	}
	limit := query.Limit
	if limit <= 0 {
		limit = 20
	}
	cursor, err := s.coll.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "occurredAt", Value: -1}, {Key: "interactionId", Value: -1}}).
			SetLimit(int64(limit+1)),
	)
	if err != nil {
		return nil, false, err
	}
	defer cursor.Close(ctx)
	var items []postdomain.ShareInteractionOccurrence
	if err := cursor.All(ctx, &items); err != nil {
		return nil, false, err
	}
	hasMore := len(items) > limit
	if hasMore {
		items = items[:limit]
	}
	return items, hasMore, nil
}

func (s *MongoShareInteractionStore) MarkState(
	ctx context.Context,
	subAccountID string,
	interactionID string,
	state string,
	at time.Time,
) error {
	minimum := bson.M{"seenAt": at.UTC()}
	if state == "read" {
		minimum["readAt"] = at.UTC()
	}
	_, err := s.coll.UpdateOne(
		ctx,
		bson.M{
			"interactionId":      strings.TrimSpace(interactionID),
			"targetSubAccountId": strings.TrimSpace(subAccountID),
		},
		bson.M{"$min": minimum},
	)
	return err
}
