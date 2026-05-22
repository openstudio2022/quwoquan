package recommendation

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/content-service/internal/application"
)

// MongoBulkImportStore implements application.BulkImportStore
// using the rm_discovery_feed and rm_entity_tags MongoDB collections.
type MongoBulkImportStore struct {
	feedColl   *mongo.Collection
	entityColl *mongo.Collection
}

func NewMongoBulkImportStore(db *mongo.Database) *MongoBulkImportStore {
	return &MongoBulkImportStore{
		feedColl:   db.Collection("rm_discovery_feed"),
		entityColl: db.Collection("rm_entity_tags"),
	}
}

func (s *MongoBulkImportStore) UpsertDiscoveryFeedItem(ctx context.Context, item application.BulkImportItem) error {
	publishedAt, _ := time.Parse(time.RFC3339, item.PublishedAt)
	if publishedAt.IsZero() {
		publishedAt = time.Now().UTC()
	}
	opts := options.UpdateOne().SetUpsert(true)
	_, err := s.feedColl.UpdateOne(ctx, bson.M{"postId": item.PostID}, bson.M{
		"$set": bson.M{
			"postId":      item.PostID,
			"title":       item.Title,
			"contentType": item.ContentType,
			"authorId":    item.AuthorID,
			"tags":        item.Tags,
			"entityRefs":  item.EntityRefs,
			"publishedAt": publishedAt,
			"coverUrl":    item.CoverURL,
			"bodyLength":  item.BodyLength,
			"updatedAt":   time.Now().UTC(),
		},
		"$setOnInsert": bson.M{
			"viewCount":    int64(0),
			"likeCount":    int64(0),
			"commentCount": int64(0),
			"shareCount":   int64(0),
		},
	}, opts)
	return err
}

func (s *MongoBulkImportStore) UpsertEntityTags(ctx context.Context, entityID string, tags []string) error {
	opts := options.UpdateOne().SetUpsert(true)
	_, err := s.entityColl.UpdateOne(ctx, bson.M{"entityId": entityID}, bson.M{
		"$set": bson.M{
			"entityId":  entityID,
			"tags":      tags,
			"updatedAt": time.Now().UTC(),
		},
	}, opts)
	return err
}
