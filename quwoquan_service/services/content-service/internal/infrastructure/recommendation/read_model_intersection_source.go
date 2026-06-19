package recommendation

import (
	"context"
	"strings"
	"time"

	app "quwoquan_service/services/content-service/internal/application"
)

// defaultIntersectionFreshnessTTL 是 policy 未声明某维度保鲜期时的兜底 TTL。
const defaultIntersectionFreshnessTTL = 7 * 24 * time.Hour

// ReadModelIntersectionSource 是 WP-2 的事实交集「增量物化 + 读穿透」层：
//
//   - FactReasons 优先从 rm_viewer_object_intersection 读模型直出（热路径零图谱计算、零打分）；
//     仅当快照缺失、或其「最易腐维度」的保鲜期已过时，才回落底层 compute 源重算，并经
//     materializeFactReasons 真算 Graph 边权 + Lifecycle 弱标（以上一次快照为增量基线）后回写
//     （分维度保鲜：不同 dimension 各有 TTL，按最短者触发整快照刷新，避免任一维度陈旧占位）。
//   - AffinityReasons 透传底层 compute 后经 applyGraphWeights 真算边权（确定性算术，非 /v1/score
//     同步打分），替换原裸 count 启发式；ObjectReasons 为 viewer×object 点查，亦补边权真算。
//
// 架构基线 v2 §21：edgeWeight / lifecycleState / previousStrength / strengthDelta 全部在「写/刷新
// 路径」物化完成，读路径（summary/list/feed 热命中）仅消费快照、零计算、零同步打分（R-IX01）。
//
// 它本身满足 app.IntersectionSource，可在 main.go 中透明包裹 MongoIntersectionSource，
// 上层 IntersectionService 的 summary/list/feed 无需改动即从读模型取数。
type ReadModelIntersectionSource struct {
	compute        app.IntersectionSource
	store          ViewerIntersectionReadModel
	ttlByDimension map[string]time.Duration
	now            func() time.Time
}

// NewReadModelIntersectionSource 构造读穿透源。ttlDaysByDimension 来自
// recpolicy.Intersection.FreshnessTTLDaysByDimension（metadata 单源）。
func NewReadModelIntersectionSource(
	compute app.IntersectionSource,
	store ViewerIntersectionReadModel,
	ttlDaysByDimension map[string]int,
) *ReadModelIntersectionSource {
	ttl := make(map[string]time.Duration, len(ttlDaysByDimension))
	for dim, days := range ttlDaysByDimension {
		if days > 0 {
			ttl[strings.TrimSpace(dim)] = time.Duration(days) * 24 * time.Hour
		}
	}
	return &ReadModelIntersectionSource{
		compute:        compute,
		store:          store,
		ttlByDimension: ttl,
		now:            func() time.Time { return time.Now().UTC() },
	}
}

func (s *ReadModelIntersectionSource) ttlFor(dimension string) time.Duration {
	if d, ok := s.ttlByDimension[strings.TrimSpace(dimension)]; ok && d > 0 {
		return d
	}
	return defaultIntersectionFreshnessTTL
}

// recomputeDeadline 返回快照需重算的时刻：取所有事实维度中最早到期者（分维度保鲜，
// 按最短 TTL 触发整快照刷新）。affinity 理由不参与（其新鲜度由 /v1/score 通道负责）。
func (s *ReadModelIntersectionSource) recomputeDeadline(doc ViewerIntersectionDoc) time.Time {
	deadline := doc.ComputedAt.Add(defaultIntersectionFreshnessTTL)
	for _, r := range doc.Reasons {
		if r.IntersectionClass == "affinity" {
			continue
		}
		if exp := doc.ComputedAt.Add(s.ttlFor(r.Dimension)); exp.Before(deadline) {
			deadline = exp
		}
	}
	return deadline
}

func (s *ReadModelIntersectionSource) FactReasons(ctx context.Context, userID, channel string) ([]app.IntersectionReasonView, error) {
	now := s.now()
	// 单次 Load 既用于保鲜命中判断，又作为 Lifecycle 增量比对的上一次快照基线。
	prevDoc, prevFound, _ := s.store.Load(ctx, userID)
	if prevFound && now.Before(s.recomputeDeadline(prevDoc)) {
		return prevDoc.Reasons, nil // 热路径零计算（边权/生命周期弱标已物化在快照内）
	}
	computed, err := s.compute.FactReasons(ctx, userID, channel)
	if err != nil {
		// 韧性：底层重算失败时回落上一次良好快照，避免整面板空窗。
		if prevFound {
			return prevDoc.Reasons, nil
		}
		return nil, err
	}
	var prevReasons []app.IntersectionReasonView
	if prevFound {
		prevReasons = prevDoc.Reasons
	}
	// 写/刷新路径真算物化：Graph 边权 + Lifecycle 状态机（以上一次快照为增量基线）。
	enriched := materializeFactReasons(prevReasons, computed, now)
	_ = s.store.Save(ctx, ViewerIntersectionDoc{ViewerID: userID, Reasons: enriched, ComputedAt: now})
	return enriched, nil
}

func (s *ReadModelIntersectionSource) AffinityReasons(ctx context.Context, userID, channel string) ([]app.IntersectionReasonView, error) {
	reasons, err := s.compute.AffinityReasons(ctx, userID, channel)
	if err != nil {
		return nil, err
	}
	// affinity 通道边权真算（确定性算术，零同步打分），与事实交集同尺度。
	return applyGraphWeights(reasons, s.now()), nil
}

func (s *ReadModelIntersectionSource) ObjectReasons(ctx context.Context, viewerID, objectID, objectType string) ([]app.IntersectionReasonView, error) {
	reasons, err := s.compute.ObjectReasons(ctx, viewerID, objectID, objectType)
	if err != nil {
		return nil, err
	}
	return applyGraphWeights(reasons, s.now()), nil
}
