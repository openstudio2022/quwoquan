package recommendation

import (
	"math"
	"strings"
	"time"

	intersectionapp "quwoquan_service/services/content-service/internal/content/post/application/intersection"
)

// 架构基线 v2 §21 —— 交集 Graph / Lifecycle / Propagation 物化器（异步真算，读路径零计算消费）。
//
// 设计要点（对齐计划切片⑥与 R-IX01「读路径零同步打分」不变量）：
//
//   - Graph 边权真算：edgeWeight = relationStrength × InteractionFrequency × RecencyDecay。
//     三个因子全部来自交集理由自身已携带的真实信号（关系强度 / 多跳证据绝对计数 / 新鲜度），
//     纯确定性算术，不调用任何同步评分服务（/score）。因此「物化写路径」与「读穿透热路径」
//     均零同步打分，不变量保持。
//   - Lifecycle 状态机真算：以「上一次物化快照」为基线对边权做增量比对，按 delta 落
//     new / strengthened / stable / weakened / reactivated 弱标，并回填 previousStrength / strengthDelta。
//     这正是「增量异步投影」语义——读路径只消费快照里已物化好的弱标。
//   - Propagation 多跳：InteractionFrequency 由交集点携带的绝对计数（共同好友 / 共同圈子 / 多跳路径
//     等可追溯证据）经饱和函数派生；每个点都带真实 Count 与具名样本，证据可回溯、可审计。
const (
	// EdgeRecencyHalfLife 边权新鲜度半衰期：14 天内边权基本保留，超期按指数衰减。
	EdgeRecencyHalfLife = 14 * 24 * time.Hour
	// EdgeRecencyFloor 衰减下限，避免既往强边被时间彻底清零（其衰减仍可被 lifecycle 标记 weakened）。
	EdgeRecencyFloor = 0.2
	// InteractionSaturation 绝对证据计数饱和常数：控制多跳证据的边际递减速度（越小越快饱和到 1）。
	InteractionSaturation = 2.5
	// lifecycleDelta 触发 strengthened / weakened 的最小边权变化阈值。
	lifecycleDelta = 0.05
)

// MaterializeFactReasons 物化事实交集：先填 Graph 边权（纯函数），再叠加 Lifecycle 状态机
// （依赖上一次快照 prev 做增量比对）。返回值即写入 rm_viewer_object_intersection 的快照理由。
func MaterializeFactReasons(prev, fresh []intersectionapp.IntersectionReasonView, now time.Time) []intersectionapp.IntersectionReasonView {
	fresh = ApplyGraphWeights(fresh, now)
	prevByKey := make(map[string]intersectionapp.IntersectionReasonView, len(prev))
	for _, p := range prev {
		prevByKey[ReasonIdentityKey(p)] = p
	}
	for i := range fresh {
		p, hadPrev := prevByKey[ReasonIdentityKey(fresh[i])]
		applyLifecycle(&fresh[i], p, hadPrev)
	}
	return fresh
}

// ApplyGraphWeights 为每条理由填充 Graph 边权（纯函数，无既往依赖；affinity 通道复用此真算
// 替换原裸 count 启发式，得到与事实交集同尺度的可排序边权）。
func ApplyGraphWeights(reasons []intersectionapp.IntersectionReasonView, now time.Time) []intersectionapp.IntersectionReasonView {
	for i := range reasons {
		reasons[i].EdgeWeight = round4(ComputeEdgeWeight(reasons[i], now))
	}
	return reasons
}

// applyLifecycle 依据上一次物化的边权基线，给单条理由落生命周期弱标 + previousStrength / strengthDelta。
func applyLifecycle(r *intersectionapp.IntersectionReasonView, prev intersectionapp.IntersectionReasonView, hadPrev bool) {
	if !hadPrev {
		// 首次出现的边：标记 new，previousStrength 归零，delta 即当前边权。
		r.LifecycleState = "new"
		r.PreviousStrength = 0
		r.StrengthDelta = round4(r.EdgeWeight)
		return
	}
	r.PreviousStrength = round4(prev.EdgeWeight)
	delta := r.EdgeWeight - prev.EdgeWeight
	r.StrengthDelta = round4(delta)
	switch {
	case prev.LifecycleState == "weakened" && delta > lifecycleDelta:
		// 曾衰退、本轮重新增强：复活。
		r.LifecycleState = "reactivated"
	case delta > lifecycleDelta:
		r.LifecycleState = "strengthened"
	case delta < -lifecycleDelta:
		r.LifecycleState = "weakened"
	default:
		r.LifecycleState = "stable"
	}
}

