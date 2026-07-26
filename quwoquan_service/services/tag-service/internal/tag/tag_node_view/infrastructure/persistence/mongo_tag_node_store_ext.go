package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	generated "quwoquan_service/services/tag-service/generated/tag/tag_node_view/persistence/tag/persistence"
	model "quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/model"
)

// MongoTagNodeStore 是 TagNode 的只读 Mongo 存储（embed codegen base）。
type MongoTagNodeStore struct {
	*generated.MongoTagNodeViewStoreBase
	coll *mongo.Collection
}

// NewMongoTagNodeStore 构造 TagNode 存储。
func NewMongoTagNodeStore(coll *mongo.Collection) *MongoTagNodeStore {
	return &MongoTagNodeStore{
		MongoTagNodeViewStoreBase: generated.NewMongoTagNodeViewStoreBase(coll),
		coll:                      coll,
	}
}

// EnsureIndexes creates the release-scoped snapshot indexes declared in storage.yaml.
// The generated base remains embedded for Create and generic helpers, but its legacy
// global tagRef index must never be recreated before codegen catches up.
func (s *MongoTagNodeStore) EnsureIndexes(ctx context.Context) error {
	_, err := s.coll.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "releaseId", Value: 1}, {Key: "tagRef", Value: 1}},
			Options: options.Index().SetName("uq_tag_nodes_release_tag_ref").SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "releaseId", Value: 1},
				{Key: "lifecycleStatus", Value: 1},
				{Key: "group", Value: 1},
				{Key: "depth", Value: 1},
				{Key: "tagRef", Value: 1},
			},
			Options: options.Index().SetName("idx_tag_nodes_release_lifecycle_group_depth_tagref"),
		},
		{
			Keys: bson.D{
				{Key: "releaseId", Value: 1},
				{Key: "parentTagRef", Value: 1},
				{Key: "lifecycleStatus", Value: 1},
				{Key: "tagRef", Value: 1},
			},
			Options: options.Index().SetName("idx_tag_nodes_release_parent_lifecycle_tagref"),
		},
		{
			Keys: bson.D{
				{Key: "releaseId", Value: 1},
				{Key: "lifecycleStatus", Value: 1},
				{Key: "nodeKind", Value: 1},
				{Key: "group", Value: 1},
				{Key: "tagRef", Value: 1},
			},
			Options: options.Index().
				SetName("idx_tag_nodes_release_kind_group_tagref"),
		},
	})
	return err
}

// FindByReleaseAndTagRef reads a tag definition from one immutable taxonomy snapshot.
func (s *MongoTagNodeStore) FindByReleaseAndTagRef(ctx context.Context, releaseID, tagRef string) (*model.TagNode, error) {
	var node model.TagNode
	if err := s.coll.FindOne(ctx, bson.M{
		"releaseId": releaseID,
		"tagRef":    tagRef,
	}).Decode(&node); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, nil
		}
		return nil, err
	}
	return &node, nil
}

