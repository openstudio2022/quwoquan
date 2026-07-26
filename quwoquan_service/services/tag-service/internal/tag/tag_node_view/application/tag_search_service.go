package application

import (
	"context"
	"sort"
	"strings"
)

// relatedScanCap 限制 TagNodeView 的 related / cooccurrence / related-objects 倒排扫描规模，
// 防止单标签热点对象集导致 O(N·k) 在线计算失控（启动子集足够，规模化由数据工程预算共现表）。
const relatedScanCap = 500

// TagSearchResultView 对齐 operations.yaml SearchTags 响应。
type TagSearchResultView struct {
	TagRef string  `json:"tagRef"`
	Label  string  `json:"label"`
	Score  float64 `json:"score"`
}

// RelatedTagView 对齐 operations.yaml RelatedTags 响应。
type RelatedTagView struct {
	TagRef       string `json:"tagRef"`
	Label        string `json:"label"`
	CooccurCount int    `json:"cooccurCount"`
}

// TagObjectMatchView 对齐 operations.yaml SearchByTags 响应。
type TagObjectMatchView struct {
	ObjectID    string   `json:"objectId"`
	ObjectType  string   `json:"objectType"`
	MatchedTags []string `json:"matchedTags"`
	Score       float64  `json:"score"`
}

// TagCooccurrenceView 对齐 operations.yaml TagCooccurrence 响应。
type TagCooccurrenceView struct {
	TagA         string `json:"tagA"`
	TagB         string `json:"tagB"`
	CooccurCount int    `json:"cooccurCount"`
}

// RelatedObjectView 对齐 operations.yaml RelatedObjects 响应。
type RelatedObjectView struct {
	ObjectID    string   `json:"objectId"`
	ObjectType  string   `json:"objectType"`
	SharedTags  []string `json:"sharedTags"`
	SharedCount int      `json:"sharedCount"`
}

// SearchTags 标签全文搜索：复用 Suggest 的匹配排名，归一化为 score（命中越精确分越高）。
func (s *TagService) SearchTags(ctx context.Context, query, group string, limit int) ([]TagSearchResultView, error) {
	query = strings.TrimSpace(query)
	group = strings.TrimSpace(group)
	if limit <= 0 {
		limit = 20
	}
	if query == "" {
		return []TagSearchResultView{}, nil
	}
	releaseID, found, err := s.activeReleaseID(ctx)
	if err != nil {
		return nil, err
	}
	if !found {
		return []TagSearchResultView{}, nil
	}
	nodes, err := s.nodes.ListAllInRelease(ctx, releaseID)
	if err != nil {
		return nil, err
	}
	queryLower := strings.ToLower(query)
	type ranked struct {
		view TagSearchResultView
		rank int
	}
	matches := make([]ranked, 0, len(nodes))
	for _, node := range nodes {
		if group != "" && node.Group != group {
			continue
		}
		if node.TagRef == "" || node.Label == "" {
			continue
		}
		if sv, rank, ok := buildTagSuggestionView(node, query, queryLower); ok {
			matches = append(matches, ranked{
				view: TagSearchResultView{
					TagRef: sv.TagRef,
					Label:  sv.Label,
					Score:  1.0 / (1.0 + float64(rank)),
				},
				rank: rank,
			})
		}
	}
	sort.SliceStable(matches, func(i, j int) bool {
		if matches[i].rank != matches[j].rank {
			return matches[i].rank < matches[j].rank
		}
		if matches[i].view.Label != matches[j].view.Label {
			return matches[i].view.Label < matches[j].view.Label
		}
		return matches[i].view.TagRef < matches[j].view.TagRef
	})
	if len(matches) > limit {
		matches = matches[:limit]
	}
	out := make([]TagSearchResultView, 0, len(matches))
	for _, m := range matches {
		out = append(out, m.view)
	}
	return out, nil
}

// cooccurrenceCounts 统计与 tagRef 共现的标签计数（扫描引用 tagRef 的对象，剔除自身）。
func (s *TagService) cooccurrenceCounts(ctx context.Context, tagRef string) (map[string]int, error) {
	idxs, err := s.objects.FindObjectsByTagRef(ctx, tagRef, "", relatedScanCap)
	if err != nil {
		return nil, err
	}
	counts := make(map[string]int)
	for _, idx := range idxs {
		for _, t := range idx.TagRefs {
			if t == "" || t == tagRef {
				continue
			}
			counts[t]++
		}
	}
	return counts, nil
}

