package recommendation

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/content-service/internal/content/post/application/ports"
)

// BehaviorProjectionRelay（N0-2）用持久轨驱动「行为 → rm_recommend_feature」投影，
// 替换此前 fire-and-forget 的 BehaviorBatchReported Pub/Sub（生产环境无订阅者，
// tagInteraction / 亲和度 / 交集 kindCounts 投影断链）。
//
// 与 post OutboxRelay 同构：游标增量扫 rm_behavior_events（_id 单调），每条事实的
// 所有 projector 更新、租约续期与 checkpoint 推进在同一事务内提交。共享 checkpoint
// 使用 lease 单写，保证多副本不会把同一用户的低 ObjectID 事件错判为旧水位；投影器仍以
// 每条事件 _id 原子去重，承接 checkpoint 重放。水位线排除最近 WatermarkLag 内插入的
// 文档，避免 InsertMany 下 ObjectID 边界乱序造成漏扫。
type BehaviorProjectionRelay struct {
	events      *mongo.Collection
	checkpoints *mongo.Collection
	projectors  []BehaviorBatchProjector
	consumer    string

	WatermarkLag time.Duration
	leaseOwner   string
	leaseTTL     time.Duration

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
	defaultBehaviorLeaseTTL     = 15 * time.Second
)

var errBehaviorProjectionLeaseLost = errors.New(
	"behavior projection relay lease lost before checkpoint commit",
)

func NewBehaviorProjectionRelay(db *mongo.Database, projectors ...BehaviorBatchProjector) *BehaviorProjectionRelay {
	return &BehaviorProjectionRelay{
		events:       db.Collection("rm_behavior_events"),
		checkpoints:  db.Collection(behaviorCheckpointsColl),
		projectors:   projectors,
		consumer:     behaviorProjectionConsumer,
		WatermarkLag: defaultBehaviorWatermarkLag,
		leaseOwner:   newBehaviorRelayLeaseOwner(),
		leaseTTL:     defaultBehaviorLeaseTTL,
	}
}

// WithWatermarkLag 覆盖乱序保护窗口。仅测试装配使用（同步 Drain 场景置 0）；
// 生产保持默认 2s。
func (r *BehaviorProjectionRelay) WithWatermarkLag(lag time.Duration) *BehaviorProjectionRelay {
	if lag < 0 {
		lag = 0
	}
	r.WatermarkLag = lag
	return r
}

// WithLeaseTTL 覆盖多副本 lease 的存活时间。仅测试或明确的运行时装配使用；
// 生产保持默认值，使一个 relay owner 串行推进共享 checkpoint。
func (r *BehaviorProjectionRelay) WithLeaseTTL(ttl time.Duration) *BehaviorProjectionRelay {
	if ttl > 0 {
		r.leaseTTL = ttl
	}
	return r
}

// WithConsumer 为独立部署或隔离测试指定 checkpoint 身份。生产默认消费者固定，
// 因此同一部署的副本仍共享单一有序游标。
func (r *BehaviorProjectionRelay) WithConsumer(consumer string) *BehaviorProjectionRelay {
	if normalized := strings.TrimSpace(consumer); normalized != "" {
		r.consumer = normalized
	}
	return r
}

type behaviorRelayCheckpointDoc struct {
	ID             string        `bson:"_id"`
	LastID         bson.ObjectID `bson:"lastId"`
	LeaseOwner     string        `bson:"leaseOwner"`
	LeaseExpiresAt time.Time     `bson:"leaseExpiresAt"`
	UpdatedAt      time.Time     `bson:"updatedAt"`
}

