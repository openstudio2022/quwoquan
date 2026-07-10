package persistence

import (
	"context"
	"errors"
	"regexp"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	model "quwoquan_service/services/tag-service/internal/domain/tag/model"
)

// MongoObjectTagIndexStore 是 ObjectTagIndex 的只读 Mongo 存储（embed codegen base）。
type MongoObjectTagIndexStore struct {
	mongoObjectTagIndexStoreBase
}

// NewMongoObjectTagIndexStore 构造对象↔tagRef 索引存储。
func NewMongoObjectTagIndexStore(coll *mongo.Collection) *MongoObjectTagIndexStore {
	return &MongoObjectTagIndexStore{mongoObjectTagIndexStoreBase{coll: coll}}
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