// RelatedTags 返回与 tagRef 共现度最高的相关标签（在线计算，受 relatedScanCap 约束）。
func (s *TagService) RelatedTags(ctx context.Context, tagRef string, limit int) ([]RelatedTagView, error) {
	tagRef = strings.TrimSpace(tagRef)
	if limit <= 0 {
		limit = 20
	}
	out := make([]RelatedTagView, 0)
	if tagRef == "" {
		return out, nil
	}
	releaseID, found, err := s.activeReleaseID(ctx)
	if err != nil {
		return nil, err
	}
	if !found {
		return out, nil
	}
	anchor, err := s.nodes.FindByReleaseAndTagRef(ctx, releaseID, tagRef)
	if err != nil {
		return nil, err
	}
	if anchor == nil || anchor.LifecycleStatus != "active" {
		return out, nil
	}
	counts, err := s.cooccurrenceCounts(ctx, tagRef)
	if err != nil {
		return nil, err
	}
	for t, c := range counts {
		node, nodeErr := s.nodes.FindByReleaseAndTagRef(ctx, releaseID, t)
		if nodeErr != nil {
			return nil, nodeErr
		}
		if node == nil || node.LifecycleStatus != "active" {
			continue
		}
		view := RelatedTagView{TagRef: t, Label: node.Label, CooccurCount: c}
		out = append(out, view)
	}
	sortRelatedTags(out)
	if len(out) > limit {
		out = out[:limit]
	}
	return out, nil
}

// TagCooccurrence 查询以 tagRef 为锚的标签对共现关系（>= minCount）。
func (s *TagService) TagCooccurrence(ctx context.Context, tagRef string, minCount, limit int) ([]TagCooccurrenceView, error) {
	tagRef = strings.TrimSpace(tagRef)
	if limit <= 0 {
		limit = 20
	}
	if minCount < 0 {
		minCount = 0
	}
	out := make([]TagCooccurrenceView, 0)
	if tagRef == "" {
		return out, nil
	}
	releaseID, found, err := s.activeReleaseID(ctx)
	if err != nil {
		return nil, err
	}
	if !found {
		return out, nil
	}
	anchor, err := s.nodes.FindByReleaseAndTagRef(ctx, releaseID, tagRef)
	if err != nil {
		return nil, err
	}
	if anchor == nil || anchor.LifecycleStatus != "active" {
		return out, nil
	}
	counts, err := s.cooccurrenceCounts(ctx, tagRef)
	if err != nil {
		return nil, err
	}
	pairs := make([]TagCooccurrenceView, 0, len(counts))
	for t, c := range counts {
		if c < minCount {
			continue
		}
		node, nodeErr := s.nodes.FindByReleaseAndTagRef(ctx, releaseID, t)
		if nodeErr != nil {
			return nil, nodeErr
		}
		if node == nil || node.LifecycleStatus != "active" {
			continue
		}
		pairs = append(pairs, TagCooccurrenceView{TagA: tagRef, TagB: t, CooccurCount: c})
	}
	sort.SliceStable(pairs, func(i, j int) bool {
		if pairs[i].CooccurCount != pairs[j].CooccurCount {
			return pairs[i].CooccurCount > pairs[j].CooccurCount
		}
		return pairs[i].TagB < pairs[j].TagB
	})
	if len(pairs) > limit {
		pairs = pairs[:limit]
	}
	return append(out, pairs...), nil
}

