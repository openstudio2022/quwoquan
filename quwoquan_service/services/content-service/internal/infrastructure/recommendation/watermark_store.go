package recommendation

import (
	"context"
	"log/slog"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	app "quwoquan_service/services/content-service/internal/application"
)

// intersectionWatermarkCollection 是「我的交集」已读水位的耐久兜底集合。
// Redis（ix:watermark hash）是加速读缓存；本集合是耐久真相源——Redis flush/宕机后
// 用户已读位（清零状态）不丢失，写降级也不阻断主请求。一 user 一文档。
const intersectionWatermarkCollection = "rm_intersection_watermark"

// MongoWatermarkStore 是 app.WatermarkStore 的 Mongo 实现。
// 文档形如 {_id: userID, wm: {identity: ts, content: ts, ...}, updatedAt}；
// 写入用 $max 逐维度合并，保证已读水位单调推进（晚到的旧时间戳不会回退已推进的位）。
type MongoWatermarkStore struct {
	coll   *mongo.Collection
	logger *slog.Logger
}

// NewMongoWatermarkStore 构造耐久水位存储。
func NewMongoWatermarkStore(db *mongo.Database, logger *slog.Logger) *MongoWatermarkStore {
	if logger == nil {
		logger = slog.Default()
	}
	return &MongoWatermarkStore{
		coll:   db.Collection(intersectionWatermarkCollection),
		logger: logger,
	}
}

var _ app.WatermarkStore = (*MongoWatermarkStore)(nil)

// LoadWatermarks 返回 userID 的 per-dimension 已读水位（unix 秒）。无记录返回空 map。
func (s *MongoWatermarkStore) LoadWatermarks(ctx context.Context, userID string) (map[string]int64, error) {
	userID = strings.TrimSpace(userID)
	out := map[string]int64{}
	if userID == "" {
		return out, nil
	}
	var doc struct {
		Watermarks map[string]int64 `bson:"wm"`
	}
	err := s.coll.FindOne(ctx, bson.M{"_id": userID}).Decode(&doc)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return out, nil
		}
		return nil, err
	}
	for d, ts := range doc.Watermarks {
		out[d] = ts
	}
	return out, nil
}

// SaveWatermarks 以 upsert + $max 逐维度合并写入水位（耐久、单调推进）。
func (s *MongoWatermarkStore) SaveWatermarks(ctx context.Context, userID string, dims map[string]int64) error {
	userID = strings.TrimSpace(userID)
	if userID == "" || len(dims) == 0 {
		return nil
	}
	maxFields := bson.M{}
	for d, ts := range dims {
		d = strings.TrimSpace(d)
		if d == "" {
			continue
		}
		maxFields["wm."+d] = ts
	}
	if len(maxFields) == 0 {
		return nil
	}
	_, err := s.coll.UpdateOne(
		ctx,
		bson.M{"_id": userID},
		bson.M{
			"$max": maxFields,
			"$set": bson.M{"updatedAt": time.Now().UTC()},
		},
		options.UpdateOne().SetUpsert(true),
	)
	if err != nil {
		s.logger.Error("intersection_watermark: save failed",
			slog.String("error", err.Error()),
			slog.String("userId", userID),
		)
	}
	return err
}
