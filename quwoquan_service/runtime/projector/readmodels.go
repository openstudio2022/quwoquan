package projector

import (
	"context"
	"log/slog"

	"quwoquan_service/runtime/eventstore"
)

// ReadModelStore is the storage-agnostic interface for projector read models.
// Infrastructure implementations (MongoDB, PostgreSQL, etc.) satisfy this
// interface and are injected at composition root.
type ReadModelStore interface {
	Upsert(ctx context.Context, collection string, id string, setFields map[string]any, setOnInsertFields map[string]any) error
	UpdateFields(ctx context.Context, collection string, id string, setFields map[string]any) error
	IncrementField(ctx context.Context, collection string, id string, field string, delta int) error
	IncrementFieldWithSet(ctx context.Context, collection string, id string, field string, delta int, setFields map[string]any) error
	DeleteByID(ctx context.Context, collection string, id string) error
}

// DiscoveryFeedProjector builds the discovery feed read model.
type DiscoveryFeedProjector struct {
	store  ReadModelStore
	logger *slog.Logger
}

func NewDiscoveryFeedProjector(store ReadModelStore, logger *slog.Logger) *DiscoveryFeedProjector {
	return &DiscoveryFeedProjector{store: store, logger: logger}
}

func (p *DiscoveryFeedProjector) Name() string { return "DiscoveryFeedProjector" }

func (p *DiscoveryFeedProjector) EventTypes() []string {
	return []string{"PostCreated", "PostPublished", "PostUpdated", "PostDeleted", "ContentReacted"}
}

func (p *DiscoveryFeedProjector) Project(ctx context.Context, event eventstore.StoredEvent) error {
	switch event.Type {
	case "PostCreated", "PostPublished":
		return p.upsertFeedItem(ctx, event)
	case "PostUpdated":
		return p.updateFeedItem(ctx, event)
	case "PostDeleted":
		return p.removeFeedItem(ctx, event)
	case "ContentReacted":
		return p.updateEngagement(ctx, event)
	default:
		return nil
	}
}

func (p *DiscoveryFeedProjector) upsertFeedItem(ctx context.Context, event eventstore.StoredEvent) error {
	return p.store.Upsert(ctx, "discovery_feed", event.AggregateID,
		map[string]any{
			"postId":      event.AggregateID,
			"authorId":    event.Payload["authorId"],
			"contentType": event.Payload["contentType"],
			"title":       event.Payload["title"],
			"tags":        event.Payload["tags"],
			"publishedAt": event.OccurredAt,
		},
		map[string]any{
			"_id": event.AggregateID,
		},
	)
}

func (p *DiscoveryFeedProjector) updateFeedItem(ctx context.Context, event eventstore.StoredEvent) error {
	set := map[string]any{}
	for _, key := range []string{"title", "tags", "body"} {
		if v, ok := event.Payload[key]; ok {
			set[key] = v
		}
	}
	return p.store.UpdateFields(ctx, "discovery_feed", event.AggregateID, set)
}

func (p *DiscoveryFeedProjector) removeFeedItem(ctx context.Context, event eventstore.StoredEvent) error {
	return p.store.DeleteByID(ctx, "discovery_feed", event.AggregateID)
}

func (p *DiscoveryFeedProjector) updateEngagement(ctx context.Context, event eventstore.StoredEvent) error {
	postID, _ := event.Payload["postId"].(string)
	if postID == "" {
		return nil
	}
	action, _ := event.Payload["action"].(string)
	return p.store.IncrementField(ctx, "discovery_feed", postID, "engagement."+action+"Count", 1)
}

// ChatInboxProjector builds the chat inbox read model.
type ChatInboxProjector struct {
	store  ReadModelStore
	logger *slog.Logger
}

func NewChatInboxProjector(store ReadModelStore, logger *slog.Logger) *ChatInboxProjector {
	return &ChatInboxProjector{store: store, logger: logger}
}

func (p *ChatInboxProjector) Name() string { return "ChatInboxProjector" }

func (p *ChatInboxProjector) EventTypes() []string {
	return []string{"MessageSent", "MessageRead"}
}

func (p *ChatInboxProjector) Project(ctx context.Context, event eventstore.StoredEvent) error {
	switch event.Type {
	case "MessageSent":
		return p.onMessageSent(ctx, event)
	case "MessageRead":
		return p.onMessageRead(ctx, event)
	default:
		return nil
	}
}

