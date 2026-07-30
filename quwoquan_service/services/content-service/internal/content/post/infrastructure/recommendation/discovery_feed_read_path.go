package recommendation

import (
	"context"
	"fmt"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

// DiscoveryFeedCandidateProjection is the storage-side projection shared by
// every Mongo recall source. Keeping it next to the index owner makes the hot
// read contract explicit: recommendation must not fetch the full, media-heavy
// rm_discovery_feed document and discard most of it after BSON decoding.
func DiscoveryFeedCandidateProjection() bson.D {
	return bson.D{
		{Key: "_id", Value: 0},
		{Key: "postId", Value: 1},
		{Key: "contentType", Value: 1},
		{Key: "authorId", Value: 1},
		{Key: "title", Value: 1},
		{Key: "tagRefs", Value: 1},
		{Key: "entityRefs", Value: 1},
		{Key: "likeCount", Value: 1},
		{Key: "commentCount", Value: 1},
		{Key: "shareCount", Value: 1},
		{Key: "viewCount", Value: 1},
		{Key: "publishedAt", Value: 1},
		{Key: "recScore", Value: 1},
		{Key: "qualityScore", Value: 1},
		{Key: "contentVertical", Value: 1},
		{Key: "supplySource", Value: 1},
		{Key: "sourceOwner", Value: 1},
		{Key: "releaseId", Value: 1},
		{Key: "manifestDigest", Value: 1},
		{Key: "lifecycleStatus", Value: 1},
		{Key: "intersectionFactStrength", Value: 1},
		{Key: "intersectionFreshness", Value: 1},
		{Key: "affinityIntersectionScore", Value: 1},
		{Key: "intersectionSourceRefTop", Value: 1},
		{Key: "intersectionConfidenceLabel", Value: 1},
		{Key: "intersectionClass", Value: 1},
	}
}

// DiscoveryFeedIndexModels is the executable form of the canonical
// discovery_feed projection indexes. All constructors are returned in a stable
// order so startup, importer and tests converge on the same names and keys.
func DiscoveryFeedIndexModels() []mongo.IndexModel {
	return []mongo.IndexModel{
		{
			Keys: bson.D{{Key: "postId", Value: 1}},
			Options: options.Index().
				SetName("uq_df_post_id").
				SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "status", Value: 1},
				{Key: "visibility", Value: 1},
				{Key: "recScore", Value: -1},
				{Key: "publishedAt", Value: -1},
				{Key: "postId", Value: -1},
			},
			Options: options.Index().SetName("idx_df_recommend_recency"),
		},
		{
			Keys: bson.D{
				{Key: "status", Value: 1},
				{Key: "visibility", Value: 1},
				{Key: "contentVertical", Value: 1},
				{Key: "recScore", Value: -1},
				{Key: "publishedAt", Value: -1},
				{Key: "postId", Value: -1},
			},
			Options: options.Index().SetName("idx_df_recommend_vertical_recency"),
		},
		{
			Keys: bson.D{
				{Key: "status", Value: 1},
				{Key: "visibility", Value: 1},
				{Key: "sourceOwner", Value: 1},
				{Key: "releaseId", Value: 1},
				{Key: "manifestDigest", Value: 1},
				{Key: "lifecycleStatus", Value: 1},
				{Key: "recScore", Value: -1},
				{Key: "publishedAt", Value: -1},
				{Key: "postId", Value: -1},
			},
			Options: options.Index().SetName("idx_df_active_release_recency"),
		},
		{
			Keys: bson.D{
				{Key: "status", Value: 1},
				{Key: "visibility", Value: 1},
				{Key: "sourceOwner", Value: 1},
				{Key: "releaseId", Value: 1},
				{Key: "manifestDigest", Value: 1},
				{Key: "lifecycleStatus", Value: 1},
				{Key: "contentVertical", Value: 1},
				{Key: "recScore", Value: -1},
				{Key: "publishedAt", Value: -1},
				{Key: "postId", Value: -1},
			},
			Options: options.Index().SetName("idx_df_active_release_vertical_recency"),
		},
		{
			Keys: bson.D{
				{Key: "status", Value: 1},
				{Key: "visibility", Value: 1},
				{Key: "contentType", Value: 1},
				{Key: "publishedAt", Value: -1},
				{Key: "postId", Value: -1},
			},
			Options: options.Index().SetName("idx_df_type_recency"),
		},
		{
			Keys: bson.D{
				{Key: "status", Value: 1},
				{Key: "visibility", Value: 1},
				{Key: "authorId", Value: 1},
				{Key: "publishedAt", Value: -1},
				{Key: "postId", Value: -1},
			},
			Options: options.Index().SetName("idx_df_author_recency"),
		},
	}
}

// EnsureIndexes makes the projection owner responsible for its read-path
// indexes. Callers must fail startup/import when this cannot be established;
// a warning would allow a release to activate with an unbounded COLLSCAN.
func (p *DiscoveryFeedProjector) EnsureIndexes(ctx context.Context) error {
	if p == nil || p.coll == nil {
		return fmt.Errorf("DiscoveryFeed projector is not configured")
	}
	if _, err := p.coll.Indexes().CreateMany(ctx, DiscoveryFeedIndexModels()); err != nil {
		return fmt.Errorf("create DiscoveryFeed indexes: %w", err)
	}
	return nil
}
