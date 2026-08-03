// Package projection 清理 UserAccountClosed 后的 user-service Mongo 派生数据。
package projection

import (
	"context"
	"fmt"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	userevent "quwoquan_service/services/user-service/internal/account/user_account/domain/user/event"
)

// MongoCleanupProjector 的每一步都幂等；任一步失败会让
// UserAccountClosed durable outbox 保持 pending 并重放。
type MongoCleanupProjector struct {
	profileViews *mongo.Collection
}

var _ application.UserEventPublisher = (*MongoCleanupProjector)(nil)

func NewMongoCleanupProjector(db *mongo.Database) *MongoCleanupProjector {
	if db == nil {
		return &MongoCleanupProjector{}
	}
	return &MongoCleanupProjector{
		profileViews: db.Collection("rm_user_profile_view"),
	}
}

func (projector *MongoCleanupProjector) PublishUserEvent(
	ctx context.Context,
	eventType string,
	accountID string,
	_ string,
	_ map[string]any,
) error {
	if eventType != userevent.UserAccountClosed ||
		projector == nil ||
		projector.profileViews == nil {
		return nil
	}
	accountID = strings.TrimSpace(accountID)
	if accountID == "" {
		return nil
	}
	if _, err := projector.profileViews.DeleteOne(
		ctx,
		bson.M{"_id": accountID},
	); err != nil {
		return fmt.Errorf("delete closed account interest projection: %w", err)
	}
	return nil
}