func (p *ChatInboxProjector) onMessageSent(ctx context.Context, event eventstore.StoredEvent) error {
	convID, _ := event.Payload["conversationId"].(string)
	if convID == "" {
		return nil
	}
	return p.store.Upsert(ctx, "chat_inbox", convID,
		map[string]any{
			"conversationId":  convID,
			"lastMessageAt":   event.OccurredAt,
			"lastMessageText": event.Payload["content"],
			"lastSenderId":    event.Payload["senderId"],
		},
		map[string]any{
			"_id": convID,
		},
	)
}

func (p *ChatInboxProjector) onMessageRead(ctx context.Context, event eventstore.StoredEvent) error {
	convID, _ := event.Payload["conversationId"].(string)
	if convID == "" {
		return nil
	}
	return p.store.UpdateFields(ctx, "chat_inbox", convID, map[string]any{"unreadCount": 0})
}

// UserProfileViewProjector builds the unified user profile view.
type UserProfileViewProjector struct {
	store  ReadModelStore
	logger *slog.Logger
}

func NewUserProfileViewProjector(store ReadModelStore, logger *slog.Logger) *UserProfileViewProjector {
	return &UserProfileViewProjector{store: store, logger: logger}
}

func (p *UserProfileViewProjector) Name() string { return "UserProfileViewProjector" }

func (p *UserProfileViewProjector) EventTypes() []string {
	return []string{"UserRegistered", "ProfileUpdated", "FollowCreated", "FollowDeleted", "ContentReacted"}
}

func (p *UserProfileViewProjector) Project(ctx context.Context, event eventstore.StoredEvent) error {
	userID := event.Metadata.UserID
	if userID == "" {
		userID, _ = event.Payload["userId"].(string)
	}
	if userID == "" {
		return nil
	}

	switch event.Type {
	case "UserRegistered":
		return p.store.Upsert(ctx, "user_profile_view", userID,
			map[string]any{
				"userId":    userID,
				"nickname":  event.Payload["nickname"],
				"createdAt": event.OccurredAt,
			},
			map[string]any{"_id": userID},
		)
	case "ProfileUpdated":
		set := map[string]any{}
		for _, key := range []string{"nickname", "bio", "avatarUrl", "tags"} {
			if v, ok := event.Payload[key]; ok {
				set[key] = v
			}
		}
		return p.store.UpdateFields(ctx, "user_profile_view", userID, set)
	case "FollowCreated":
		return p.store.IncrementField(ctx, "user_profile_view", userID, "followingCount", 1)
	case "FollowDeleted":
		return p.store.IncrementField(ctx, "user_profile_view", userID, "followingCount", -1)
	case "ContentReacted":
		action, _ := event.Payload["action"].(string)
		if action != "" {
			return p.store.IncrementField(ctx, "user_profile_view", userID, "stats."+action+"Count", 1)
		}
		return nil
	default:
		return nil
	}
}

// RecommendFeatureProjector builds the recommendation feature wide table.
type RecommendFeatureProjector struct {
	store  ReadModelStore
	logger *slog.Logger
}

func NewRecommendFeatureProjector(store ReadModelStore, logger *slog.Logger) *RecommendFeatureProjector {
	return &RecommendFeatureProjector{store: store, logger: logger}
}

func (p *RecommendFeatureProjector) Name() string { return "RecommendFeatureProjector" }

func (p *RecommendFeatureProjector) EventTypes() []string {
	return []string{"PostCreated", "PostPublished", "ContentReacted", "UserTagsUpdated", "ContentViewed"}
}

func (p *RecommendFeatureProjector) Project(ctx context.Context, event eventstore.StoredEvent) error {
	switch event.Type {
	case "PostCreated", "PostPublished":
		return p.store.Upsert(ctx, "recommend_features", event.AggregateID,
			map[string]any{
				"postId":      event.AggregateID,
				"authorId":    event.Payload["authorId"],
				"contentType": event.Payload["contentType"],
				"tags":        event.Payload["tags"],
				"publishedAt": event.OccurredAt,
			},
			map[string]any{
				"_id":          event.AggregateID,
				"viewCount":    0,
				"likeCount":    0,
				"commentCount": 0,
			},
		)
	case "ContentReacted":
		postID, _ := event.Payload["postId"].(string)
		if postID == "" {
			return nil
		}
		action, _ := event.Payload["action"].(string)
		return p.store.IncrementFieldWithSet(ctx, "recommend_features", postID, action+"Count", 1, nil)
	case "ContentViewed":
		postID, _ := event.Payload["postId"].(string)
		if postID == "" {
			return nil
		}
		return p.store.IncrementField(ctx, "recommend_features", postID, "viewCount", 1)
	default:
		return nil
	}
}