// RelayBehaviorEvent 在 RawBehaviorEvent 之上带出 Mongo _id 作游标。
type RelayBehaviorEvent struct {
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
	acquired, err := r.acquireLease(ctx)
	if err != nil {
		return 0, err
	}
	if !acquired {
		// standby replica：活跃 owner 正在顺序推进全局 cursor。不得并行处理，
		// 否则每文档 ObjectID 水位会把较慢副本尚未落下的低 ID 误判为旧事件。
		return 0, nil
	}

	var checkpoint behaviorRelayCheckpointDoc
	err = r.checkpoints.FindOne(ctx, bson.M{"_id": r.consumer}).Decode(&checkpoint)
	if err != nil && err != mongo.ErrNoDocuments {
		return 0, fmt.Errorf("load behavior projection checkpoint: %w", err)
	}

	filter := r.ScanFilter(checkpoint.LastID, time.Now().UTC())

	cursor, err := r.events.Find(ctx, filter,
		options.Find().SetSort(bson.D{{Key: "_id", Value: 1}}).SetLimit(int64(limit)))
	if err != nil {
		return 0, fmt.Errorf("scan behavior events: %w", err)
	}
	var rows []RelayBehaviorEvent
	if err := cursor.All(ctx, &rows); err != nil {
		return 0, fmt.Errorf("decode behavior events: %w", err)
	}
	if len(rows) == 0 {
		return 0, nil
	}

	session, err := r.checkpoints.Database().Client().StartSession()
	if err != nil {
		return 0, fmt.Errorf("start behavior projection transaction session: %w", err)
	}
	defer session.EndSession(ctx)

	events := BuildBehaviorBatchEvents(rows)
	processed := 0
	for index, event := range events {
		_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
			now := time.Now().UTC()
			leaseResult, leaseErr := r.checkpoints.UpdateOne(txCtx,
				bson.M{
					"_id":            r.consumer,
					"leaseOwner":     r.leaseOwner,
					"leaseExpiresAt": bson.M{"$gt": now},
				},
				bson.M{"$set": bson.M{
					"leaseExpiresAt": now.Add(r.leaseTTL),
					"updatedAt":      now,
				}},
			)
			if leaseErr != nil {
				return nil, fmt.Errorf("renew behavior projection lease: %w", leaseErr)
			}
			if leaseResult.MatchedCount != 1 {
				return nil, errBehaviorProjectionLeaseLost
			}
			for _, projector := range r.projectors {
				if projectErr := projector.Project(txCtx, event); projectErr != nil {
					return nil, fmt.Errorf(
						"project behavior batch (aggregate=%s): %w",
						event.AggregateID,
						projectErr,
					)
				}
			}
			checkpointAt := time.Now().UTC()
			checkpointResult, checkpointErr := r.checkpoints.UpdateOne(txCtx,
				bson.M{"_id": r.consumer, "leaseOwner": r.leaseOwner},
				bson.M{"$set": bson.M{
					"lastId":         rows[index].ID,
					"leaseExpiresAt": checkpointAt.Add(r.leaseTTL),
					"updatedAt":      checkpointAt,
				}},
			)
			if checkpointErr != nil {
				return nil, fmt.Errorf(
					"save behavior projection checkpoint: %w",
					checkpointErr,
				)
			}
			if checkpointResult.MatchedCount != 1 {
				return nil, errBehaviorProjectionLeaseLost
			}
			return nil, nil
		})
		if err != nil {
			r.recordFailure(err)
			return processed, err
		}
		processed++
	}
	return processed, nil
}

// scanFilter 为生产 relay 保留 ObjectID 插入时间水位，避免批量写入边界的乱序漏扫。
// lag=0 仅用于同步测试/回放：ObjectID 的时间部分精度只有秒，若仍使用
// `$lt NewObjectIDFromTimestamp(now)`，本秒刚写入的所有事实都会被错误排除。
func (r *BehaviorProjectionRelay) ScanFilter(
	lastID bson.ObjectID,
	now time.Time,
) bson.M {
	bounds := bson.M{}
	if !lastID.IsZero() {
		bounds["$gt"] = lastID
	}
	if r.WatermarkLag > 0 {
		bounds["$lt"] = bson.NewObjectIDFromTimestamp(now.Add(-r.WatermarkLag))
	}
	if len(bounds) == 0 {
		return bson.M{}
	}
	return bson.M{"_id": bounds}
}

