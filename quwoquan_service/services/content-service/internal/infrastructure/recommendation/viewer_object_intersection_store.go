package recommendation

import (
	"context"
	"encoding/json"
	"log/slog"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	app "quwoquan_service/services/content-service/internal/application"
)

// viewerObjectIntersectionCollection 是事实交集读模型集合（WP-2 预物化）。
// 每个 viewer 一份快照文档：viewer 与各对象的事实交集理由 + 物化时刻；
// summary/list/feed 读路径只点查本集合，不在请求期做社交图谱扫描（零打分）。
const viewerObjectIntersectionCollection = "rm_viewer_object_intersection"

// ViewerIntersectionDoc 是单个 viewer 的事实交集预物化快照。
type ViewerIntersectionDoc struct {
	ViewerID   string
	Reasons    []app.IntersectionReasonView
	ComputedAt time.Time
}

// ViewerIntersectionReadModel 持久化/读取 rm_viewer_object_intersection。
// 它不承载任何打分/图谱逻辑：读为 O(1) 点查，保证 summary/list/feed 不在热路径重算。
type ViewerIntersectionReadModel interface {
	Load(ctx context.Context, viewerID string) (ViewerIntersectionDoc, bool, error)
	Save(ctx context.Context, doc ViewerIntersectionDoc) error
}

// MongoViewerIntersectionStore 是 Mongo 实现（一 viewer 一文档）。
// reasons 以 JSON blob 存储：读模型只整文档点查，无需按字段查询，JSON 保证
// app.IntersectionReasonView 全字段精确往返，避免 bson 字段名映射歧义。
type MongoViewerIntersectionStore struct {
	coll   *mongo.Collection
	logger *slog.Logger
}

func NewMongoViewerIntersectionStore(db *mongo.Database, logger *slog.Logger) *MongoViewerIntersectionStore {
	if logger == nil {
		logger = slog.Default()
	}
	s := &MongoViewerIntersectionStore{
		coll:   db.Collection(viewerObjectIntersectionCollection),
		logger: logger,
	}
	s.ensureIndexes()
	return s
}

func (s *MongoViewerIntersectionStore) ensureIndexes() {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	// computedAt 倒排：供保鲜巡检 / 物化新鲜度观测。
	idx := mongo.IndexModel{Keys: bson.D{{Key: "computedAt", Value: -1}}}
	if _, err := s.coll.Indexes().CreateOne(ctx, idx); err != nil {
		s.logger.Warn("viewer_object_intersection: index creation failed", slog.String("error", err.Error()))
	}
}

func (s *MongoViewerIntersectionStore) Load(ctx context.Context, viewerID string) (ViewerIntersectionDoc, bool, error) {
	viewerID = strings.TrimSpace(viewerID)
	if viewerID == "" {
		return ViewerIntersectionDoc{}, false, nil
	}
	var doc struct {
		ID          string    `bson:"_id"`
		ComputedAt  time.Time `bson:"computedAt"`
		ReasonsJSON string    `bson:"reasonsJson"`
	}
	err := s.coll.FindOne(ctx, bson.M{"_id": viewerID}).Decode(&doc)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return ViewerIntersectionDoc{}, false, nil
		}
		return ViewerIntersectionDoc{}, false, err
	}
	out := ViewerIntersectionDoc{ViewerID: viewerID, ComputedAt: doc.ComputedAt}
	if strings.TrimSpace(doc.ReasonsJSON) != "" {
		if err := json.Unmarshal([]byte(doc.ReasonsJSON), &out.Reasons); err != nil {
			return ViewerIntersectionDoc{}, false, err
		}
	}
	return out, true, nil
}

func (s *MongoViewerIntersectionStore) Save(ctx context.Context, doc ViewerIntersectionDoc) error {
	viewerID := strings.TrimSpace(doc.ViewerID)
	if viewerID == "" {
		return nil
	}
	payload, err := json.Marshal(doc.Reasons)
	if err != nil {
		return err
	}
	computedAt := doc.ComputedAt
	if computedAt.IsZero() {
		computedAt = time.Now().UTC()
	}
	_, err = s.coll.UpdateOne(
		ctx,
		bson.M{"_id": viewerID},
		bson.M{"$set": bson.M{
			"computedAt":  computedAt,
			"reasonsJson": string(payload),
		}},
		options.UpdateOne().SetUpsert(true),
	)
	if err != nil {
		s.logger.Error("viewer_object_intersection: save failed",
			slog.String("error", err.Error()),
			slog.String("viewerId", viewerID),
		)
	}
	return err
}
