package intersection

import (
	"sort"
	"strconv"
	"strings"
	"time"
)

func rankAndDedupeIntersectionList(userID string, items []IntersectionReasonView) []IntersectionReasonView {
	chosen := make(map[string]IntersectionReasonView, len(items))
	for _, item := range items {
		key := intersectionListDedupeKey(userID, item)
		if strings.TrimSpace(item.DedupeKey) == "" {
			item.DedupeKey = key
		}
		existing, ok := chosen[key]
		if !ok || compareIntersectionListRank(item, existing) < 0 {
			chosen[key] = item
		}
	}
	ranked := make([]IntersectionReasonView, 0, len(chosen))
	for _, item := range chosen {
		ranked = append(ranked, item)
	}
	sort.SliceStable(ranked, func(i, j int) bool {
		return compareIntersectionListRank(ranked[i], ranked[j]) < 0
	})
	return ranked
}

func intersectionListDedupeKey(userID string, r IntersectionReasonView) string {
	viewerID := strings.TrimSpace(userID)
	objectID := strings.TrimSpace(r.ActionTargetID)
	if objectID == "" {
		objectID = strings.TrimSpace(r.RelationObjectID)
	}
	if objectID == "" {
		objectID = strings.TrimSpace(r.IntersectionID)
	}
	objectType := strings.TrimSpace(r.ObjectKind)
	intersectionKind := strings.TrimSpace(r.Kind)
	if intersectionKind == "" {
		intersectionKind = strings.TrimSpace(r.Source)
	}
	return strings.Join([]string{viewerID, objectID, objectType, intersectionKind}, ":")
}

func resolveIntersectionListTimeBucket(now time.Time, freshAt string) string {
	fresh, err := time.Parse(time.RFC3339, strings.TrimSpace(freshAt))
	if err != nil {
		return "lastMonth"
	}
	today := dateOnlyUTC(now)
	day := dateOnlyUTC(fresh)
	if day.Equal(today) {
		return "today"
	}
	if day.Equal(today.AddDate(0, 0, -1)) {
		return "yesterday"
	}
	if !day.Before(today.AddDate(0, 0, -7)) {
		return "last7Days"
	}
	if day.Year() == today.Year() && day.Month() == today.Month() {
		return "thisMonth"
	}
	lastMonth := today.AddDate(0, -1, 0)
	if day.Year() == lastMonth.Year() && day.Month() == lastMonth.Month() {
		return "lastMonth"
	}
	return "outOfRange"
}

func dateOnlyUTC(t time.Time) time.Time {
	utc := t.UTC()
	return time.Date(utc.Year(), utc.Month(), utc.Day(), 0, 0, 0, 0, time.UTC)
}

func compareIntersectionListRank(a, b IntersectionReasonView) int {
	if a.Strength != b.Strength {
		if a.Strength > b.Strength {
			return -1
		}
		return 1
	}
	if ap, bp := intersectionListTimeBucketPriority(a), intersectionListTimeBucketPriority(b); ap != bp {
		if ap < bp {
			return -1
		}
		return 1
	}
	if a.AnchorUserWeight != b.AnchorUserWeight {
		if a.AnchorUserWeight > b.AnchorUserWeight {
			return -1
		}
		return 1
	}
	if cmp := compareEdgeWeight(a, b); cmp != 0 {
		return cmp
	}
	if a.TotalPointCount != b.TotalPointCount {
		if a.TotalPointCount > b.TotalPointCount {
			return -1
		}
		return 1
	}
	if a.MutualCount != b.MutualCount {
		if a.MutualCount > b.MutualCount {
			return -1
		}
		return 1
	}
	return strings.Compare(stableIntersectionListKey(a), stableIntersectionListKey(b))
}

// compareEdgeWeight 让物化边权参与排序：边权大的在前，返回 -1/0/1。
//
// edgeWeight = relationStrength × interactionFrequency × recencyDecay，由
// intersection_graph_materializer 异步真算并随快照落库。它排在语义序（已看过 /
// 事实优先 / kind 锚强度 / Strength）之后、裸计数之前：语义序表达「该不该先看」，
// 边权表达「同等语义下哪条边更实」，裸计数只是边权的一个因子，不该盖过复合信号。
//
// 请求期直算的 reason 没有物化边权（0），此时本比较返回 0 并原样落到既有键上，
// 因此混排不会因为「有没有被物化过」而改变既有顺序。
func compareEdgeWeight(a, b IntersectionReasonView) int {
	if a.EdgeWeight == b.EdgeWeight {
		return 0
	}
	if a.EdgeWeight > b.EdgeWeight {
		return -1
	}
	return 1
}

func intersectionListTimeBucketPriority(r IntersectionReasonView) int {
	switch strings.TrimSpace(r.TimeBucket) {
	case "today":
		return 0
	case "yesterday":
		return 1
	case "last7Days":
		return 2
	case "thisMonth":
		return 3
	case "lastMonth":
		return 4
	default:
		return 5
	}
}

func stableIntersectionListKey(r IntersectionReasonView) string {
	if key := strings.TrimSpace(r.DedupeKey); key != "" {
		return key
	}
	return strings.Join([]string{
		strings.TrimSpace(r.ActionTargetID),
		strings.TrimSpace(r.RelationObjectID),
		strings.TrimSpace(r.ObjectKind),
		strings.TrimSpace(r.Kind),
		strings.TrimSpace(r.IntersectionID),
	}, ":")
}

func matchesIntersectionListQuery(r IntersectionReasonView, query IntersectionListQuery, wm map[string]int64) bool {
	dimension := strings.TrimSpace(query.Dimension)
	if dimension != "" && !reasonHasDimension(r, dimension) {
		return false
	}
	timeBucket := strings.TrimSpace(query.TimeBucket)
	if timeBucket != "" && r.TimeBucket != timeBucket {
		return false
	}
	sourceRef := strings.TrimSpace(query.SourceRef)
	if sourceRef != "" && !reasonHasSourceRef(r, sourceRef) {
		return false
	}
	switch strings.TrimSpace(query.Filter) {
	case "", "all":
		return true
	case "new":
		return freshUnix(r) > wm[r.Dimension]
	case "fact":
		return r.IntersectionClass == "" || r.IntersectionClass == "fact"
	case "affinity", "recommended":
		return r.IntersectionClass == "affinity"
	default:
		return true
	}
}

func reasonHasSourceRef(r IntersectionReasonView, sourceRef string) bool {
	if r.Source == sourceRef {
		return true
	}
	for _, point := range r.IntersectionPoints {
		if point.SourceRef == sourceRef {
			return true
		}
	}
	return false
}

// reasonHasDimension 与 Summary 的维度计数同源：Summary 按可见 point 的维度分桶
// （point.Dimension 缺省回落 reason.Dimension），List 的维度下钻必须用同一谓词，
// 否则「地点 1」红点下钻到空列表（计数-可见一致合同）。
func reasonHasDimension(r IntersectionReasonView, dimension string) bool {
	if r.Dimension == dimension {
		return true
	}
	for _, point := range r.IntersectionPoints {
		dim := point.Dimension
		if dim == "" {
			dim = r.Dimension
		}
		if dim == dimension {
			return true
		}
	}
	return false
}

func decodeIntersectionListCursor(cursor string) int {
	cursor = strings.TrimSpace(cursor)
	if cursor == "" {
		return 0
	}
	n, err := strconv.Atoi(cursor)
	if err != nil || n < 0 {
		return 0
	}
	return n
}
