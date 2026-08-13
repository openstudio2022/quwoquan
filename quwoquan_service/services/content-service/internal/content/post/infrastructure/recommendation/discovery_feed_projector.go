package recommendation

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	postevent "quwoquan_service/services/content-service/generated/content/post/contract/event"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
)

// DiscoveryFeedProjector 将在线 Post 生命周期事实投影到 rm_discovery_feed。
//
// canonical release importer 与在线发布链路共享同一个 ReadModel；前者负责不可变
// 运营供给，后者负责用户实时发布。该 projector 由独立 outbox relay 驱动，失败时
// 不推进自身 checkpoint，也不回滚已经提交的 Post。
type DiscoveryFeedProjector struct {
	collection *mongo.Collection
}

func NewDiscoveryFeedProjector(db *mongo.Database) *DiscoveryFeedProjector {
	if db == nil {
		return &DiscoveryFeedProjector{}
	}
	return &DiscoveryFeedProjector{
		collection: db.Collection("rm_discovery_feed"),
	}
}

func (p *DiscoveryFeedProjector) Project(
	ctx context.Context,
	event ports.ProjectorEvent,
) error {
	if p == nil || p.collection == nil {
		return fmt.Errorf("discovery feed projector is not configured")
	}
	postID := strings.TrimSpace(event.AggregateID)
	if payloadID := strings.TrimSpace(stringValue(event.Payload["postId"])); payloadID != "" {
		postID = payloadID
	}
	if postID == "" {
		return fmt.Errorf("discovery feed event has no post id")
	}

	switch event.Type {
	case postevent.PostDeleted,
		postevent.PostPrivacyRedacted,
		postevent.PostPurged,
		postevent.PostModerationRejected:
		return p.remove(ctx, postID)
	case postevent.PostPublished,
		postevent.PostUpdated,
		postevent.PostSettingsUpdated,
		postevent.PostPromotedToWork,
		postevent.PostImported:
		return p.reconcile(ctx, postID, event.Payload)
	default:
		return nil
	}
}

func (p *DiscoveryFeedProjector) reconcile(
	ctx context.Context,
	postID string,
	payload map[string]any,
) error {
	if !discoveryFeedEligible(payload) {
		return p.remove(ctx, postID)
	}
	set := make(bson.M, len(payload)+8)
	for key, value := range payload {
		if key == "_id" {
			continue
		}
		set[key] = value
	}
	set["postId"] = postID
	normalizeProjectionTimes(set)
	for key, value := range BuildRecommendationProjectionFields(set) {
		set[key] = value
	}
	_, err := p.collection.UpdateOne(
		ctx,
		bson.M{"postId": postID},
		bson.M{
			"$set": set,
			"$setOnInsert": bson.M{
				"viewCount": int64(0),
			},
		},
		options.UpdateOne().SetUpsert(true),
	)
	if err != nil {
		return fmt.Errorf("upsert discovery feed post %s: %w", postID, err)
	}
	return nil
}

func (p *DiscoveryFeedProjector) remove(ctx context.Context, postID string) error {
	if _, err := p.collection.DeleteOne(ctx, bson.M{"postId": postID}); err != nil {
		return fmt.Errorf("delete discovery feed post %s: %w", postID, err)
	}
	return nil
}

func discoveryFeedEligible(payload map[string]any) bool {
	return strings.EqualFold(strings.TrimSpace(stringValue(payload["status"])), "published") &&
		strings.EqualFold(strings.TrimSpace(stringValue(payload["visibility"])), "public") &&
		strings.EqualFold(strings.TrimSpace(stringValue(payload["moderationStatus"])), "approved")
}

func normalizeProjectionTimes(set bson.M) {
	for _, key := range []string{"publishedAt", "createdAt", "updatedAt", "visitedAt"} {
		raw, ok := set[key].(string)
		if !ok {
			continue
		}
		raw = strings.TrimSpace(raw)
		if raw == "" {
			delete(set, key)
			continue
		}
		if parsed, err := time.Parse(time.RFC3339Nano, raw); err == nil {
			set[key] = parsed.UTC()
		}
	}
}

func stringValue(value any) string {
	switch typed := value.(type) {
	case string:
		return typed
	case fmt.Stringer:
		return typed.String()
	default:
		return ""
	}
}

var _ ports.Projector = (*DiscoveryFeedProjector)(nil)
