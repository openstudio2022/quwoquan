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
