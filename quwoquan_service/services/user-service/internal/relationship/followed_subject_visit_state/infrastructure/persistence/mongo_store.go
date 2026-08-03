package persistence

import (
	"context"
	"errors"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	visitmodel "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/domain/model"
)

// MongoFollowedSubjectVisitStore 持久化 viewer × subject 的访问水位。
// lastVisitedAt 用 $max 单调推进；重复 clientRequestId 返回已存 receipt。
type MongoFollowedSubjectVisitStore struct {
	collection *mongo.Collection
}

func NewMongoFollowedSubjectVisitStore(database *mongo.Database) *MongoFollowedSubjectVisitStore {
	if database == nil {
		return &MongoFollowedSubjectVisitStore{}
	}
	return &MongoFollowedSubjectVisitStore{
		collection: database.Collection("followed_subject_visit_states"),
	}
}

func (s *MongoFollowedSubjectVisitStore) EnsureIndexes(ctx context.Context) error {
	if s == nil || s.collection == nil {
		return nil
	}
	_, err := s.collection.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "personaId", Value: 1},
				{Key: "subjectType", Value: 1},
				{Key: "subjectId", Value: 1},
			},
			Options: options.Index().SetName("uq_visit_identity").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "personaId", Value: 1}, {Key: "updatedAt", Value: -1}},
			Options: options.Index().SetName("idx_visit_persona_updated"),
		},
	})
	return err
}

type visitStateDocument struct {
	PersonaID           string    `bson:"personaId"`
	SubjectType         string    `bson:"subjectType"`
	SubjectID           string    `bson:"subjectId"`
	LastVisitedAt       time.Time `bson:"lastVisitedAt"`
	LastClientRequestID string    `bson:"lastClientRequestId"`
	UpdatedAt           time.Time `bson:"updatedAt"`
}

// MarkVisited 原子推进水位并返回提交后的结果。重复 clientRequestId 是幂等
// 重放：返回已存结果、不再推进水位。
func (s *MongoFollowedSubjectVisitStore) MarkVisited(
	ctx context.Context,
	command visitmodel.MarkVisitedCommand,
) (visitmodel.VisitResult, error) {
	if s == nil || s.collection == nil {
		return visitmodel.VisitResult{}, errors.New("followed subject visit store is unavailable")
	}
	filter := bson.M{
		"personaId":   command.PersonaID,
		"subjectType": command.SubjectType,
		"subjectId":   command.SubjectID,
	}

	var existing visitStateDocument
	err := s.collection.FindOne(ctx, filter).Decode(&existing)
	switch {
	case err == nil:
		if existing.LastClientRequestID == command.ClientRequestID {
			return visitmodel.VisitResult{
				SubjectID:        existing.SubjectID,
				SubjectType:      existing.SubjectType,
				LastVisitedAt:    existing.LastVisitedAt.UTC(),
				HasUnreadChanges: false,
				Replayed:         true,
			}, nil
		}
	case errors.Is(err, mongo.ErrNoDocuments):
	default:
		return visitmodel.VisitResult{}, fmt.Errorf("load followed subject visit state: %w", err)
	}

	now := time.Now().UTC()
	update := bson.M{
		"$max": bson.M{"lastVisitedAt": command.VisitedAt},
		"$set": bson.M{
			"lastClientRequestId": command.ClientRequestID,
			"updatedAt":           now,
		},
		"$setOnInsert": bson.M{
			"personaId":   command.PersonaID,
			"subjectType": command.SubjectType,
			"subjectId":   command.SubjectID,
		},
	}
	var updated visitStateDocument
	err = s.collection.FindOneAndUpdate(
		ctx,
		filter,
		update,
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&updated)
	if err != nil {
		return visitmodel.VisitResult{}, fmt.Errorf("mark followed subject visited: %w", err)
	}
	return visitmodel.VisitResult{
		SubjectID:        updated.SubjectID,
		SubjectType:      updated.SubjectType,
		LastVisitedAt:    updated.LastVisitedAt.UTC(),
		HasUnreadChanges: false,
	}, nil
}

func (s *MongoFollowedSubjectVisitStore) DeleteForClosedSubjects(
	ctx context.Context,
	accountID string,
	personaIDs []string,
) error {
	if s == nil || s.collection == nil {
		return errors.New("followed subject visit store is unavailable")
	}
	subjectIDs := append([]string{accountID}, personaIDs...)
	_, err := s.collection.DeleteMany(ctx, bson.M{
		"$or": bson.A{
			bson.M{"personaId": bson.M{"$in": personaIDs}},
			bson.M{"subjectType": "persona", "subjectId": bson.M{"$in": subjectIDs}},
		},
	})
	if err != nil {
		return fmt.Errorf("delete closed subject visit states: %w", err)
	}
	return nil
}
