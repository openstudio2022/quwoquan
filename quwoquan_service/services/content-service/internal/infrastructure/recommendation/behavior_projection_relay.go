package recommendation

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/content-service/internal/application/ports"
)

// BehaviorProjectionRelay（N0-2）用持久轨驱动「行为 → rm_recommend_feature」投影，
// 替换此前 fire-and-forget 的 BehaviorBatchReported Pub/Sub（生产环境无订阅者，
// tagInteraction / 亲和度 / 交集 kindCounts 投影断链）。
//
// 与 post OutboxRelay 同构：游标增量扫 rm_behavior_events（_id 单调），全部
// projector 处理成功后才推进 checkpoint。投影器以每条事件 _id 原子去重，因此
// checkpoint 重放与多副本并发不会重复 $inc。水位线排除最近 watermarkLag 内
// 插入的文档，避免多副本并发 InsertMany 下 ObjectID 边界乱序造成漏扫。
type BehaviorProjectionRelay struct {
	events      *mongo.Collection
	checkpoints *mongo.Collection
	projectors  []BehaviorBatchProjector
	consumer    string

	watermarkLag time.Duration

	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

// BehaviorBatchProjector 是 relay 下游的窄接口；RecommendFeatureProjector 与
// DiscoveryFeedProjector 均满足（消费 Type=="BehaviorBatchReported" 的事件）。
type BehaviorBatchProjector interface {
	Project(ctx context.Context, event ProjectorEvent) error
}

const (
	behaviorProjectionConsumer  = "behavior-feature-projection"
	behaviorCheckpointsColl     = "rec_projection_checkpoints"
	defaultBehaviorWatermarkLag = 2 * time.Second
)

func NewBehaviorProjectionRelay(db *mongo.Database, projectors ...BehaviorBatchProjector) *BehaviorProjectionRelay {
	return &BehaviorProjectionRelay{
		events:       db.Collection("rm_behavior_events"),
		checkpoints:  db.Collection(behaviorCheckpointsColl),
		projectors:   projectors,
		consumer:     behaviorProjectionConsumer,
		watermarkLag: defaultBehaviorWatermarkLag,
	}
}

// WithWatermarkLag 覆盖乱序保护窗口。仅测试装配使用（同步 Drain 场景置 0）；
// 生产保持默认 2s。
func (r *BehaviorProjectionRelay) WithWatermarkLag(lag time.Duration) *BehaviorProjectionRelay {
	r.watermarkLag = lag
	return r
}

type behaviorRelayCheckpointDoc struct {
	ID        string        `bson:"_id"`
	LastID    bson.ObjectID `bson:"lastId"`
	UpdatedAt time.Time     `bson:"updatedAt"`
}

// relayBehaviorEvent 在 RawBehaviorEvent 之上带出 Mongo _id 作游标。
type relayBehaviorEvent struct {
	ID bson.ObjectID `bson:"_id"`

	ports.RawBehaviorEvent `bson:",inline"`
}

// Drain 处理最多 limit 条持久行为事实，返回已 checkpoint 的条数。
// 任何 projector 失败都不推进 checkpoint（下一轮整批重扫）。
func (r *BehaviorProjectionRelay) Drain(ctx context.Context, limit int) (int, error) {
	if r == nil || r.events == nil || r.checkpoints == nil || len(r.projectors) == 0 {
		return 0, fmt.Errorf("behavior projection relay is not fully configured")
	}
	if limit <= 0 {
		limit = 200
	}

	var checkpoint behaviorRelayCheckpointDoc
	err := r.checkpoints.FindOne(ctx, bson.M{"_id": r.consumer}).Decode(&checkpoint)
	if err != nil && err != mongo.ErrNoDocuments {
		return 0, fmt.Errorf("load behavior projection checkpoint: %w", err)
	}

	// 水位线：只消费插入时间早于 now-watermarkLag 的文档（ObjectID 时间戳前缀
	// 由服务端生成，与客户端 occurredAt 时钟无关）。
	watermark := bson.NewObjectIDFromTimestamp(time.Now().Add(-r.watermarkLag))
	filter := bson.M{"_id": bson.M{"$lt": watermark}}
	if !checkpoint.LastID.IsZero() {
		filter["_id"] = bson.M{"$gt": checkpoint.LastID, "$lt": watermark}
	}

	cursor, err := r.events.Find(ctx, filter,
		options.Find().SetSort(bson.D{{Key: "_id", Value: 1}}).SetLimit(int64(limit)))
	if err != nil {
		return 0, fmt.Errorf("scan behavior events: %w", err)
	}
	var rows []relayBehaviorEvent
	if err := cursor.All(ctx, &rows); err != nil {
		return 0, fmt.Errorf("decode behavior events: %w", err)
	}
	if len(rows) == 0 {
		return 0, nil
	}

	for _, event := range buildBehaviorBatchEvents(rows) {
		for _, projector := range r.projectors {
			if err := projector.Project(ctx, event); err != nil {
				r.recordFailure(err)
				return 0, fmt.Errorf("project behavior batch (aggregate=%s): %w", event.AggregateID, err)
			}
		}
	}

	lastID := rows[len(rows)-1].ID
	if _, err := r.checkpoints.UpdateOne(ctx,
		bson.M{"_id": r.consumer},
		bson.M{"$set": bson.M{"lastId": lastID, "updatedAt": time.Now().UTC()}},
		options.UpdateOne().SetUpsert(true),
	); err != nil {
		return 0, fmt.Errorf("save behavior projection checkpoint: %w", err)
	}
	return len(rows), nil
}

// Run 周期 Drain 直到 ctx 结束；失败批次不推进 checkpoint，下一轮重试。
func (r *BehaviorProjectionRelay) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = time.Second
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		if _, err := r.Drain(ctx, 200); err != nil {
			r.recordFailure(err)
			if ctx.Err() != nil {
				return ctx.Err()
			}
		} else {
			r.recordSuccess()
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

// Healthy 供生产 readiness 边界使用（与 post OutboxRelay.Healthy 同构）。
func (r *BehaviorProjectionRelay) Healthy(maxStaleness time.Duration) error {
	if r == nil {
		return fmt.Errorf("behavior projection relay is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 30 * time.Second
	}
	r.mu.RLock()
	defer r.mu.RUnlock()
	if r.lastSuccess.IsZero() {
		return fmt.Errorf("behavior projection relay has not completed a scan")
	}
	if r.lastFailure != nil {
		return fmt.Errorf("behavior projection relay last failure: %w", r.lastFailure)
	}
	if time.Since(r.lastSuccess) > maxStaleness {
		return fmt.Errorf("behavior projection relay heartbeat is stale: %s",
			time.Since(r.lastSuccess).Round(time.Millisecond))
	}
	return nil
}

func (r *BehaviorProjectionRelay) recordSuccess() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.lastSuccess = time.Now().UTC()
	r.lastFailure = nil
}

func (r *BehaviorProjectionRelay) recordFailure(err error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.lastFailure = err
}

// buildBehaviorBatchEvents 按 Mongo _id 全序把每条持久事实重建为一个
// BehaviorBatchReported。禁止跨行合批：event.ID 是两个非幂等计数 projector
// 的原子去重水位；若把非连续事实按 user/session 聚合，单文档水位会跳过交错事件。
func buildBehaviorBatchEvents(rows []relayBehaviorEvent) []ProjectorEvent {
	events := make([]ProjectorEvent, 0, len(rows))
	for _, row := range rows {
		occurredAt := row.CreatedAt.UTC()
		events = append(events, ProjectorEvent{
			ID:            row.ID.Hex(),
			Type:          "BehaviorBatchReported",
			AggregateType: "BehaviorBatch",
			AggregateID:   firstNonEmptyRelay(row.SessionID, row.UserID),
			Payload: map[string]any{
				"userId":     row.UserID,
				"sessionId":  row.SessionID,
				"events":     []map[string]any{behaviorEventPayload(row.RawBehaviorEvent)},
				"count":      1,
				"reportedAt": occurredAt.Format(time.RFC3339),
				"source":     "behavior_projection_relay",
			},
			OccurredAt: occurredAt,
		})
	}
	return events
}

// behaviorEventPayload 将持久事实重建为 onBehaviorBatch 消费的 payload 形状
// （字段名与 behavior_service.ProcessBatch 的 projectedEvents 对齐）。
func behaviorEventPayload(ev ports.RawBehaviorEvent) map[string]any {
	return map[string]any{
		"clientEventId":          ev.ClientEventID,
		"state":                  ev.State,
		"userId":                 ev.UserID,
		"deviceActorId":          ev.DeviceActorID,
		"sessionId":              ev.SessionID,
		"contentId":              ev.ContentID,
		"action":                 ev.Action,
		"contentType":            ev.ContentType,
		"tagRefs":                append([]string(nil), ev.Tags...),
		"duration":               ev.Duration,
		"occurredAt":             ev.OccurredAt,
		"authorId":               ev.AuthorID,
		"referralSource":         ev.ReferralSource,
		"engagementDepth":        ev.EngagementDepth,
		"consumedRatio":          ev.ConsumedRatio,
		"totalUnits":             ev.TotalUnits,
		"effectivePlayMs":        ev.EffectivePlayMS,
		"entityRefs":             append([]string(nil), ev.EntityRefs...),
		"feedRequestId":          ev.FeedRequestID,
		"feedPosition":           ev.Position,
		"commentLength":          ev.CommentLength,
		"channelId":              ev.ChannelID,
		"rankingVersion":         ev.RankingVersion,
		"reasonVersion":          ev.ReasonVersion,
		"recallPath":             ev.RecallPath,
		"contentVertical":        ev.ContentVertical,
		"supplySource":           ev.SupplySource,
		"intersectionDimension":  ev.IntersectionDimension,
		"intersectionTagRefs":    append([]string(nil), ev.IntersectionTagRefs...),
		"intersectionId":         ev.IntersectionID,
		"intersectionClass":      ev.IntersectionClass,
		"intersectionSourceRef":  ev.IntersectionSourceRef,
		"intersectionEvidenceId": ev.IntersectionEvidenceID,
	}
}

func firstNonEmptyRelay(values ...string) string {
	for _, v := range values {
		if strings.TrimSpace(v) != "" {
			return v
		}
	}
	return ""
}
