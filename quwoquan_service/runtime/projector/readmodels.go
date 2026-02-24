package projector

import (
	"context"
	"log/slog"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/eventstore"
)

// DiscoveryFeedProjector builds the discovery feed read model.
type DiscoveryFeedProjector struct {
	coll   *mongo.Collection
	logger *slog.Logger
}

func NewDiscoveryFeedProjector(db *mongo.Database, logger *slog.Logger) *DiscoveryFeedProjector {
	return &DiscoveryFeedProjector{
		coll:   db.Collection("discovery_feed"),
		logger: logger,
	}
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
	postID := event.AggregateID
	doc := bson.M{
		"$set": bson.M{
			"postId":      postID,
			"authorId":    event.Payload["authorId"],
			"contentType": event.Payload["contentType"],
			"title":       event.Payload["title"],
			"tags":        event.Payload["tags"],
			"publishedAt": event.OccurredAt,
			"updatedAt":   time.Now().UTC(),
		},
		"$setOnInsert": bson.M{
			"_id":       postID,
			"createdAt": time.Now().UTC(),
		},
	}
	opts := options.UpdateOne().SetUpsert(true)
	_, err := p.coll.UpdateOne(ctx, bson.M{"_id": postID}, doc, opts)
	return err
}

func (p *DiscoveryFeedProjector) updateFeedItem(ctx context.Context, event eventstore.StoredEvent) error {
	set := bson.M{"updatedAt": time.Now().UTC()}
	for _, key := range []string{"title", "tags", "body"} {
		if v, ok := event.Payload[key]; ok {
			set[key] = v
		}
	}
	_, err := p.coll.UpdateOne(ctx, bson.M{"_id": event.AggregateID}, bson.M{"$set": set})
	return err
}

func (p *DiscoveryFeedProjector) removeFeedItem(ctx context.Context, event eventstore.StoredEvent) error {
	_, err := p.coll.DeleteOne(ctx, bson.M{"_id": event.AggregateID})
	return err
}

func (p *DiscoveryFeedProjector) updateEngagement(ctx context.Context, event eventstore.StoredEvent) error {
	postID, _ := event.Payload["postId"].(string)
	if postID == "" {
		return nil
	}
	action, _ := event.Payload["action"].(string)
	field := "engagement." + action + "Count"
	_, err := p.coll.UpdateOne(ctx,
		bson.M{"_id": postID},
		bson.M{"$inc": bson.M{field: 1}},
	)
	return err
}

// ChatInboxProjector builds the chat inbox read model.
type ChatInboxProjector struct {
	coll   *mongo.Collection
	logger *slog.Logger
}

func NewChatInboxProjector(db *mongo.Database, logger *slog.Logger) *ChatInboxProjector {
	return &ChatInboxProjector{
		coll:   db.Collection("chat_inbox"),
		logger: logger,
	}
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

	doc := bson.M{
		"$set": bson.M{
			"conversationId":  convID,
			"lastMessageAt":   event.OccurredAt,
			"lastMessageText": event.Payload["content"],
			"lastSenderId":    event.Payload["senderId"],
		},
		"$inc": bson.M{
			"unreadCount": 1,
		},
		"$setOnInsert": bson.M{
			"_id":       convID,
			"createdAt": time.Now().UTC(),
		},
	}
	opts := options.UpdateOne().SetUpsert(true)
	_, err := p.coll.UpdateOne(ctx, bson.M{"_id": convID}, doc, opts)
	return err
}

func (p *ChatInboxProjector) onMessageRead(ctx context.Context, event eventstore.StoredEvent) error {
	convID, _ := event.Payload["conversationId"].(string)
	if convID == "" {
		return nil
	}
	_, err := p.coll.UpdateOne(ctx,
		bson.M{"_id": convID},
		bson.M{"$set": bson.M{"unreadCount": 0}},
	)
	return err
}

// UserProfileViewProjector builds the unified user profile view.
type UserProfileViewProjector struct {
	coll   *mongo.Collection
	logger *slog.Logger
}