// acquireLease 为共享 checkpoint 取得单写租约。投影器保留逐文档事件水位以处理重放；
// 租约补齐全局顺序保证，避免领先副本使另一副本尚未落下的低 ObjectID 被跳过。
// 每条事实随后在事务内再次续租并推进 checkpoint，过期 owner 不能在新 owner 接管后提交。
func (r *BehaviorProjectionRelay) acquireLease(ctx context.Context) (bool, error) {
	now := time.Now().UTC()
	if strings.TrimSpace(r.leaseOwner) == "" {
		return false, fmt.Errorf("behavior projection relay lease owner is empty")
	}
	if r.leaseTTL <= 0 {
		return false, fmt.Errorf("behavior projection relay lease TTL must be positive")
	}
	filter := bson.M{
		"_id": r.consumer,
		"$or": []bson.M{
			{"leaseOwner": r.leaseOwner},
			{"leaseExpiresAt": bson.M{"$exists": false}},
			{"leaseExpiresAt": bson.M{"$lte": now}},
		},
	}
	update := bson.M{
		"$set": bson.M{
			"leaseOwner":     r.leaseOwner,
			"leaseExpiresAt": now.Add(r.leaseTTL),
			"updatedAt":      now,
		},
	}
	result, err := r.checkpoints.UpdateOne(
		ctx,
		filter,
		update,
		options.UpdateOne().SetUpsert(true),
	)
	if isBehaviorProjectionLeaseContention(err) {
		// 另一副本创建/续期 checkpoint，或持有事务内的 checkpoint 写锁。
		// 这两种情况都代表当前循环不能越过全局 cursor，下一轮再尝试。
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("acquire behavior projection lease: %w", err)
	}
	return result.MatchedCount == 1 || result.UpsertedCount == 1, nil
}

func isBehaviorProjectionLeaseContention(err error) bool {
	if err == nil {
		return false
	}
	if mongo.IsDuplicateKeyError(err) {
		return true
	}
	var commandError mongo.CommandError
	if errors.As(err, &commandError) && commandError.Code == 112 {
		// Mongo WriteConflict：活跃 relay 正在其事务中续租、投影并提交 cursor。
		return true
	}
	var writeError mongo.WriteException
	return errors.As(err, &writeError) && writeError.HasErrorCode(112)
}

func newBehaviorRelayLeaseOwner() string {
	var raw [16]byte
	if _, err := rand.Read(raw[:]); err == nil {
		return "behavior-relay-" + hex.EncodeToString(raw[:])
	}
	// crypto/rand 不可用是极端运行时故障；纳秒 fallback 仍确保同一进程内 owner
	// 不会静默空值退化为无锁并行。
	return fmt.Sprintf("behavior-relay-fallback-%d", time.Now().UnixNano())
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

// BuildBehaviorBatchEvents 按 Mongo _id 全序把每条持久事实重建为一个
// BehaviorBatchReported。禁止跨行合批：event.ID 是两个非幂等计数 projector
// 的原子去重水位；若把非连续事实按 user/session 聚合，单文档水位会跳过交错事件。
func BuildBehaviorBatchEvents(rows []RelayBehaviorEvent) []ProjectorEvent {
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
				"events":     []map[string]any{BehaviorEventPayload(row.RawBehaviorEvent)},
				"count":      1,
				"reportedAt": occurredAt.Format(time.RFC3339),
				"source":     "behavior_projection_relay",
			},
			OccurredAt: occurredAt,
		})
	}
	return events
}

// BehaviorEventPayload 将持久事实重建为 onBehaviorBatch 消费的 payload 形状
// （字段名与 behavior_service.ProcessBatch 的 projectedEvents 对齐）。
func BehaviorEventPayload(ev ports.RawBehaviorEvent) map[string]any {
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
