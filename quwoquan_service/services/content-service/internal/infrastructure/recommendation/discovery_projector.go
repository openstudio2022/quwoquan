package recommendation

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

// DiscoveryFeedProjector maintains the rm_discovery_feed read model.
// Source events: PostCreated, PostPublished, ContentReacted, BehaviorBatchReported.
// Aligned with contracts/metadata/_projections/discovery_feed.yaml.
type DiscoveryFeedProjector struct {
	coll *mongo.Collection
}

func NewDiscoveryFeedProjector(db *mongo.Database) *DiscoveryFeedProjector {
	return &DiscoveryFeedProjector{coll: db.Collection("rm_discovery_feed")}
}

func (p *DiscoveryFeedProjector) Name() string { return "DiscoveryFeedProjector" }

func (p *DiscoveryFeedProjector) EventTypes() []string {
	return []string{"PostCreated", "PostPublished", "ContentReacted", "BehaviorBatchReported"}
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
	case "PostCreated":
		return p.onPostCreated(ctx, event)
	case "PostPublished":
		return p.onPostPublished(ctx, event)
	case "ContentReacted":
		return p.onContentReacted(ctx, event)
	case "BehaviorBatchReported":
		return p.onBehaviorReported(ctx, event)
	default:
		return nil
	}
}

func (p *DiscoveryFeedProjector) onPostCreated(ctx context.Context, event ProjectorEvent) error {
	postID := strVal(event.Payload, "_id")
	if postID == "" {
		return nil
	}

	doc := bson.M{
		"$set": bson.M{
			"postId":      postID,
			"contentType": strVal(event.Payload, "contentType"),
			"authorId":    strVal(event.Payload, "authorId"),
			"title":       strVal(event.Payload, "title"),
			"tags":        anySlice(event.Payload, "tags"),
			"coverUrl":    strVal(event.Payload, "coverUrl"),
			"publishedAt": event.OccurredAt,
			"recScore":    0.0,
		},
		"$setOnInsert": bson.M{
			"likeCount":     int64(0),
			"commentCount":  int64(0),
			"favoriteCount": int64(0),
			"viewCount":     int64(0),
		},
	}

	opts := options.UpdateOne().SetUpsert(true)
	_, err := p.coll.UpdateOne(ctx, bson.M{"postId": postID}, doc, opts)
	return err
}

func (p *DiscoveryFeedProjector) onPostPublished(ctx context.Context, event ProjectorEvent) error {
	postID := strVal(event.Payload, "_id")
	if postID == "" {
		return nil
	}

	update := bson.M{
		"$set": bson.M{
			"publishedAt": event.OccurredAt,
		},
	}
	_, err := p.coll.UpdateOne(ctx, bson.M{"postId": postID}, update)
	return err
}

func (p *DiscoveryFeedProjector) onContentReacted(ctx context.Context, event ProjectorEvent) error {
	postID := strVal(event.Payload, "postId")
	if postID == "" {
		return nil
	}

	inc := bson.M{}
	if boolVal(event.Payload, "liked") {
		inc["likeCount"] = int64(1)
	}
	if boolVal(event.Payload, "favorited") {
		inc["favoriteCount"] = int64(1)
	}

	if len(inc) == 0 {
		return nil
	}
	_, err := p.coll.UpdateOne(ctx, bson.M{"postId": postID}, bson.M{"$inc": inc})
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
		case "like":
			inc["likeCount"] = int64(1)
		case "favorite":
			inc["favoriteCount"] = int64(1)
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
