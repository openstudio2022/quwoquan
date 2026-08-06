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
// 水位与 FollowedSubjectVisited outbox 记录在同一个 Mongo 事务内提交。
type MongoFollowedSubjectVisitStore struct {
	collection *mongo.Collection
	outbox     *mongo.Collection
}

func NewMongoFollowedSubjectVisitStore(database *mongo.Database) *MongoFollowedSubjectVisitStore {
	if database == nil {
		return &MongoFollowedSubjectVisitStore{}
	}
	return &MongoFollowedSubjectVisitStore{
		collection: database.Collection("followed_subject_visit_states"),
		outbox:     database.Collection("followed_subject_visit_outbox"),
	}
}

func (s *MongoFollowedSubjectVisitStore) EnsureIndexes(ctx context.Context) error {
	if s == nil || s.collection == nil {
		return nil
	}
	if _, err := s.collection.Indexes().CreateMany(ctx, []mongo.IndexModel{
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
	}); err != nil {
		return err
	}
	_, err := s.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "publishedAt", Value: 1},
				{Key: "leasedUntil", Value: 1},
				{Key: "occurredAt", Value: 1},
			},
			Options: options.Index().SetName("idx_visit_outbox_pending"),
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

// MarkVisited 原子推进水位并在同一事务内追加 FollowedSubjectVisited。重复
// clientRequestId 是幂等重放：返回已存结果、不再推进水位、不追加第二条事件。
// 事务保证不会出现「水位已推进但事件丢失」或「事件已投递但水位回滚」。
func (s *MongoFollowedSubjectVisitStore) MarkVisited(
	ctx context.Context,
	command visitmodel.MarkVisitedCommand,
) (visitmodel.VisitResult, error) {
	if s == nil || s.collection == nil || s.outbox == nil {
		return visitmodel.VisitResult{}, errors.New("followed subject visit store is unavailable")
	}
	session, err := s.collection.Database().Client().StartSession()
	if err != nil {
		return visitmodel.VisitResult{}, fmt.Errorf("start followed subject visit transaction: %w", err)
	}
	defer session.EndSession(ctx)

	var result visitmodel.VisitResult
	if _, err := session.WithTransaction(
		ctx,
		func(txCtx context.Context) (any, error) {
			filter := bson.M{
				"personaId":   command.PersonaID,
				"subjectType": command.SubjectType,
				"subjectId":   command.SubjectID,
			}
			var existing visitStateDocument
			readErr := s.collection.FindOne(txCtx, filter).Decode(&existing)
			switch {
			case readErr == nil:
				if existing.LastClientRequestID == command.ClientRequestID {
					result = visitmodel.VisitResult{
						SubjectID:        existing.SubjectID,
						SubjectType:      existing.SubjectType,
						LastVisitedAt:    existing.LastVisitedAt.UTC(),
						HasUnreadChanges: false,
						Replayed:         true,
					}
					return nil, nil
				}
			case errors.Is(readErr, mongo.ErrNoDocuments):
			default:
				return nil, fmt.Errorf("load followed subject visit state: %w", readErr)
			}

			now := time.Now().UTC()
			var updated visitStateDocument
			if err := s.collection.FindOneAndUpdate(
				txCtx,
				filter,
				bson.M{
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
				},
				options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
			).Decode(&updated); err != nil {
				return nil, fmt.Errorf("mark followed subject visited: %w", err)
			}

			// 事件行与水位共用同一个事务句柄：提交成功即 FollowedSubjectVisited 必然
			// 可投递，任一步失败则水位与事件一起回滚。eventId 由 clientRequestId 派生，
			// 重复命令即使绕过前置重放短路也只会命中唯一键。
			if _, err := s.outbox.InsertOne(txCtx, visitOutboxDocument{
				ID: visitmodel.VisitEventID(command),
				AggregateID: visitmodel.VisitAggregateID(
					updated.PersonaID, updated.SubjectType, updated.SubjectID,
				),
				EventName:     visitmodel.EventFollowedSubjectVisited,
				PersonaID:     updated.PersonaID,
				SubjectType:   updated.SubjectType,
				SubjectID:     updated.SubjectID,
				LastVisitedAt: updated.LastVisitedAt.UTC(),
				UpdatedAt:     updated.UpdatedAt.UTC(),
				OccurredAt:    updated.UpdatedAt.UTC(),
			}); err != nil && !mongo.IsDuplicateKeyError(err) {
				return nil, fmt.Errorf("append followed subject visit outbox: %w", err)
			}
			result = visitmodel.VisitResult{
				SubjectID:        updated.SubjectID,
				SubjectType:      updated.SubjectType,
				LastVisitedAt:    updated.LastVisitedAt.UTC(),
				HasUnreadChanges: false,
			}
			return nil, nil
		},
	); err != nil {
		return visitmodel.VisitResult{}, err
	}
	return result, nil
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
