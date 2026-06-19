package persistence

import (
	"context"
	"log/slog"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const (
	behaviorEventsCollection = "rm_behavior_events"
	behaviorEventTTLDays     = 30
)

// BehaviorEventStore persists raw user behavior events for offline analytics.
type BehaviorEventStore interface {
	InsertBatch(ctx context.Context, events []RawBehaviorEvent) error
	// ListUserFootprint 按用户读取最近行为边（我的足迹只读契约的数据源；
	// 无新写路径，复用既有行为事件）。actions 为空表示全部消费型行为；
	// before 非零时只取更早的事件（cursor 分页）。
	ListUserFootprint(ctx context.Context, userID string, actions []string, before time.Time, limit int) ([]RawBehaviorEvent, error)
}

// RawBehaviorEvent is the persistent form of a user behavior event.
type RawBehaviorEvent struct {
	ClientEventID   string   `bson:"clientEventId,omitempty"`
	State           string   `bson:"state,omitempty"`
	UserID          string   `bson:"userId"`
	DeviceActorID   string   `bson:"deviceActorId,omitempty"`
	SessionID       string   `bson:"sessionId"`
	ContentID       string   `bson:"contentId"`
	Action          string   `bson:"action"`
	Tags            []string `bson:"tagRefs,omitempty"`
	Duration        float64  `bson:"duration,omitempty"`
	AuthorID        string   `bson:"authorId,omitempty"`
	ReferralSource  string   `bson:"referralSource,omitempty"`
	EngagementDepth int      `bson:"engagementDepth,omitempty"`
	ConsumedRatio   float64  `bson:"consumedRatio,omitempty"`
	TotalUnits      int      `bson:"totalUnits,omitempty"`
	EntityRefs      []string `bson:"entityRefs,omitempty"`
	FeedRequestID   string   `bson:"feedRequestId,omitempty"`
	// Position 是事件发生时的 feed 内序位（曝光/点击位置），与 FeedRequestID 组合可还原
	// 「某一次 feed 下发的第几位被点击/停留」，供位置偏置校正与离线 replay 归因。
	Position int `bson:"position,omitempty"`
	// CommentLength 是评论行为的正文长度，供评论质量/深度互动信号离线分析。
	CommentLength int `bson:"commentLength,omitempty"`
	// ChannelID/RankingVersion 是阶段五归因字段：feed 下发频道与精排版本；与 FeedRequestID 组合可
	// 离线还原「某次 feed 下发(频道/精排版本)的第几位被曝光/点击/转化」，供位置偏置校正与 AB / replay。
	ChannelID      string `bson:"channelId,omitempty"`
	RankingVersion string `bson:"rankingVersion,omitempty"`
	// 交集转化归因（S6）：触发交集行动（follow/join_circle/add_contact）的维度与路径制 tagRef。
	IntersectionDimension string   `bson:"intersectionDimension,omitempty"`
	IntersectionTagRefs   []string `bson:"intersectionTagRefs,omitempty"`
	// 交集漏斗归因（曝光/点击/转化，R08 端云对齐）：交集稳定标识、类别（fact|affinity）、
	// 来源 kind 与点级证据 id，使「交集曝光 → 点击 → 转化」可按同一 intersectionId 离线下钻。
	IntersectionID         string    `bson:"intersectionId,omitempty"`
	IntersectionClass      string    `bson:"intersectionClass,omitempty"`
	IntersectionSourceRef  string    `bson:"intersectionSourceRef,omitempty"`
	IntersectionEvidenceID string    `bson:"intersectionEvidenceId,omitempty"`
	OccurredAt             string    `bson:"occurredAt"`
	CreatedAt              time.Time `bson:"createdAt"`
}

// MongoBehaviorEventStore persists raw behavior events to MongoDB with TTL.
type MongoBehaviorEventStore struct {
	coll   *mongo.Collection
	logger *slog.Logger
}

// NewMongoBehaviorEventStore creates a store and ensures TTL + analytics indexes.
func NewMongoBehaviorEventStore(db *mongo.Database, logger *slog.Logger) *MongoBehaviorEventStore {
	s := &MongoBehaviorEventStore{
		coll:   db.Collection(behaviorEventsCollection),
		logger: logger,
	}
	s.ensureIndexes()
	return s
}

func (s *MongoBehaviorEventStore) ensureIndexes() {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	ttl := int32(behaviorEventTTLDays * 24 * 60 * 60)

	indexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "createdAt", Value: 1}},
			Options: options.Index().SetExpireAfterSeconds(ttl),
		},
		{
			Keys: bson.D{{Key: "userId", Value: 1}, {Key: "action", Value: 1}, {Key: "createdAt", Value: -1}},
		},
		{
			Keys: bson.D{{Key: "contentId", Value: 1}, {Key: "createdAt", Value: -1}},
		},
	}

	for _, idx := range indexes {
		if _, err := s.coll.Indexes().CreateOne(ctx, idx); err != nil {
			s.logger.Warn("behavior_event_store: index creation failed", slog.String("error", err.Error()))
		}
	}
}

func (s *MongoBehaviorEventStore) InsertBatch(ctx context.Context, events []RawBehaviorEvent) error {
	if len(events) == 0 {
		return nil
	}

	docs := make([]interface{}, len(events))
	for i := range events {
		docs[i] = events[i]
	}

	_, err := s.coll.InsertMany(ctx, docs)
	if err != nil {
		s.logger.Error("behavior_event_store: insert failed",
			slog.String("error", err.Error()),
			slog.Int("count", len(events)),
		)
	}
	return err
}

// ListUserFootprint 读取用户最近行为事件（createdAt 倒序），复用
// userId+action+createdAt 复合索引；不投影聚合，去重与展示语义由应用层决定。
func (s *MongoBehaviorEventStore) ListUserFootprint(ctx context.Context, userID string, actions []string, before time.Time, limit int) ([]RawBehaviorEvent, error) {
	if limit <= 0 || limit > 200 {
		limit = 50
	}
	filter := bson.M{"userId": userID}
	if len(actions) > 0 {
		filter["action"] = bson.M{"$in": actions}
	}
	if !before.IsZero() {
		filter["createdAt"] = bson.M{"$lt": before}
	}
	cursor, err := s.coll.Find(ctx, filter,
		options.Find().SetSort(bson.D{{Key: "createdAt", Value: -1}}).SetLimit(int64(limit)))
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var out []RawBehaviorEvent
	if err := cursor.All(ctx, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// NoopBehaviorEventStore discards events (used when MongoDB is not available).
type NoopBehaviorEventStore struct{}

func (NoopBehaviorEventStore) InsertBatch(_ context.Context, _ []RawBehaviorEvent) error {
	return nil
}

func (NoopBehaviorEventStore) ListUserFootprint(_ context.Context, _ string, _ []string, _ time.Time, _ int) ([]RawBehaviorEvent, error) {
	return nil, nil
}
