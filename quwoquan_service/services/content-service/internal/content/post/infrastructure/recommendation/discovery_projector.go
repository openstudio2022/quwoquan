package recommendation

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	postevent "quwoquan_service/services/content-service/internal/content/post/domain/event"
)

// DiscoveryFeedProjector maintains the rm_discovery_feed read model.
// Source events: Post lifecycle and BehaviorBatchReported. ContentReaction uses
// its own aggregate outbox + exact-count projector and must not enter this delta path.
// Aligned with contracts/metadata/_projections/discovery_feed.yaml.
type DiscoveryFeedProjector struct {
	coll  *mongo.Collection
	posts *mongo.Collection
}

func NewDiscoveryFeedProjector(db *mongo.Database) *DiscoveryFeedProjector {
	return &DiscoveryFeedProjector{
		coll:  db.Collection("rm_discovery_feed"),
		posts: db.Collection("posts"),
	}
}

func (p *DiscoveryFeedProjector) Name() string { return "DiscoveryFeedProjector" }

func (p *DiscoveryFeedProjector) EventTypes() []string {
	return []string{
		postevent.PostPublished,
		postevent.PostSettingsUpdated,
		postevent.PostPromotedToWork,
		postevent.PostDeleted,
		"BehaviorBatchReported",
	}
}

// ProjectorEvent mirrors the event structure from runtime/projector.
type ProjectorEvent struct {
	ID            string         `json:"id"`
	Type          string         `json:"type"`
	AggregateType string         `json:"aggregateType"`
	AggregateID   string         `json:"aggregateId"`
	Payload       map[string]any `json:"payload"`
	OccurredAt    time.Time      `json:"occurredAt"`
}

func (p *DiscoveryFeedProjector) Project(ctx context.Context, event ProjectorEvent) error {
	switch event.Type {
	case postevent.PostPublished:
		return p.onPostPublished(ctx, event)
	case postevent.PostSettingsUpdated:
		return p.onPostSettingsUpdated(ctx, event)
	case postevent.PostPromotedToWork:
		return p.onPostPromotedToWork(ctx, event)
	case postevent.PostDeleted:
		return p.onPostDeleted(ctx, event)
	case "BehaviorBatchReported":
		return p.onBehaviorReported(ctx, event)
	default:
		return nil
	}
}

func (p *DiscoveryFeedProjector) onPostPublished(ctx context.Context, event ProjectorEvent) error {
	return p.syncPost(ctx, event)
}

func (p *DiscoveryFeedProjector) onPostSettingsUpdated(ctx context.Context, event ProjectorEvent) error {
	return p.syncPost(ctx, event)
}

func (p *DiscoveryFeedProjector) onPostPromotedToWork(ctx context.Context, event ProjectorEvent) error {
	return p.syncPost(ctx, event)
}

func (p *DiscoveryFeedProjector) onPostDeleted(ctx context.Context, event ProjectorEvent) error {
	postID := StrVal(event.Payload, "postId")
	if postID == "" {
		return nil
	}
	_, err := p.coll.DeleteOne(ctx, bson.M{"postId": postID})
	return err
}

