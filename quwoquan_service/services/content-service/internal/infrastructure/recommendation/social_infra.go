package recommendation

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtrec "quwoquan_service/runtime/recommendation"
)

// MongoEntityTagIndex implements rtrec.EntityTagIndex backed by rm_entity_tags collection.
// Document schema: { entityId: string, tags: []string }
type MongoEntityTagIndex struct {
	coll *mongo.Collection
}

func NewMongoEntityTagIndex(db *mongo.Database) *MongoEntityTagIndex {
	return &MongoEntityTagIndex{coll: db.Collection("rm_entity_tags")}
}

func (m *MongoEntityTagIndex) GetEntityTags(ctx context.Context, entityID string) ([]string, error) {
	var doc struct {
		Tags []string `bson:"tags"`
	}
	err := m.coll.FindOne(ctx, bson.M{"entityId": entityID}).Decode(&doc)
	if err == mongo.ErrNoDocuments {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return doc.Tags, nil
}

// UpsertEntityTags sets the tag list for an entity (used by bulk import).
func (m *MongoEntityTagIndex) UpsertEntityTags(ctx context.Context, entityID string, tags []string) error {
	opts := options.UpdateOne().SetUpsert(true)
	_, err := m.coll.UpdateOne(ctx, bson.M{"entityId": entityID}, bson.M{
		"$set": bson.M{
			"entityId":  entityID,
			"tags":      tags,
			"updatedAt": time.Now().UTC(),
		},
	}, opts)
	return err
}

// MongoSocialGraphProvider implements rtrec.SocialGraphProvider backed by MongoDB.
// Collections:
//   - circle_members: { circleId, userId }
//   - circle_tag_aggregates: { circleId, tags: map[string]float64 }
//   - follow_edges: { followerId, followeeId }
//   - rm_recommend_feature: user feature store (for friend interest intersection)
type MongoSocialGraphProvider struct {
	db *mongo.Database
}

func NewMongoSocialGraphProvider(db *mongo.Database) *MongoSocialGraphProvider {
	return &MongoSocialGraphProvider{db: db}
}

func (m *MongoSocialGraphProvider) GetUserCircleTags(ctx context.Context, userID string) (map[string]float64, error) {
	memberColl := m.db.Collection("circle_members")
	cursor, err := memberColl.Find(ctx, bson.M{"userId": userID})
	if err != nil {
		return nil, nil
	}
	defer cursor.Close(ctx)

	var circleIDs []string
	for cursor.Next(ctx) {
		var doc struct {
			CircleID string `bson:"circleId"`
		}
		if err := cursor.Decode(&doc); err == nil && doc.CircleID != "" {
			circleIDs = append(circleIDs, doc.CircleID)
		}
	}
	if len(circleIDs) == 0 {
		return nil, nil
	}

	tagColl := m.db.Collection("circle_tag_aggregates")
	tagCursor, err := tagColl.Find(ctx, bson.M{"circleId": bson.M{"$in": circleIDs}})
	if err != nil {
		return nil, nil
	}
	defer tagCursor.Close(ctx)

	result := make(map[string]float64)
	for tagCursor.Next(ctx) {
		var doc struct {
			Tags map[string]float64 `bson:"tags"`
		}
		if err := tagCursor.Decode(&doc); err == nil {
			for k, v := range doc.Tags {
				result[k] += v
			}
		}
	}
	return result, nil
}

func (m *MongoSocialGraphProvider) GetUserCircleIDs(ctx context.Context, userID string) ([]string, error) {
	memberColl := m.db.Collection("circle_members")
	cursor, err := memberColl.Find(ctx, bson.M{"userId": userID})
	if err != nil {
		return nil, nil
	}
	defer cursor.Close(ctx)

	var circleIDs []string
	for cursor.Next(ctx) {
		var doc struct {
			CircleID string `bson:"circleId"`
		}
		if err := cursor.Decode(&doc); err == nil && doc.CircleID != "" {
			circleIDs = append(circleIDs, doc.CircleID)
		}
	}
	return circleIDs, nil
}

func (m *MongoSocialGraphProvider) GetFriendInterestIntersection(ctx context.Context, userID string) (map[string]float64, error) {
	followColl := m.db.Collection("follow_edges")
	cursor, err := followColl.Find(ctx, bson.M{"followerId": userID},
		options.Find().SetLimit(50))
	if err != nil {
		return nil, nil
	}
	defer cursor.Close(ctx)

	var followeeIDs []string
	for cursor.Next(ctx) {
		var doc struct {
			FolloweeID string `bson:"followeeId"`
		}
		if err := cursor.Decode(&doc); err == nil && doc.FolloweeID != "" {
			followeeIDs = append(followeeIDs, doc.FolloweeID)
		}
	}
	if len(followeeIDs) == 0 {
		return nil, nil
	}

	featureColl := m.db.Collection("rm_recommend_feature")
	featureCursor, err := featureColl.Find(ctx, bson.M{"userId": bson.M{"$in": followeeIDs}})
	if err != nil {
		return nil, nil
	}
	defer featureCursor.Close(ctx)

	tagFreq := make(map[string]int)
	for featureCursor.Next(ctx) {
		var doc struct {
			UserFeatures struct {
				TagInteraction map[string]int `bson:"tagInteraction"`
			} `bson:"userFeatures"`
		}
		if err := featureCursor.Decode(&doc); err == nil {
			for tag := range doc.UserFeatures.TagInteraction {
				tagFreq[tag]++
			}
		}
	}

	result := make(map[string]float64, len(tagFreq))
	for tag, count := range tagFreq {
		if count >= 2 {
			result[tag] = float64(count) / float64(len(followeeIDs))
		}
	}
	return result, nil
}

func (m *MongoSocialGraphProvider) GetFriendInteractedContent(ctx context.Context, userID string, limit int) ([]string, error) {
	followColl := m.db.Collection("follow_edges")
	cursor, err := followColl.Find(ctx, bson.M{"followerId": userID},
		options.Find().SetLimit(30))
	if err != nil {
		return nil, nil
	}
	defer cursor.Close(ctx)

	var followeeIDs []string
	for cursor.Next(ctx) {
		var doc struct {
			FolloweeID string `bson:"followeeId"`
		}
		if err := cursor.Decode(&doc); err == nil && doc.FolloweeID != "" {
			followeeIDs = append(followeeIDs, doc.FolloweeID)
		}
	}
	if len(followeeIDs) == 0 {
		return nil, nil
	}

	eventColl := m.db.Collection("rec_learning_events")
	cutoff := time.Now().Add(-7 * 24 * time.Hour)
	eventCursor, err := eventColl.Find(ctx, bson.M{
		"userId":    bson.M{"$in": followeeIDs},
		"eventType": "rec_engagement",
		"labels.action": bson.M{"$in": []string{"like", "favorite", "share"}},
		"createdAt":     bson.M{"$gte": cutoff},
	}, options.Find().SetLimit(int64(limit)).SetSort(bson.M{"createdAt": -1}))
	if err != nil {
		return nil, nil
	}
	defer eventCursor.Close(ctx)

	seen := make(map[string]bool)
	var contentIDs []string
	for eventCursor.Next(ctx) {
		var doc struct {
			TargetID string `bson:"targetId"`
		}
		if err := eventCursor.Decode(&doc); err == nil && doc.TargetID != "" && !seen[doc.TargetID] {
			seen[doc.TargetID] = true
			contentIDs = append(contentIDs, doc.TargetID)
		}
	}
	return contentIDs, nil
}

// MongoSocialCandidateDB implements rtrec.SocialCandidateDB backed by MongoDB.
type MongoSocialCandidateDB struct {
	coll *mongo.Collection
}

func NewMongoSocialCandidateDB(db *mongo.Database) *MongoSocialCandidateDB {
	return &MongoSocialCandidateDB{coll: db.Collection("rm_discovery_feed")}
}

func (m *MongoSocialCandidateDB) GetCandidatesByIDs(ctx context.Context, ids []string) ([]rtrec.ContentCandidate, error) {
	if len(ids) == 0 {
		return nil, nil
	}
	cursor, err := m.coll.Find(ctx, bson.M{"postId": bson.M{"$in": ids}})
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	return decodeCandidatesFromCursor(ctx, cursor)
}

func (m *MongoSocialCandidateDB) GetCircleHotContent(ctx context.Context, circleIDs []string, limit int, maxAge time.Duration) ([]rtrec.ContentCandidate, error) {
	if len(circleIDs) == 0 {
		return nil, nil
	}
	cutoff := time.Now().Add(-maxAge)
	cursor, err := m.coll.Find(ctx, bson.M{
		"circleIds":   bson.M{"$in": circleIDs},
		"publishedAt": bson.M{"$gte": cutoff},
	}, options.Find().SetLimit(int64(limit)).SetSort(bson.M{"viewCount": -1}))
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	return decodeCandidatesFromCursor(ctx, cursor)
}

func decodeCandidatesFromCursor(ctx context.Context, cursor *mongo.Cursor) ([]rtrec.ContentCandidate, error) {
	var results []rtrec.ContentCandidate
	for cursor.Next(ctx) {
		var doc struct {
			PostID       string    `bson:"postId"`
			ContentType  string    `bson:"contentType"`
			AuthorID     string    `bson:"authorId"`
			Title        string    `bson:"title"`
			Tags         []string  `bson:"tags"`
			EntityRefs   []string  `bson:"entityRefs"`
			PublishedAt  time.Time `bson:"publishedAt"`
			ViewCount    int64     `bson:"viewCount"`
			LikeCount    int64     `bson:"likeCount"`
			CommentCount int64     `bson:"commentCount"`
			ShareCount   int64     `bson:"shareCount"`
		}
		if err := cursor.Decode(&doc); err == nil {
			results = append(results, rtrec.ContentCandidate{
				ContentID:    doc.PostID,
				ContentType:  doc.ContentType,
				AuthorID:     doc.AuthorID,
				Title:        doc.Title,
				Tags:         doc.Tags,
				EntityRefs:   doc.EntityRefs,
				PublishedAt:  doc.PublishedAt,
				ViewCount:    doc.ViewCount,
				LikeCount:    doc.LikeCount,
				CommentCount: doc.CommentCount,
				ShareCount:   doc.ShareCount,
			})
		}
	}
	return results, nil
}
