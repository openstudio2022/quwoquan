package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	followingsubject "quwoquan_service/services/user-service/internal/profile_projection/following_subject/application"
)

// MongoFollowingSubjectStore 是 following_subjects 投影的唯一 writer 与
// named reader。写入按 source (subjectType 事件流) 的版本单调，可重建。
type MongoFollowingSubjectStore struct {
	collection *mongo.Collection
}

func NewMongoFollowingSubjectStore(database *mongo.Database) *MongoFollowingSubjectStore {
	if database == nil {
		return &MongoFollowingSubjectStore{}
	}
	return &MongoFollowingSubjectStore{
		collection: database.Collection("following_subjects"),
	}
}

func (s *MongoFollowingSubjectStore) EnsureIndexes(ctx context.Context) error {
	if s == nil || s.collection == nil {
		return nil
	}
	_, err := s.collection.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "viewerSubAccountId", Value: 1},
				{Key: "subjectType", Value: 1},
				{Key: "subjectId", Value: 1},
			},
			Options: options.Index().SetName("idx_following_subject_viewer_subject").SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "viewerSubAccountId", Value: 1},
				{Key: "subjectType", Value: 1},
				{Key: "latestChangedAt", Value: -1},
			},
			Options: options.Index().SetName("idx_following_subject_viewer_type_changed"),
		},
	})
	return err
}

// UpsertFollow 应用关注事实；sourceVersion 单调防止乱序回退。
func (s *MongoFollowingSubjectStore) UpsertFollow(
	ctx context.Context,
	personaID, subjectType, subjectID string,
	followedAt time.Time,
	sourceVersion int64,
) error {
	if s == nil || s.collection == nil {
		return errors.New("following subject store is unavailable")
	}
	now := time.Now().UTC()
	filter := bson.M{
		"viewerSubAccountId": personaID,
		"subjectType":        subjectType,
		"subjectId":          subjectID,
		"$or": bson.A{
			bson.M{"sourceVersion": bson.M{"$lt": sourceVersion}},
			bson.M{"sourceVersion": bson.M{"$exists": false}},
		},
	}
	update := bson.M{
		"$set": bson.M{
			"followedAt":    followedAt.UTC(),
			"sourceVersion": sourceVersion,
			"updatedAt":     now,
		},
		"$setOnInsert": bson.M{
			"viewerSubAccountId": personaID,
			"subjectType":        subjectType,
			"subjectId":          subjectID,
			"unreadChangeCount":  int64(0),
		},
	}
	_, err := s.collection.UpdateOne(ctx, filter, update, options.UpdateOne().SetUpsert(true))
	if err != nil && mongo.IsDuplicateKeyError(err) {
		// 唯一键已存在且 sourceVersion 不小于本事件：乱序旧事件，安全忽略。
		return nil
	}
	if err != nil {
		return fmt.Errorf("upsert following subject: %w", err)
	}
	return nil
}

// RemoveFollow 应用取关/退出事实；仅当事件不落后于当前投影版本时删除。
func (s *MongoFollowingSubjectStore) RemoveFollow(
	ctx context.Context,
	personaID, subjectType, subjectID string,
	sourceVersion int64,
) error {
	if s == nil || s.collection == nil {
		return errors.New("following subject store is unavailable")
	}
	_, err := s.collection.DeleteOne(ctx, bson.M{
		"viewerSubAccountId": personaID,
		"subjectType":        subjectType,
		"subjectId":          subjectID,
		"sourceVersion":      bson.M{"$lte": sourceVersion},
	})
	if err != nil {
		return fmt.Errorf("remove following subject: %w", err)
	}
	return nil
}

// ApplyVisit 应用访问水位事实：清除未读并推进 lastVisitedAt。
func (s *MongoFollowingSubjectStore) ApplyVisit(
	ctx context.Context,
	personaID, subjectType, subjectID string,
	visitedAt time.Time,
) error {
	if s == nil || s.collection == nil {
		return errors.New("following subject store is unavailable")
	}
	_, err := s.collection.UpdateOne(ctx, bson.M{
		"viewerSubAccountId": personaID,
		"subjectType":        subjectType,
		"subjectId":          subjectID,
	}, bson.M{
		"$max": bson.M{"lastVisitedAt": visitedAt.UTC()},
		"$set": bson.M{
			"unreadChangeCount": int64(0),
			"updatedAt":         time.Now().UTC(),
		},
	})
	if err != nil {
		return fmt.Errorf("apply following subject visit: %w", err)
	}
	return nil
}

// List 返回 viewer 的关注对象切片（latestChangedAt 优先、followedAt 兜底的
// 稳定排序），cursor 为上一页最后一行的 subjectType/subjectId 复合标识。
func (s *MongoFollowingSubjectStore) List(
	ctx context.Context,
	personaID, subjectType string,
	limit int,
) ([]followingsubject.Row, error) {
	if s == nil || s.collection == nil {
		return nil, errors.New("following subject store is unavailable")
	}
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	filter := bson.M{"viewerSubAccountId": strings.TrimSpace(personaID)}
	if subjectType = strings.TrimSpace(subjectType); subjectType != "" {
		filter["subjectType"] = subjectType
	}
	cursor, err := s.collection.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{
				{Key: "latestChangedAt", Value: -1},
				{Key: "followedAt", Value: -1},
				{Key: "subjectId", Value: -1},
			}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, fmt.Errorf("list following subjects: %w", err)
	}
	defer cursor.Close(ctx)
	var rows []followingsubject.Row
	if err := cursor.All(ctx, &rows); err != nil {
		return nil, fmt.Errorf("decode following subjects: %w", err)
	}
	return rows, nil
}