func (p *DiscoveryFeedProjector) syncPost(ctx context.Context, event ProjectorEvent) error {
	postID := StrVal(event.Payload, "postId")
	if postID == "" {
		return nil
	}
	if !eligibleForDiscovery(event.Payload) {
		_, err := p.coll.DeleteOne(ctx, bson.M{"postId": postID})
		return err
	}

	set := bson.M{
		"postId":               postID,
		"authorId":             StrVal(event.Payload, "authorId"),
		"creatorProfileId":     StrVal(event.Payload, "creatorProfileId"),
		"creatorDisclosure":    anyMap(event.Payload, "creatorDisclosure"),
		"experienceClaimMode":  StrVal(event.Payload, "experienceClaimMode"),
		"authorQualitySignals": anyMap(event.Payload, "authorQualitySignals"),
		"contentType":          StrVal(event.Payload, "contentType"),
		"contentIdentity":      StrVal(event.Payload, "contentIdentity"),
		"title":                StrVal(event.Payload, "title"),
		"tagRefs":              AnySlice(event.Payload, "tagRefs"),
		"coverUrl":             StrVal(event.Payload, "coverUrl"),
		"thumbnailUrl":         StrVal(event.Payload, "thumbnailUrl"),
		"videoUrl":             StrVal(event.Payload, "videoUrl"),
		"coverStrategy":        StrVal(event.Payload, "coverStrategy"),
		"coverFrameTimeMs":     int64Val(event.Payload, "coverFrameTimeMs"),
		"durationMs":           int64Val(event.Payload, "durationMs"),
		"width":                int64Val(event.Payload, "width"),
		"height":               int64Val(event.Payload, "height"),
		"mediaItems":           event.Payload["mediaItems"],
		"status":               normalizedStatus(event.Payload),
		"visibility":           normalizeVisibility(StrVal(event.Payload, "visibility")),
		"assistantUsePolicy":   StrVal(event.Payload, "assistantUsePolicy"),
		"entityRefs":           AnySlice(event.Payload, "entityRefs"),
		"semanticMentions":     event.Payload["semanticMentions"],
		"contentVertical":      StrVal(event.Payload, "contentVertical"),
		"sourceTaskId":         StrVal(event.Payload, "sourceTaskId"),
		// conditionProfile 为实体级画像：在线 Post 事件 payload 暂不携带，
		// 由绑定实体（canonicalEntityId→entity.conditionProfile）派生后注入；冷启动 cmd/import 路径直接冗余。
		"conditionProfile": anyMap(event.Payload, "conditionProfile"),
	}
	for key, value := range BuildRecommendationProjectionFields(set) {
		set[key] = value
	}
	setOnInsert := bson.M{
		"likeCount":    int64(0),
		"commentCount": int64(0),
		"shareCount":   int64(0),
		"viewCount":    int64(0),
	}
	// 时间语义：createdAt 仅首次插入置位（来自 Post.CreatedAt，永不被后续事件覆盖）；
	// publishedAt 由首次发布事件携带（PostPublished 仅触发一次，值来自 set-once 的 Post.PublishedAt）；
	// updatedAt 随每次内容事件单调推进。feed 卡片据此展示「创作 vs 更新」。
	if publishedAt := parseEventTime(StrVal(event.Payload, "publishedAt"), event.OccurredAt); !publishedAt.IsZero() {
		set["publishedAt"] = publishedAt
	}
	if createdAt := parseEventTime(StrVal(event.Payload, "createdAt"), event.OccurredAt); !createdAt.IsZero() {
		setOnInsert["createdAt"] = createdAt
	}
	if updatedAt := parseEventTime(StrVal(event.Payload, "updatedAt"), event.OccurredAt); !updatedAt.IsZero() {
		set["updatedAt"] = updatedAt
	}

	update := bson.M{
		"$set":         set,
		"$setOnInsert": setOnInsert,
	}
	opts := options.UpdateOne().SetUpsert(true)
	_, err := p.coll.UpdateOne(ctx, bson.M{"postId": postID}, update, opts)
	return err
}

