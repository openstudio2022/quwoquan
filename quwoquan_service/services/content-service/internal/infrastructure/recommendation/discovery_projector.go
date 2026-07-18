package recommendation

import (
	"context"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	postevent "quwoquan_service/services/content-service/internal/domain/post/event"
)

// DiscoveryFeedProjector maintains the rm_discovery_feed read model.
// Source events: Post lifecycle and BehaviorBatchReported. ContentReaction uses
// its own aggregate outbox + exact-count projector and must not enter this delta path.
// Aligned with contracts/metadata/_projections/discovery_feed.yaml.
type DiscoveryFeedProjector struct {
	coll *mongo.Collection
}

func NewDiscoveryFeedProjector(db *mongo.Database) *DiscoveryFeedProjector {
	return &DiscoveryFeedProjector{coll: db.Collection("rm_discovery_feed")}
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
	postID := strVal(event.Payload, "postId")
	if postID == "" {
		return nil
	}
	_, err := p.coll.DeleteOne(ctx, bson.M{"postId": postID})
	return err
}

func (p *DiscoveryFeedProjector) syncPost(ctx context.Context, event ProjectorEvent) error {
	postID := strVal(event.Payload, "postId")
	if postID == "" {
		return nil
	}
	if !eligibleForDiscovery(event.Payload) {
		_, err := p.coll.DeleteOne(ctx, bson.M{"postId": postID})
		return err
	}

	set := bson.M{
		"postId":               postID,
		"authorId":             strVal(event.Payload, "authorId"),
		"creatorProfileId":     strVal(event.Payload, "creatorProfileId"),
		"creatorDisclosure":    anyMap(event.Payload, "creatorDisclosure"),
		"experienceClaimMode":  strVal(event.Payload, "experienceClaimMode"),
		"authorQualitySignals": anyMap(event.Payload, "authorQualitySignals"),
		"contentType":          strVal(event.Payload, "contentType"),
		"contentIdentity":      strVal(event.Payload, "contentIdentity"),
		"title":                strVal(event.Payload, "title"),
		"tagRefs":              anySlice(event.Payload, "tagRefs"),
		"coverUrl":             strVal(event.Payload, "coverUrl"),
		"thumbnailUrl":         strVal(event.Payload, "thumbnailUrl"),
		"videoUrl":             strVal(event.Payload, "videoUrl"),
		"coverStrategy":        strVal(event.Payload, "coverStrategy"),
		"coverFrameTimeMs":     int64Val(event.Payload, "coverFrameTimeMs"),
		"durationMs":           int64Val(event.Payload, "durationMs"),
		"width":                int64Val(event.Payload, "width"),
		"height":               int64Val(event.Payload, "height"),
		"mediaItems":           event.Payload["mediaItems"],
		"status":               normalizedStatus(event.Payload),
		"visibility":           normalizeVisibility(strVal(event.Payload, "visibility")),
		"assistantUsePolicy":   strVal(event.Payload, "assistantUsePolicy"),
		"entityRefs":           anySlice(event.Payload, "entityRefs"),
		"semanticMentions":     event.Payload["semanticMentions"],
		"contentVertical":      strVal(event.Payload, "contentVertical"),
		"sourceTaskId":         strVal(event.Payload, "sourceTaskId"),
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
		"viewCount":    int64(0),
	}
	// 时间语义：createdAt 仅首次插入置位（来自 Post.CreatedAt，永不被后续事件覆盖）；
	// publishedAt 由首次发布事件携带（PostPublished 仅触发一次，值来自 set-once 的 Post.PublishedAt）；
	// updatedAt 随每次内容事件单调推进。feed 卡片据此展示「创作 vs 更新」。
	if publishedAt := parseEventTime(strVal(event.Payload, "publishedAt"), event.OccurredAt); !publishedAt.IsZero() {
		set["publishedAt"] = publishedAt
	}
	if createdAt := parseEventTime(strVal(event.Payload, "createdAt"), event.OccurredAt); !createdAt.IsZero() {
		setOnInsert["createdAt"] = createdAt
	}
	if updatedAt := parseEventTime(strVal(event.Payload, "updatedAt"), event.OccurredAt); !updatedAt.IsZero() {
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
	events, ok := event.Payload["events"].([]any)
	if !ok || len(events) == 0 {
		return nil
	}

	for _, raw := range events {
		ev, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		action, _ := ev["action"].(string)
		contentID, _ := ev["contentId"].(string)
		if contentID == "" {
			continue
		}

		inc := bson.M{}
		switch action {
		case "impression":
			inc["viewCount"] = int64(1)
		}

		if len(inc) > 0 {
			_, _ = p.coll.UpdateOne(ctx, bson.M{"postId": contentID}, bson.M{"$inc": inc})
		}
	}
	return nil
}

func strVal(m map[string]any, key string) string {
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
	if status := strings.TrimSpace(strings.ToLower(strVal(payload, "status"))); status != "" {
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
		normalizeVisibility(strVal(payload, "visibility")) == "public"
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

func anySlice(m map[string]any, key string) []string {
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