// SearchByTags 多标签联合搜索对象：按对象聚合命中标签，score = 命中数 / 查询标签数。
func (s *TagService) SearchByTags(ctx context.Context, tagRefs []string, objectType string, limit int) ([]TagObjectMatchView, error) {
	if limit <= 0 {
		limit = 20
	}
	uniq := dedupeNonEmpty(tagRefs)
	out := make([]TagObjectMatchView, 0)
	if len(uniq) == 0 {
		return out, nil
	}
	releaseID, found, err := s.activeReleaseID(ctx)
	if err != nil {
		return nil, err
	}
	if !found {
		return out, nil
	}
	activeRefs := make([]string, 0, len(uniq))
	for _, tagRef := range uniq {
		node, nodeErr := s.nodes.FindByReleaseAndTagRef(ctx, releaseID, tagRef)
		if nodeErr != nil {
			return nil, nodeErr
		}
		if node != nil && node.LifecycleStatus == "active" {
			activeRefs = append(activeRefs, tagRef)
		}
	}
	uniq = activeRefs
	if len(uniq) == 0 {
		return out, nil
	}
	type agg struct {
		objectType string
		matched    []string
	}
	byObject := make(map[string]*agg)
	for _, t := range uniq {
		idxs, err := s.objects.FindObjectsByTagRef(ctx, t, objectType, relatedScanCap)
		if err != nil {
			return nil, err
		}
		for _, idx := range idxs {
			a, ok := byObject[idx.ObjectID]
			if !ok {
				a = &agg{objectType: idx.ObjectType}
				byObject[idx.ObjectID] = a
			}
			a.matched = append(a.matched, t)
		}
	}
	total := float64(len(uniq))
	for id, a := range byObject {
		sort.Strings(a.matched)
		out = append(out, TagObjectMatchView{
			ObjectID:    id,
			ObjectType:  a.objectType,
			MatchedTags: a.matched,
			Score:       float64(len(a.matched)) / total,
		})
	}
	sort.SliceStable(out, func(i, j int) bool {
		if out[i].Score != out[j].Score {
			return out[i].Score > out[j].Score
		}
		return out[i].ObjectID < out[j].ObjectID
	})
	if len(out) > limit {
		out = out[:limit]
	}
	return out, nil
}

// RelatedObjects 通过共享标签查找相关对象：取自身 tagRefs 倒排聚合，sharedCount 降序。
func (s *TagService) RelatedObjects(ctx context.Context, objectID, objectType string, limit int) ([]RelatedObjectView, error) {
	objectID = strings.TrimSpace(objectID)
	if limit <= 0 {
		limit = 20
	}
	out := make([]RelatedObjectView, 0)
	if objectID == "" {
		return out, nil
	}
	releaseID, found, err := s.activeReleaseID(ctx)
	if err != nil {
		return nil, err
	}
	if !found {
		return out, nil
	}
	self, err := s.objects.FindByObject(ctx, objectID, objectType)
	if err != nil {
		return nil, err
	}
	if self == nil {
		return out, nil
	}
	type agg struct {
		objectType string
		shared     []string
	}
	byObject := make(map[string]*agg)
	for _, t := range self.TagRefs {
		if t == "" {
			continue
		}
		node, nodeErr := s.nodes.FindByReleaseAndTagRef(ctx, releaseID, t)
		if nodeErr != nil {
			return nil, nodeErr
		}
		if node == nil || node.LifecycleStatus != "active" {
			continue
		}
		idxs, err := s.objects.FindObjectsByTagRef(ctx, t, "", relatedScanCap)
		if err != nil {
			return nil, err
		}
		for _, idx := range idxs {
			if idx.ObjectID == objectID {
				continue
			}
			a, ok := byObject[idx.ObjectID]
			if !ok {
				a = &agg{objectType: idx.ObjectType}
				byObject[idx.ObjectID] = a
			}
			a.shared = append(a.shared, t)
		}
	}
	for id, a := range byObject {
		sort.Strings(a.shared)
		out = append(out, RelatedObjectView{
			ObjectID:    id,
			ObjectType:  a.objectType,
			SharedTags:  a.shared,
			SharedCount: len(a.shared),
		})
	}
	sort.SliceStable(out, func(i, j int) bool {
		if out[i].SharedCount != out[j].SharedCount {
			return out[i].SharedCount > out[j].SharedCount
		}
		return out[i].ObjectID < out[j].ObjectID
	})
	if len(out) > limit {
		out = out[:limit]
	}
	return out, nil
}

func sortRelatedTags(out []RelatedTagView) {
	sort.SliceStable(out, func(i, j int) bool {
		if out[i].CooccurCount != out[j].CooccurCount {
			return out[i].CooccurCount > out[j].CooccurCount
		}
		return out[i].TagRef < out[j].TagRef
	})
}

func dedupeNonEmpty(in []string) []string {
	seen := make(map[string]bool, len(in))
	out := make([]string, 0, len(in))
	for _, raw := range in {
		t := strings.TrimSpace(raw)
		if t == "" || seen[t] {
			continue
		}
		seen[t] = true
		out = append(out, t)
	}
	return out
}
