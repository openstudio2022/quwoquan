package persistence

import (
	"context"
	"errors"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	model "quwoquan_service/services/tag-service/internal/domain/tag/model"
)

// MongoTagNodeStore 是 TagNode 的只读 Mongo 存储（embed codegen base）。
type MongoTagNodeStore struct {
	mongoTagNodeStoreBase
}

// NewMongoTagNodeStore 构造 TagNode 存储。
func NewMongoTagNodeStore(coll *mongo.Collection) *MongoTagNodeStore {
	return &MongoTagNodeStore{mongoTagNodeStoreBase{coll: coll}}
}

// FindByTagRef 按路径制 tagRef 精确查询标签定义；未命中返回 (nil, nil)。
func (s *MongoTagNodeStore) FindByTagRef(ctx context.Context, tagRef string) (*model.TagNode, error) {
	var node model.TagNode
	if err := s.coll.FindOne(ctx, bson.M{"tagRef": tagRef}).Decode(&node); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, nil
		}
		return nil, err
	}
	return &node, nil
}

// TagRefExists 供 TagFeedback append 校验 tagRef 有效性（tagfeedback.TagRefValidator）。
func (s *MongoTagNodeStore) TagRefExists(ctx context.Context, tagRef string) (bool, error) {
	node, err := s.FindByTagRef(ctx, tagRef)
	if err != nil {
		return false, err
	}
	return node != nil, nil
}

// ListChildren 读取某 tagRef 的 active 直接子节点，供层级浏览/行政区选择使用。
func (s *MongoTagNodeStore) ListChildren(ctx context.Context, parentTagRef string, limit int64) ([]model.TagNode, error) {
	filter := bson.M{
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

// CountActiveChildren 返回某 tagRef 下 active 子节点数量。
func (s *MongoTagNodeStore) CountActiveChildren(ctx context.Context, parentTagRef string) (int64, error) {
	return s.coll.CountDocuments(ctx, bson.M{
		"parentTagRef":    parentTagRef,
		"lifecycleStatus": "active",
	}, options.Count().SetLimit(1))
}

// ListAll 读取全部标签节点，供 suggest / 面板类查询使用。
func (s *MongoTagNodeStore) ListAll(ctx context.Context) ([]model.TagNode, error) {
	cur, err := s.coll.Find(
		ctx,
		bson.M{},
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
