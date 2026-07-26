package persistence

import (
	"context"
	"errors"
	"regexp"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	generated "quwoquan_service/services/tag-service/generated/tag/object_tag_index_view/persistence/tag/persistence"
	model "quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/model"
	ports "quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/ports"
)

// MongoObjectTagIndexStore 是 ObjectTagIndex 的只读 Mongo 存储（embed codegen base）。
type MongoObjectTagIndexStore struct {
	*generated.MongoObjectTagIndexStoreBase
	coll *mongo.Collection
}

// NewMongoObjectTagIndexStore 构造对象↔tagRef 索引存储。
func NewMongoObjectTagIndexStore(coll *mongo.Collection) *MongoObjectTagIndexStore {
	return &MongoObjectTagIndexStore{
		MongoObjectTagIndexStoreBase: generated.NewMongoObjectTagIndexStoreBase(coll),
		coll:                         coll,
	}
}

// FindByObject 取单个对象的 tagRefs 索引；未命中返回 (nil, nil)。
func (s *MongoObjectTagIndexStore) FindByObject(ctx context.Context, objectID, objectType string) (*model.ObjectTagIndex, error) {
	var idx model.ObjectTagIndex
	if err := s.coll.FindOne(ctx, bson.M{"objectId": objectID, "objectType": objectType}).Decode(&idx); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, nil
		}
		return nil, err
	}
	return &idx, nil
}

// FindObjectsByTagRef 反向查询：引用某 tagRef 的对象索引（tagRefs 为数组，走 contains）。
func (s *MongoObjectTagIndexStore) FindObjectsByTagRef(ctx context.Context, tagRef, objectType string, limit int64) ([]model.ObjectTagIndex, error) {
	filter := bson.M{"tagRefs": tagRef}
	if objectType != "" {
		filter["objectType"] = objectType
	}
	opts := options.Find()
	if limit > 0 {
		opts.SetLimit(limit)
	}
	cur, err := s.coll.Find(ctx, filter, opts)
	if err != nil {
		return nil, err
	}
	defer cur.Close(ctx)
	out := make([]model.ObjectTagIndex, 0)
	if err := cur.All(ctx, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// FindObjectsByTagRefSubtree 子孙展开反查：tagRefs 命中 tagRef 自身或其任意
// 子孙（锚定前缀正则 ^{tagRef}(/|$)，路径制标签的子孙即 "/" 分隔的更深路径）。
// 查询侧展开、存储不物化祖先链；锚定前缀正则可走 tagRefs 多键索引。
func (s *MongoObjectTagIndexStore) FindObjectsByTagRefSubtree(ctx context.Context, tagRef, objectType string, limit int64) ([]model.ObjectTagIndex, error) {
	pattern := "^" + regexp.QuoteMeta(tagRef) + "(/|$)"
	filter := bson.M{"tagRefs": bson.M{"$regex": pattern}}
	if objectType != "" {
		filter["objectType"] = objectType
	}
	opts := options.Find()
	if limit > 0 {
		opts.SetLimit(limit)
	}
	cur, err := s.coll.Find(ctx, filter, opts)
	if err != nil {
		return nil, err
	}
	defer cur.Close(ctx)
	out := make([]model.ObjectTagIndex, 0)
	if err := cur.All(ctx, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// UpsertObjectTags 幂等写入对象的 tagRefs 倒排（按 {objectId, objectType} 唯一键）。
// 派生数据，可由离线回填管道重建；nil tagRefs 规整为空数组。
func (s *MongoObjectTagIndexStore) UpsertObjectTags(ctx context.Context, objectID, objectType string, tagRefs []string) error {
	now := time.Now().UTC()
	if tagRefs == nil {
		tagRefs = []string{}
	}
	_, err := s.coll.UpdateOne(ctx,
		bson.M{"objectId": objectID, "objectType": objectType},
		bson.M{
			"$set":         bson.M{"tagRefs": tagRefs, "updatedAt": now},
			"$setOnInsert": bson.M{"createdAt": now},
		},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

// UpsertObjectTagsFromRelease 原子写入环境数据发布投影及其来源信息。
// visibleFromReleaseId 只在首次插入时确定，后续发布重放不会改写首见批次。
func (s *MongoObjectTagIndexStore) UpsertObjectTagsFromRelease(
	ctx context.Context,
	objectID, objectType string,
	tagRefs []string,
	releaseID, sourceOwner string,
) error {
	now := time.Now().UTC()
	if tagRefs == nil {
		tagRefs = []string{}
	}
	_, err := s.coll.UpdateOne(
		ctx,
		bson.M{"objectId": objectID, "objectType": objectType},
		bson.M{
			"$set": bson.M{
				"tagRefs":          tagRefs,
				"updatedAt":        now,
				"releaseId":        releaseID,
				"sourceOwner":      sourceOwner,
				"lifecycleStatus":  "active",
				"releaseUpdatedAt": now,
			},
			"$setOnInsert": bson.M{
				"createdAt":            now,
				"visibleFromReleaseId": releaseID,
			},
		},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

// ApplyUserProfileTagProjection 只允许更大的 profileVersion 覆盖当前投影。
// Redis Stream 至少一次重放和跨 consumer 的乱序交付因此都收敛到最新源版本。
func (s *MongoObjectTagIndexStore) ApplyUserProfileTagProjection(
	ctx context.Context,
	projection ports.UserProfileTagProjection,
) (bool, error) {
	eventID := strings.TrimSpace(projection.EventID)
	userID := strings.TrimSpace(projection.UserID)
	taxonomyReleaseID := strings.TrimSpace(projection.TaxonomyReleaseID)
	if eventID == "" || userID == "" || taxonomyReleaseID == "" ||
		projection.ProfileVersion <= 0 || projection.OccurredAt.IsZero() {
		return false, errors.New("invalid user profile tag projection")
	}
	tagRefs := projection.TagRefs
	if tagRefs == nil {
		tagRefs = []string{}
	}
	result, err := s.coll.UpdateOne(
		ctx,
		bson.M{
			"objectId":   userID,
			"objectType": "user",
			"$or": bson.A{
				bson.M{"sourceAggregateVersion": bson.M{"$exists": false}},
				bson.M{
					"sourceAggregateVersion": bson.M{
						"$lt": projection.ProfileVersion,
					},
				},
			},
		},
		bson.M{
			"$set": bson.M{
				"objectId":               userID,
				"objectType":             "user",
				"tagRefs":                tagRefs,
				"taxonomyReleaseId":      taxonomyReleaseID,
				"sourceOwner":            "user-service",
				"sourceAggregateVersion": projection.ProfileVersion,
				"sourceEventId":          eventID,
				"lifecycleStatus":        "active",
				"updatedAt":              projection.OccurredAt.UTC(),
			},
			"$setOnInsert": bson.M{"createdAt": projection.OccurredAt.UTC()},
		},
		options.UpdateOne().SetUpsert(true),
	)
	if mongo.IsDuplicateKeyError(err) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return result.UpsertedCount == 1 || result.ModifiedCount == 1, nil
}

var _ ports.UserProfileTagProjector = (*MongoObjectTagIndexStore)(nil)
