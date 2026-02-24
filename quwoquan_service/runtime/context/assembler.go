package runtimecontext

import (
	"context"
	"sort"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/recommendation"
)

// ProfileStore reads long-term profiles from MongoDB.
type ProfileStore interface {
	GetProfile(ctx context.Context, userID string) (*UserHolisticProfile, error)
}

// VectorSearcher searches for relevant memories/content by embedding.
type VectorSearcher interface {
	Search(ctx context.Context, query string, limit int) ([]RetrievedChunk, error)
}

// ContextAssembler assembles the three-layer context for the assistant.
type ContextAssembler struct {
	pageCtxMgr *PageContextManager
	sessions   recommendation.SessionReader
	profiles   ProfileStore
	vectors    VectorSearcher
}

func NewContextAssembler(
	pageCtxMgr *PageContextManager,
	sessions recommendation.SessionReader,
	profiles ProfileStore,
	vectors VectorSearcher,
) *ContextAssembler {
	return &ContextAssembler{
		pageCtxMgr: pageCtxMgr,
		sessions:   sessions,
		profiles:   profiles,
		vectors:    vectors,
	}
}

// Assemble returns the full three-layer context. Target: < 50ms.
func (a *ContextAssembler) Assemble(ctx context.Context, userID, sessionID string) (*AssistantContext, error) {
	result := &AssistantContext{}

	// Layer 1: PageContext (Redis, < 5ms)
	pageCtx, err := a.pageCtxMgr.Get(ctx, userID)
	if err == nil && pageCtx != nil {
		result.PageContext = pageCtx
	}

	// Layer 2: Session signals from recommendation hot path (Redis, < 5ms)
	if a.sessions != nil {
		state, err := a.sessions.GetSessionState(ctx, userID, sessionID)
		if err == nil && state != nil {
			topInterests := topNKeys(state.TagWeights, 5)
			result.SessionSignals = &SessionSignalSnapshot{
				TagWeights:    state.TagWeights,
				ExposedCount:  len(state.ExposedIDs),
				NegativeCount: len(state.NegativeIDs),
				TopInterests:  topInterests,
			}
		}
	}

	// Layer 3: Long-term holistic profile (MongoDB, < 20ms)
	if a.profiles != nil {
		profile, err := a.profiles.GetProfile(ctx, userID)
		if err == nil && profile != nil {
			result.HolisticProfile = profile
		}
	}

	// Optional: RAG vector search for relevant context
	if a.vectors != nil && result.PageContext != nil {
		query := buildRAGQuery(result.PageContext)
		if query != "" {
			chunks, err := a.vectors.Search(ctx, query, 5)
			if err == nil {
				result.RelevantContent = chunks
			}
		}
	}

	return result, nil
}

func buildRAGQuery(pageCtx *PageContextSnapshot) string {
	if pageCtx.Objects.Post != nil {
		p := pageCtx.Objects.Post
		if p.Title != "" {
			return p.Title
		}
		if len(p.Tags) > 0 {
			return p.Tags[0]
		}
	}
	if pageCtx.Objects.SearchQuery != "" {
		return pageCtx.Objects.SearchQuery
	}
	return ""
}

func topNKeys(weights map[string]float64, n int) []string {
	type kv struct {
		k string
		v float64
	}
	var pairs []kv
	for k, v := range weights {
		if v > 0 {
			pairs = append(pairs, kv{k, v})
		}
	}
	sort.Slice(pairs, func(i, j int) bool { return pairs[i].v > pairs[j].v })
	result := make([]string, 0, n)
	for i, p := range pairs {
		if i >= n {
			break
		}
		result = append(result, p.k)
	}
	return result
}

// MongoProfileStore reads profiles from MongoDB user_holistic_profile collection.
type MongoProfileStore struct {
	coll *mongo.Collection
}

func NewMongoProfileStore(db *mongo.Database) *MongoProfileStore {
	return &MongoProfileStore{coll: db.Collection("user_holistic_profile")}
}