func (p *DiscoveryFeedProjector) onBehaviorReported(ctx context.Context, event ProjectorEvent) error {
	// BehaviorPayloadEvents 同时接受 []any（wire 解码）与 []map[string]any
	// （进程内 relay 直连），避免类型不匹配静默 no-op。
	events := BehaviorPayloadEvents(event.Payload["events"])
	if len(events) == 0 {
		return nil
	}
	if strings.TrimSpace(event.ID) == "" {
		return fmt.Errorf("BehaviorBatchReported requires a projection event id")
	}

	deltas := map[string]int64{}
	for _, ev := range events {
		contentID, _ := ev["contentId"].(string)
		if contentID == "" {
			continue
		}
		if delta := BehaviorViewCountDelta(ev); delta > 0 {
			deltas[contentID] += delta
		}
	}
	for contentID, delta := range deltas {
		filter := bson.M{
			"postId": contentID,
			"$or": []bson.M{
				{"behaviorProjectionLastId": bson.M{"$exists": false}},
				{"behaviorProjectionLastId": bson.M{"$lt": event.ID}},
			},
		}
		result, err := p.coll.UpdateOne(
			ctx,
			filter,
			bson.M{
				"$inc": bson.M{"viewCount": delta},
				"$set": bson.M{"behaviorProjectionLastId": event.ID},
			},
		)
		if err != nil {
			return fmt.Errorf("increment DiscoveryFeed viewCount for %q: %w", contentID, err)
		}
		if result.MatchedCount > 0 {
			continue
		}
		// 文档存在但水位不小于当前事件，说明是 checkpoint 重放，计数已落。
		existing, countErr := p.coll.CountDocuments(
			ctx,
			bson.M{"postId": contentID},
			options.Count().SetLimit(1),
		)
		if countErr != nil {
			return fmt.Errorf("check DiscoveryFeed replay for %q: %w", contentID, countErr)
		}
		if existing > 0 {
			continue
		}
		eligible, countErr := p.posts.CountDocuments(
			ctx,
			DiscoveryFeedEligibleSourceFilter(contentID),
			options.Count().SetLimit(1),
		)
		if countErr != nil {
			return fmt.Errorf("check DiscoveryFeed source post %q: %w", contentID, countErr)
		}
		if eligible > 0 {
			// Post 与行为 relay 有独立 checkpoint：公开已发布内容的 feed row
			// 尚未建立时必须失败重试，不能推进游标永久丢掉 viewCount。
			return fmt.Errorf("DiscoveryFeed viewCount target %q is missing", contentID)
		}
	}
	return nil
}

func DiscoveryFeedEligibleSourceFilter(contentID string) bson.M {
	return bson.M{
		"_id":              contentID,
		"status":           "published",
		"visibility":       "public",
		"moderationStatus": "approved",
	}
}

func BehaviorViewCountDelta(event map[string]any) int64 {
	action := strings.ToLower(strings.TrimSpace(StrVal(event, "action")))
	if action != "impression" {
		return 0
	}
	// 七态漏斗中 visible 只是进入视窗的弱证据；只有满足面积+停留门槛的
	// impressed 才是 viewCount。行为入口已强校验 state，缺失状态不得兼容计数。
	switch strings.ToLower(strings.TrimSpace(StrVal(event, "state"))) {
	case "impressed":
		return 1
	default:
		return 0
	}
}

func StrVal(m map[string]any, key string) string {
	v, _ := m[key].(string)
	return v
}

func boolVal(m map[string]any, key string) bool {
	v, _ := m[key].(bool)
	return v
}

func int64Val(m map[string]any, key string) int64 {
	switch v := m[key].(type) {
	case int:
		return int64(v)
	case int32:
		return int64(v)
	case int64:
		return v
	case float32:
		return int64(v)
	case float64:
		return int64(v)
	default:
		return 0
	}
}

func normalizedStatus(payload map[string]any) string {
	if status := strings.TrimSpace(strings.ToLower(StrVal(payload, "status"))); status != "" {
		return status
	}
	return "published"
}

func normalizeVisibility(value string) string {
	normalized := strings.TrimSpace(strings.ToLower(value))
	switch normalized {
	case "", "public":
		return "public"
	case "private":
		return "private"
	default:
		return normalized
	}
}

func eligibleForDiscovery(payload map[string]any) bool {
	return normalizedStatus(payload) == "published" &&
		normalizeVisibility(StrVal(payload, "visibility")) == "public" &&
		strings.EqualFold(strings.TrimSpace(StrVal(payload, "moderationStatus")), "approved")
}

func parseEventTime(raw string, fallback time.Time) time.Time {
	raw = strings.TrimSpace(raw)
	if raw != "" {
		if ts, err := time.Parse(time.RFC3339, raw); err == nil {
			return ts
		}
	}
	if fallback.IsZero() {
		return time.Time{}
	}
	return fallback.UTC()
}

func anyMap(m map[string]any, key string) map[string]any {
	if v, ok := m[key].(map[string]any); ok {
		return v
	}
	return nil
}

func AnySlice(m map[string]any, key string) []string {
	raw, ok := m[key].([]any)
	if !ok {
		if ss, ok := m[key].([]string); ok {
			return ss
		}
		return nil
	}
	out := make([]string, 0, len(raw))
	for _, item := range raw {
		if s, ok := item.(string); ok {
			out = append(out, s)
		}
	}
	return out
}
