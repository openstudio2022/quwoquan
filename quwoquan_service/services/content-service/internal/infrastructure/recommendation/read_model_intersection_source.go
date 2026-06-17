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
//   - FactReasons 优先从 rm_viewer_object_intersection 读模型直出（热路径零图谱计算）；
//     仅当快照缺失、或其「最易腐维度」的保鲜期已过时，才回落底层 compute 源重算并回写
//     （分维度保鲜：不同 dimension 各有 TTL，按最短者触发整快照刷新，避免任一维度陈旧占位）。
//   - AffinityReasons / ObjectReasons 透传底层 compute（affinity = /v1/score 概率分通道；
//     对象页为 viewer×object 点查访问模式，不属于 viewer 级 feed 读模型）。
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
	if doc, found, err := s.store.Load(ctx, userID); err == nil && found {
		if now.Before(s.recomputeDeadline(doc)) {
			return doc.Reasons, nil // 热路径零计算
		}
	}
	computed, err := s.compute.FactReasons(ctx, userID, channel)
	if err != nil {
		// 韧性：底层重算失败时回落上一次良好快照，避免整面板空窗。
		if doc, found, lerr := s.store.Load(ctx, userID); lerr == nil && found {
			return doc.Reasons, nil
		}
		return nil, err
	}
	_ = s.store.Save(ctx, ViewerIntersectionDoc{ViewerID: userID, Reasons: computed, ComputedAt: now})
	return computed, nil
}

func (s *ReadModelIntersectionSource) AffinityReasons(ctx context.Context, userID, channel string) ([]app.IntersectionReasonView, error) {
	return s.compute.AffinityReasons(ctx, userID, channel)
}

func (s *ReadModelIntersectionSource) ObjectReasons(ctx context.Context, viewerID, objectID, objectType string) ([]app.IntersectionReasonView, error) {
	return s.compute.ObjectReasons(ctx, viewerID, objectID, objectType)
}