// ComputeEdgeWeight 真算单条交集边权（确定性，无外部调用）。
func ComputeEdgeWeight(r intersectionapp.IntersectionReasonView, now time.Time) float64 {
	w := relationStrength(r) * InteractionFrequency(r) * RecencyDecay(r.FreshAt, now)
	return clamp01(w)
}

// relationStrength 关系强度：优先取理由自身 Strength（scoreFromCount 真实派生，基线 0.5）；
// 缺省时从证据频率回退派生，保证可参与排序。
func relationStrength(r intersectionapp.IntersectionReasonView) float64 {
	if r.Strength > 0 {
		return clamp01(r.Strength)
	}
	return clamp01(0.5 + 0.5*InteractionFrequency(r))
}

// InteractionFrequency 交互/多跳频率：对绝对证据计数做指数饱和（1 - e^{-n/k}），范围 (0,1)，
// 体现多跳证据的边际递减；n 为可追溯的绝对计数（Propagation 真实多跳条数）。
func InteractionFrequency(r intersectionapp.IntersectionReasonView) float64 {
	n := EvidenceCount(r)
	if n <= 0 {
		return 0
	}
	return 1 - math.Exp(-float64(n)/InteractionSaturation)
}

// EvidenceCount 取理由的多跳证据绝对计数：优先按交集点 Count 求和（最细粒度且可追溯），
// 回退到 TotalPointCount / MutualCount / FactPointCount 中的最大者。
func EvidenceCount(r intersectionapp.IntersectionReasonView) int {
	if len(r.IntersectionPoints) > 0 {
		sum := 0
		for _, p := range r.IntersectionPoints {
			if p.Count > 0 {
				sum += p.Count
			} else {
				sum++
			}
		}
		if sum > 0 {
			return sum
		}
	}
	n := r.TotalPointCount
	if r.MutualCount > n {
		n = r.MutualCount
	}
	if r.FactPointCount > n {
		n = r.FactPointCount
	}
	return n
}

// RecencyDecay 新鲜度衰减：以 FreshAt 为基准做半衰期指数衰减，clamp 到 [floor, 1]。
// 缺省/无法解析新鲜度时按「刚生成」处理（decay=1）。
func RecencyDecay(freshAt string, now time.Time) float64 {
	t, err := time.Parse(time.RFC3339, strings.TrimSpace(freshAt))
	if err != nil {
		return 1.0
	}
	age := now.Sub(t)
	if age <= 0 {
		return 1.0
	}
	decay := math.Pow(0.5, age.Hours()/EdgeRecencyHalfLife.Hours())
	if decay < EdgeRecencyFloor {
		return EdgeRecencyFloor
	}
	return decay
}

// ReasonIdentityKey 跨快照稳定地标识同一条交集边，用于 lifecycle 增量比对。
func ReasonIdentityKey(r intersectionapp.IntersectionReasonView) string {
	switch {
	case strings.TrimSpace(r.DedupeKey) != "":
		return "d:" + r.DedupeKey
	case strings.TrimSpace(r.IntersectionID) != "":
		return "i:" + r.IntersectionID
	case strings.TrimSpace(r.ActionTargetID) != "":
		return "a:" + r.ActionTargetID
	case strings.TrimSpace(r.RelationObjectID) != "":
		return "r:" + r.RelationObjectID
	default:
		return "n:" + r.Dimension + "|" + r.DisplayName
	}
}

func clamp01(v float64) float64 {
	if v < 0 {
		return 0
	}
	if v > 1 {
		return 1
	}
	return v
}

func round4(v float64) float64 {
	return math.Round(v*1e4) / 1e4
}