func NewUserProfileViewProjector(db *mongo.Database, logger *slog.Logger) *UserProfileViewProjector {
	return &UserProfileViewProjector{
		coll:   db.Collection("user_profile_view"),
		logger: logger,
	}
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
		doc := bson.M{
			"$set": bson.M{
				"userId":    userID,
				"nickname":  event.Payload["nickname"],
				"createdAt": event.OccurredAt,
			},
			"$setOnInsert": bson.M{"_id": userID},
		}
		opts := options.UpdateOne().SetUpsert(true)
		_, err := p.coll.UpdateOne(ctx, bson.M{"_id": userID}, doc, opts)
		return err

	case "ProfileUpdated":
		set := bson.M{"updatedAt": time.Now().UTC()}
		for _, key := range []string{"nickname", "bio", "avatarUrl", "tags"} {
			if v, ok := event.Payload[key]; ok {
				set[key] = v
			}
		}
		_, err := p.coll.UpdateOne(ctx, bson.M{"_id": userID}, bson.M{"$set": set})
		return err

	case "FollowCreated":
		_, err := p.coll.UpdateOne(ctx, bson.M{"_id": userID}, bson.M{"$inc": bson.M{"followingCount": 1}})
		return err

	case "FollowDeleted":
		_, err := p.coll.UpdateOne(ctx, bson.M{"_id": userID}, bson.M{"$inc": bson.M{"followingCount": -1}})
		return err

	case "ContentReacted":
		action, _ := event.Payload["action"].(string)
		if action != "" {
			field := "stats." + action + "Count"
			_, err := p.coll.UpdateOne(ctx, bson.M{"_id": userID}, bson.M{"$inc": bson.M{field: 1}})
			return err
		}
		return nil

	default:
		return nil
	}
}

// RecommendFeatureProjector builds the recommendation feature wide table.
type RecommendFeatureProjector struct {
	coll   *mongo.Collection
	logger *slog.Logger
}

func NewRecommendFeatureProjector(db *mongo.Database, logger *slog.Logger) *RecommendFeatureProjector {
	return &RecommendFeatureProjector{
		coll:   db.Collection("recommend_features"),
		logger: logger,
	}
}

func (p *RecommendFeatureProjector) Name() string { return "RecommendFeatureProjector" }

func (p *RecommendFeatureProjector) EventTypes() []string {
	return []string{"PostCreated", "PostPublished", "ContentReacted", "UserTagsUpdated", "ContentViewed"}
}

func (p *RecommendFeatureProjector) Project(ctx context.Context, event eventstore.StoredEvent) error {
	switch event.Type {
	case "PostCreated", "PostPublished":
		postID := event.AggregateID
		doc := bson.M{
			"$set": bson.M{
				"postId":      postID,
				"authorId":    event.Payload["authorId"],
				"contentType": event.Payload["contentType"],
				"tags":        event.Payload["tags"],
				"publishedAt": event.OccurredAt,
			},
			"$setOnInsert": bson.M{
				"_id":          postID,
				"viewCount":    0,
				"likeCount":    0,
				"commentCount": 0,
			},
		}
		opts := options.UpdateOne().SetUpsert(true)
		_, err := p.coll.UpdateOne(ctx, bson.M{"_id": postID}, doc, opts)
		return err

	case "ContentReacted":
		postID, _ := event.Payload["postId"].(string)
		if postID == "" {
			return nil
		}
		action, _ := event.Payload["action"].(string)
		field := action + "Count"
		_, err := p.coll.UpdateOne(ctx,
			bson.M{"_id": postID},
			bson.M{
				"$inc": bson.M{field: 1},
				"$set": bson.M{"lastEngagementAt": time.Now().UTC()},
			},
		)
		return err

	case "ContentViewed":
		postID, _ := event.Payload["postId"].(string)
		if postID == "" {
			return nil
		}
		_, err := p.coll.UpdateOne(ctx,
			bson.M{"_id": postID},
			bson.M{"$inc": bson.M{"viewCount": 1}},
		)
		return err

	default:
		return nil
	}
}
