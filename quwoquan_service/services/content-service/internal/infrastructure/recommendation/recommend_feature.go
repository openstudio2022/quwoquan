package recommendation

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtrec "quwoquan_service/runtime/recommendation"
)

// RecommendFeatureProjector maintains the rm_recommend_feature read model.
// Aligned with contracts/metadata/_projections/recommend_feature.yaml.
type RecommendFeatureProjector struct {
	coll *mongo.Collection
}

func NewRecommendFeatureProjector(db *mongo.Database) *RecommendFeatureProjector {
	return &RecommendFeatureProjector{coll: db.Collection("rm_recommend_feature")}
}

func (p *RecommendFeatureProjector) Name() string { return "RecommendFeatureProjector" }

func (p *RecommendFeatureProjector) EventTypes() []string {
	return []string{
		"PostCreated", "ContentReacted", "BehaviorBatchReported",
		"UserFollowed", "CircleMemberJoined",
	}
}

func (p *RecommendFeatureProjector) Project(ctx context.Context, event ProjectorEvent) error {
	switch event.Type {
	case "BehaviorBatchReported":
		return p.onBehaviorBatch(ctx, event)
	case "ContentReacted":
		return p.onContentReacted(ctx, event)
	default:
		return nil
	}
}

func (p *RecommendFeatureProjector) onBehaviorBatch(ctx context.Context, event ProjectorEvent) error {
	userID := strVal(event.Payload, "userId")
	if userID == "" {
		return nil
	}

	events, ok := event.Payload["events"].([]any)
	if !ok || len(events) == 0 {
		return nil
	}

	tagCounts := map[string]int{}
	authorCounts := map[string]int{}
	for _, raw := range events {
		ev, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		tags := anySlice(ev, "tags")
		for _, t := range tags {
			tagCounts[t]++
		}
		if authorID := strVal(ev, "authorId"); authorID != "" {
			authorCounts[authorID]++
		}
	}

	inc := bson.M{}
	for tag, count := range tagCounts {
		inc["userFeatures.tagInteraction."+tag] = count
	}
	for author, count := range authorCounts {
		inc["userFeatures.authorInteraction."+author] = count
	}
	inc["userFeatures.totalEvents"] = len(events)

	update := bson.M{
		"$inc": inc,
		"$set": bson.M{
			"userId":    userID,
			"updatedAt": time.Now().UTC(),
		},
	}

	opts := options.UpdateOne().SetUpsert(true)
	_, err := p.coll.UpdateOne(ctx, bson.M{"userId": userID}, update, opts)
	return err
}

func (p *RecommendFeatureProjector) onContentReacted(ctx context.Context, event ProjectorEvent) error {
	userID := strVal(event.Payload, "userId")
	if userID == "" {
		return nil
	}

	inc := bson.M{}
	if boolVal(event.Payload, "liked") {
		inc["userFeatures.totalLikes"] = 1
	}
	if boolVal(event.Payload, "favorited") {
		inc["userFeatures.totalFavorites"] = 1
	}
	if boolVal(event.Payload, "shared") {
		inc["userFeatures.totalShares"] = 1
	}

	if len(inc) == 0 {
		return nil
	}

	update := bson.M{
		"$inc": inc,
		"$set": bson.M{
			"userId":    userID,
			"updatedAt": time.Now().UTC(),
		},
	}

	opts := options.UpdateOne().SetUpsert(true)
	_, err := p.coll.UpdateOne(ctx, bson.M{"userId": userID}, update, opts)
	return err
}

// FeatureStore reads pre-computed recommendation features for scoring.
// Implements rtrec.FeatureProvider interface for direct use in the Engine.
type FeatureStore struct {
	coll *mongo.Collection
}

func NewFeatureStore(db *mongo.Database) *FeatureStore {
	return &FeatureStore{coll: db.Collection("rm_recommend_feature")}
}

// UserFeatures holds aggregated user-level features for scoring.
type UserFeatures struct {
	UserID            string            `bson:"userId"`
	TagInteraction    map[string]int    `bson:"tagInteraction"`
	AuthorInteraction map[string]int    `bson:"authorInteraction"`
	TotalEvents       int               `bson:"totalEvents"`
	TotalLikes        int               `bson:"totalLikes"`
	TotalFavorites    int               `bson:"totalFavorites"`
	TotalShares       int               `bson:"totalShares"`
}

func (s *FeatureStore) GetUserFeatures(ctx context.Context, userID string) (*UserFeatures, error) {
	var doc struct {
		UserID       string `bson:"userId"`
		UserFeatures struct {
			TagInteraction    map[string]int `bson:"tagInteraction"`
			AuthorInteraction map[string]int `bson:"authorInteraction"`
			TotalEvents       int            `bson:"totalEvents"`
			TotalLikes        int            `bson:"totalLikes"`
			TotalFavorites    int            `bson:"totalFavorites"`
			TotalShares       int            `bson:"totalShares"`
		} `bson:"userFeatures"`
	}

	err := s.coll.FindOne(ctx, bson.M{"userId": userID}).Decode(&doc)
	if err == mongo.ErrNoDocuments {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}

	return &UserFeatures{
		UserID:            doc.UserID,
		TagInteraction:    doc.UserFeatures.TagInteraction,
		AuthorInteraction: doc.UserFeatures.AuthorInteraction,
		TotalEvents:       doc.UserFeatures.TotalEvents,
		TotalLikes:        doc.UserFeatures.TotalLikes,
		TotalFavorites:    doc.UserFeatures.TotalFavorites,
		TotalShares:       doc.UserFeatures.TotalShares,
	}, nil
}

// GetFeatures implements rtrec.FeatureProvider.
// Converts the stored features into the runtime's UserFeatureVector format.
func (s *FeatureStore) GetFeatures(ctx context.Context, userID string) (*rtrec.UserFeatureVector, error) {
	raw, err := s.GetUserFeatures(ctx, userID)
	if err != nil || raw == nil {
		return nil, err
	}

	tagAffinities := make(map[string]float64, len(raw.TagInteraction))
	for tag, count := range raw.TagInteraction {
		tagAffinities[tag] = float64(count)
	}

	authorAffinities := make(map[string]float64, len(raw.AuthorInteraction))
	for author, count := range raw.AuthorInteraction {
		authorAffinities[author] = float64(count)
	}

	var engagementRate float64
	if raw.TotalEvents > 0 {
		engagementRate = float64(raw.TotalLikes+raw.TotalFavorites+raw.TotalShares) / float64(raw.TotalEvents)
	}

	return &rtrec.UserFeatureVector{
		TagAffinities:    tagAffinities,
		AuthorAffinities: authorAffinities,
		TotalLikes:       raw.TotalLikes,
		TotalFavorites:   raw.TotalFavorites,
		TotalShares:      raw.TotalShares,
		TotalEvents:      raw.TotalEvents,
		EngagementRate:   engagementRate,
		LikeLevel:        rtrec.MapCountToLevel(raw.TotalLikes),
		FavoriteLevel:    rtrec.MapCountToLevel(raw.TotalFavorites),
		ShareLevel:       rtrec.MapCountToLevel(raw.TotalShares),
		EventLevel:       rtrec.MapCountToLevel(raw.TotalEvents),
	}, nil
}
