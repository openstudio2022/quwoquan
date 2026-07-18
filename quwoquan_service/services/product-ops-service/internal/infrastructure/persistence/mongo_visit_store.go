package persistence

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/product-ops-service/internal/application"
)

// MongoVisitStore 仅保存 visit_record 业务事实；产品事件不再创建、索引或查询
// event_records 集合。
type MongoVisitStore struct{ collection *mongo.Collection }

func NewMongoVisitStore(db *mongo.Database) *MongoVisitStore {
	return &MongoVisitStore{collection: db.Collection("visit_records")}
}

func (s *MongoVisitStore) EnsureIndexes(ctx context.Context) error {
	indexes := []mongo.IndexModel{
		{Keys: bson.D{{Key: "userId", Value: 1}, {Key: "targetType", Value: 1}, {Key: "targetKey", Value: 1}}, Options: options.Index().SetName("uq_visit_user_target").SetUnique(true)},
		{Keys: bson.D{{Key: "targetType", Value: 1}, {Key: "targetKey", Value: 1}, {Key: "timestamp", Value: -1}}, Options: options.Index().SetName("idx_visit_target")},
		{Keys: bson.D{{Key: "sessionId", Value: 1}, {Key: "timestamp", Value: -1}}, Options: options.Index().SetName("idx_visit_session").SetSparse(true)},
		{Keys: bson.D{{Key: "timestamp", Value: 1}}, Options: options.Index().SetName("ttl_visit_timestamp").SetExpireAfterSeconds(180 * 24 * 60 * 60)},
	}
	_, err := s.collection.Indexes().CreateMany(ctx, indexes)
	if err != nil {
		return fmt.Errorf("create visit indexes: %w", err)
	}
	return nil
}

func (s *MongoVisitStore) RecordVisit(ctx context.Context, input application.VisitInput) (application.VisitRecord, error) {
	now := time.Now().UTC()
	filter := bson.D{{Key: "userId", Value: input.UserID}, {Key: "targetType", Value: input.TargetType}, {Key: "targetKey", Value: input.TargetKey}}
	set := bson.D{{Key: "lastSeenAt", Value: now.Format(time.RFC3339Nano)}, {Key: "timestamp", Value: now}}
	if value := strings.TrimSpace(input.SessionID); value != "" {
		set = append(set, bson.E{Key: "sessionId", Value: value})
	}
	if value := strings.TrimSpace(input.Source); value != "" {
		set = append(set, bson.E{Key: "source", Value: value})
	}
	update := bson.D{
		{Key: "$inc", Value: bson.D{{Key: "visitCount", Value: 1}}},
		{Key: "$set", Value: set},
		{Key: "$setOnInsert", Value: bson.D{{Key: "userId", Value: input.UserID}, {Key: "targetType", Value: input.TargetType}, {Key: "targetKey", Value: input.TargetKey}}},
	}
	var record application.VisitRecord
	err := s.collection.FindOneAndUpdate(ctx, filter, update, options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After)).Decode(&record)
	if err != nil {
		return application.VisitRecord{}, fmt.Errorf("record visit: %w", err)
	}
	return record, nil
}

func (s *MongoVisitStore) GetVisitStats(ctx context.Context, query application.VisitStatsQuery) (application.VisitStats, error) {
	filter := bson.D{}
	if value := strings.TrimSpace(query.TargetType); value != "" {
		filter = append(filter, bson.E{Key: "targetType", Value: value})
	}
	if value := strings.TrimSpace(query.TargetKey); value != "" {
		filter = append(filter, bson.E{Key: "targetKey", Value: value})
	}
	cursor, err := s.collection.Find(ctx, filter)
	if err != nil {
		return application.VisitStats{}, fmt.Errorf("find visit stats: %w", err)
	}
	defer cursor.Close(ctx)
	out := application.VisitStats{Items: []application.VisitRecord{}}
	for cursor.Next(ctx) {
		var item application.VisitRecord
		if err := cursor.Decode(&item); err != nil {
			return application.VisitStats{}, err
		}
		out.TotalVisits += item.VisitCount
		out.Items = append(out.Items, item)
	}
	if err := cursor.Err(); err != nil {
		return application.VisitStats{}, err
	}
	sort.Slice(out.Items, func(i, j int) bool { return out.Items[i].VisitCount > out.Items[j].VisitCount })
	return out, nil
}

var _ application.VisitTelemetryStore = (*MongoVisitStore)(nil)