// ListChildrenInRelease reads active direct children within one snapshot.
func (s *MongoTagNodeStore) ListChildrenInRelease(ctx context.Context, releaseID, parentTagRef string, limit int64) ([]model.TagNode, error) {
	filter := bson.M{
		"releaseId":       releaseID,
		"parentTagRef":    parentTagRef,
		"lifecycleStatus": "active",
	}
	findOptions := options.Find().SetSort(bson.D{{Key: "tagRef", Value: 1}})
	if limit > 0 {
		findOptions.SetLimit(limit)
	}
	cur, err := s.coll.Find(ctx, filter, findOptions)
	if err != nil {
		return nil, err
	}
	defer cur.Close(ctx)
	out := make([]model.TagNode, 0)
	if err := cur.All(ctx, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// CountActiveChildrenInRelease returns the active direct child count for one snapshot.
func (s *MongoTagNodeStore) CountActiveChildrenInRelease(ctx context.Context, releaseID, parentTagRef string) (int64, error) {
	return s.coll.CountDocuments(ctx, bson.M{
		"releaseId":       releaseID,
		"parentTagRef":    parentTagRef,
		"lifecycleStatus": "active",
	}, options.Count().SetLimit(1))
}

// ListAllInRelease reads active nodes from one snapshot for suggestion and search.
func (s *MongoTagNodeStore) ListAllInRelease(ctx context.Context, releaseID string) ([]model.TagNode, error) {
	cur, err := s.coll.Find(
		ctx,
		bson.M{"releaseId": releaseID, "lifecycleStatus": "active"},
		options.Find().SetSort(bson.D{
			{Key: "group", Value: 1},
			{Key: "depth", Value: 1},
			{Key: "tagRef", Value: 1},
		}),
	)
	if err != nil {
		return nil, err
	}
	defer cur.Close(ctx)
	out := make([]model.TagNode, 0)
	if err := cur.All(ctx, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// ListDimensionsInRelease reads dimension metadata from the active immutable
// taxonomy snapshot; no application-owned dimension catalog is maintained.
func (s *MongoTagNodeStore) ListDimensionsInRelease(
	ctx context.Context,
	releaseID string,
) ([]model.TagNode, error) {
	cursor, err := s.coll.Find(
		ctx,
		bson.M{
			"releaseId":       releaseID,
			"lifecycleStatus": "active",
			"nodeKind":        "dimension",
		},
		options.Find().SetSort(bson.D{
			{Key: "group", Value: 1},
			{Key: "tagRef", Value: 1},
		}),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	out := make([]model.TagNode, 0)
	if err := cursor.All(ctx, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// IsActiveLeaf verifies a node and its direct children in one Mongo aggregate
// request so ValidateTagRefs needs at most one storage query per distinct tagRef.
func (s *MongoTagNodeStore) IsActiveLeaf(ctx context.Context, releaseID, tagRef string) (bool, error) {
	pipeline := mongo.Pipeline{
		bson.D{{Key: "$match", Value: bson.D{
			{Key: "releaseId", Value: releaseID},
			{Key: "tagRef", Value: tagRef},
			{Key: "lifecycleStatus", Value: "active"},
		}}},
		bson.D{{Key: "$lookup", Value: bson.D{
			{Key: "from", Value: s.coll.Name()},
			{Key: "let", Value: bson.D{{Key: "parentTagRef", Value: "$tagRef"}}},
			{Key: "pipeline", Value: mongo.Pipeline{
				bson.D{{Key: "$match", Value: bson.D{
					{Key: "releaseId", Value: releaseID},
					{Key: "lifecycleStatus", Value: "active"},
					{Key: "$expr", Value: bson.D{{Key: "$eq", Value: bson.A{"$parentTagRef", "$$parentTagRef"}}}},
				}}},
				bson.D{{Key: "$limit", Value: 1}},
			}},
			{Key: "as", Value: "activeChildren"},
		}}},
		bson.D{{Key: "$match", Value: bson.D{
			{Key: "activeChildren.0", Value: bson.D{{Key: "$exists", Value: false}}},
		}}},
		bson.D{{Key: "$limit", Value: 1}},
	}
	cursor, err := s.coll.Aggregate(ctx, pipeline)
	if err != nil {
		return false, err
	}
	defer cursor.Close(ctx)
	return cursor.Next(ctx), cursor.Err()
}

// HasCompleteSnapshot is the release activation readiness check. Snapshot
// identity is enforced by the unique (releaseId, tagRef) index, so matching the
// staged node count and required lifecycle fields proves no partial import is
// eligible for activation.
func (s *MongoTagNodeStore) HasCompleteSnapshot(
	ctx context.Context,
	releaseID string,
	expectedNodeCount int,
) (bool, error) {
	if expectedNodeCount <= 0 {
		return false, nil
	}
	count, err := s.coll.CountDocuments(ctx, bson.M{
		"releaseId":       releaseID,
		"tagRef":          bson.M{"$type": "string", "$ne": ""},
		"lifecycleStatus": bson.M{"$in": bson.A{"active", "deprecated"}},
	})
	if err != nil {
		return false, err
	}
	return count == int64(expectedNodeCount), nil
}

// ValidateReleaseProjection rejects incomplete legacy snapshots instead of
// silently falling back to an application-owned taxonomy catalog.
func (s *MongoTagNodeStore) ValidateReleaseProjection(
	ctx context.Context,
	releaseID string,
) error {
	releaseID = strings.TrimSpace(releaseID)
	if releaseID == "" {
		return errors.New("taxonomy release id is required")
	}
	total, err := s.coll.CountDocuments(ctx, bson.M{"releaseId": releaseID})
	if err != nil {
		return err
	}
	if total == 0 {
		return errors.New("taxonomy release snapshot is empty")
	}
	invalid, err := s.coll.CountDocuments(ctx, bson.M{
		"releaseId": releaseID,
		"nodeKind": bson.M{"$nin": bson.A{
			"group",
			"dimension",
			"definition",
		}},
	})
	if err != nil {
		return err
	}
	if invalid != 0 {
		return fmt.Errorf(
			"taxonomy release %s has %d incomplete projected nodes",
			releaseID,
			invalid,
		)
	}
	return nil
}
