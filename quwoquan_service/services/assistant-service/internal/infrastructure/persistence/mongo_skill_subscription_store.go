package persistence

import (
	"context"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type MongoSkillSubscriptionStore struct {
	coll *mongo.Collection
}

func NewMongoSkillSubscriptionStore(db *mongo.Database) *MongoSkillSubscriptionStore {
	return &MongoSkillSubscriptionStore{coll: db.Collection("skill_subscriptions")}
}

func (s *MongoSkillSubscriptionStore) EnsureIndexes(ctx context.Context) error {
	indexes := []mongo.IndexModel{
		{Keys: bson.D{{Key: "owner.ownerId", Value: 1}, {Key: "status", Value: 1}, {Key: "updatedAt", Value: -1}}, Options: options.Index().SetName("idx_skill_subscriptions_owner_status")},
		{Keys: bson.D{{Key: "status", Value: 1}, {Key: "updatedAt", Value: -1}}, Options: options.Index().SetName("idx_skill_subscriptions_status_updated")},
		{Keys: bson.D{{Key: "status", Value: 1}, {Key: "trigger.type", Value: 1}}, Options: options.Index().SetName("idx_skill_subscriptions_trigger")},
		{
			Keys: bson.D{{Key: "owner.ownerId", Value: 1}, {Key: "clientRequestId", Value: 1}},
			Options: options.Index().
				SetName("uq_skill_subscriptions_client_request").
				SetUnique(true).
				SetPartialFilterExpression(bson.M{"clientRequestId": bson.M{"$type": "string"}}),
		},
	}
	if _, err := s.coll.Indexes().CreateMany(ctx, indexes); err != nil {
		return fmt.Errorf("create skill subscription indexes: %w", err)
	}
	return nil
}

// CreateSkillSubscription 为一次创建：clientRequestId 唯一约束承载幂等，
// 重放返回首个已创建订阅。
func (s *MongoSkillSubscriptionStore) CreateSkillSubscription(ctx context.Context, subscription assistant.SkillSubscription) (assistant.SkillSubscription, error) {
	if _, err := s.coll.InsertOne(ctx, subscription); err != nil {
		if mongo.IsDuplicateKeyError(err) && subscription.ClientRequestID != "" {
			var existing assistant.SkillSubscription
			findErr := s.coll.FindOne(ctx, bson.M{
				"owner.ownerId":   subscription.Owner.OwnerID,
				"clientRequestId": subscription.ClientRequestID,
			}).Decode(&existing)
			if findErr == nil {
				return existing, nil
			}
		}
		return assistant.SkillSubscription{}, rterr.NewUnavailable(rterr.ModuleAssistant, "写入订阅失败", err.Error())
	}
	return subscription, nil
}

func (s *MongoSkillSubscriptionStore) UpsertSkillSubscription(ctx context.Context, subscription assistant.SkillSubscription) (assistant.SkillSubscription, error) {
	var item assistant.SkillSubscription
	err := s.coll.FindOneAndUpdate(
		ctx,
		bson.M{"_id": subscription.SubscriptionID},
		bson.M{
			"$set": bson.M{
				"owner":           subscription.Owner,
				"createdByUserId": subscription.CreatedByUserID,
				"skillId":         subscription.SkillID,
				"domainId":        subscription.DomainID,
				"tagRefs":         subscription.TagRefs,
				"status":          subscription.Status,
				"searchQueryPlan": subscription.SearchQueryPlan,
				"trigger":         subscription.Trigger,
				"destination":     subscription.Destination,
				"updatedAt":       subscription.UpdatedAt,
			},
			"$setOnInsert": bson.M{
				"createdAt": subscription.CreatedAt,
			},
		},
		options.FindOneAndUpdate().
			SetUpsert(true).
			SetReturnDocument(options.After),
	).Decode(&item)
	if err != nil {
		return assistant.SkillSubscription{}, rterr.NewUnavailable(rterr.ModuleAssistant, "写入订阅失败", err.Error())
	}
	return item, nil
}

func (s *MongoSkillSubscriptionStore) GetSkillSubscription(ctx context.Context, userID, subscriptionID string) (assistant.SkillSubscription, error) {
	var item assistant.SkillSubscription
	err := s.coll.FindOne(ctx, bson.M{"_id": subscriptionID, "owner.ownerId": userID}).Decode(&item)
	if err != nil {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "订阅不存在", "skill subscription not found")
	}
	return item, nil
}

func (s *MongoSkillSubscriptionStore) ListSkillSubscriptions(ctx context.Context, userID, status string, limit int) ([]assistant.SkillSubscription, error) {
	filter := bson.M{}
	if userID != "" {
		filter["owner.ownerId"] = userID
	}
	if status != "" {
		filter["status"] = status
	} else {
		filter["status"] = bson.M{"$ne": assistant.SkillSubscriptionStatusArchived}
	}
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	cur, err := s.coll.Find(ctx, filter, options.Find().SetSort(bson.D{{Key: "updatedAt", Value: -1}}).SetLimit(int64(limit)))
	if err != nil {
		return nil, rterr.NewUnavailable(rterr.ModuleAssistant, "读取订阅失败", err.Error())
	}
	defer cur.Close(ctx)
	items := []assistant.SkillSubscription{}
	if err := cur.All(ctx, &items); err != nil {
		return nil, rterr.NewUnavailable(rterr.ModuleAssistant, "解析订阅失败", err.Error())
	}
	return items, nil
}

// UpdateSkillSubscriptionStatus 是收敛的 set 语义：目标状态已满足时 no-op
// 返回存量（不推进 updatedAt、不制造伪变更）。
func (s *MongoSkillSubscriptionStore) UpdateSkillSubscriptionStatus(ctx context.Context, userID, subscriptionID, status string, updatedAt time.Time) (assistant.SkillSubscription, error) {
	var item assistant.SkillSubscription
	err := s.coll.FindOneAndUpdate(
		ctx,
		bson.M{"_id": subscriptionID, "owner.ownerId": userID, "status": bson.M{"$ne": status}},
		bson.M{"$set": bson.M{"status": status, "updatedAt": updatedAt}},
		options.FindOneAndUpdate().SetReturnDocument(options.After),
	).Decode(&item)
	if err == nil {
		return item, nil
	}
	// 未匹配：订阅不存在，或目标状态已满足（no-op 读回存量）。
	findErr := s.coll.FindOne(ctx, bson.M{"_id": subscriptionID, "owner.ownerId": userID}).Decode(&item)
	if findErr != nil {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "订阅不存在", "skill subscription not found")
	}
	return item, nil
}