func (s *MongoProfileStore) GetProfile(ctx context.Context, userID string) (*UserHolisticProfile, error) {
	var profile UserHolisticProfile
	err := s.coll.FindOne(ctx, bson.M{"userId": userID}).Decode(&profile)
	if err == mongo.ErrNoDocuments {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &profile, nil
}

// AssistantContextProjector consumes domain events to build holistic profiles.
type AssistantContextProjector struct {
	coll *mongo.Collection
}

func NewAssistantContextProjector(db *mongo.Database) *AssistantContextProjector {
	return &AssistantContextProjector{coll: db.Collection("user_holistic_profile")}
}

func (p *AssistantContextProjector) Name() string { return "AssistantContextProjector" }

func (p *AssistantContextProjector) EventTypes() []string {
	return []string{
		"PostCreated", "PostPublished", "ContentReacted", "ContentViewed",
		"FollowCreated", "FollowDeleted",
		"CircleJoined", "CircleLeft",
		"MessageSent",
		"AssistantRunCompleted",
		"UserTagsUpdated",
	}
}

func (p *AssistantContextProjector) Project(ctx context.Context, event StoredEvent) error {
	userID := event.Metadata.UserID
	if userID == "" {
		userID, _ = event.Payload["userId"].(string)
	}
	if userID == "" {
		return nil
	}

	var dimension string
	var tagKey string

	switch event.Type {
	case "PostCreated", "PostPublished", "ContentViewed", "ContentReacted":
		dimension = "contentPreference"
		tags, _ := event.Payload["tags"].([]any)
		if len(tags) > 0 {
			tagKey, _ = tags[0].(string)
		}
		ct, _ := event.Payload["contentType"].(string)
		if tagKey == "" && ct != "" {
			tagKey = ct
		}

	case "FollowCreated", "FollowDeleted":
		dimension = "socialGraph"
		tagKey = "follow_activity"

	case "CircleJoined", "CircleLeft":
		dimension = "circleActivity"
		tagKey = "circle_participation"

	case "MessageSent":
		dimension = "chatTopics"
		tagKey = "chat_activity"

	case "AssistantRunCompleted":
		dimension = "assistantHistory"
		tagKey = "assistant_usage"

	case "UserTagsUpdated":
		dimension = "contentPreference"
		tags, _ := event.Payload["tags"].([]any)
		if len(tags) > 0 {
			tagKey, _ = tags[0].(string)
		}

	default:
		return nil
	}

	if tagKey == "" {
		tagKey = "_general"
	}

	field := dimension + ".tags." + tagKey
	update := bson.M{
		"$inc": bson.M{
			field:                           1.0,
			dimension + ".eventCount": 1,
		},
		"$set": bson.M{
			"userId":    userID,
			"updatedAt": time.Now().UTC(),
		},
	}

	opts := options.UpdateOne().SetUpsert(true)
	_, err := p.coll.UpdateOne(ctx, bson.M{"userId": userID}, update, opts)
	return err
}

// StoredEvent mirrors eventstore.StoredEvent to avoid circular import.
type StoredEvent struct {
	ID            string         `bson:"_id"           json:"id"`
	Type          string         `bson:"type"          json:"type"`
	AggregateType string         `bson:"aggregateType" json:"aggregateType"`
	AggregateID   string         `bson:"aggregateId"   json:"aggregateId"`
	Payload       map[string]any `bson:"payload"       json:"payload"`
	Metadata      EventMeta      `bson:"metadata"      json:"metadata"`
	OccurredAt    time.Time      `bson:"occurredAt"    json:"occurredAt"`
}

type EventMeta struct {
	TraceID   string `bson:"traceId"   json:"traceId"`
	RequestID string `bson:"requestId" json:"requestId"`
	UserID    string `bson:"userId"    json:"userId"`
	Producer  string `bson:"producer"  json:"producer"`
}
