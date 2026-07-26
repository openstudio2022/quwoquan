package application

import (
	"context"
	"errors"
	"sort"
	"strings"

	model "quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/model"
	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/ports"
	releaseports "quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/domain/taxonomyrelease/ports"
)

var ErrTagParentNotFound = errors.New("parent tagRef not found")

// TagResolveView 对齐 operations.yaml ResolveTag 响应。
type TagResolveView struct {
	TagRef    string   `json:"tagRef"`
	Group     string   `json:"group"`
	Label     string   `json:"label"`
	LabelEn   string   `json:"labelEn"`
	Aliases   []string `json:"aliases"`
	Ancestors []string `json:"ancestors"`
}

// TagChildView 对齐 operations.yaml ListTagChildren 响应。
type TagChildView struct {
	TagRef          string `json:"tagRef"`
	Label           string `json:"label"`
	DisplayLabel    string `json:"displayLabel"`
	LabelEn         string `json:"labelEn"`
	ParentTagRef    string `json:"parentTagRef"`
	Depth           int    `json:"depth"`
	HasChildren     bool   `json:"hasChildren"`
	ReleaseID       string `json:"releaseId"`
	LifecycleStatus string `json:"lifecycleStatus"`
}

// SharedTagView 对齐 operations.yaml SharedTags 响应（交集锚点）。
type SharedTagView struct {
	TagRef   string  `json:"tagRef"`
	Label    string  `json:"label"`
	Strength float64 `json:"strength"`
	Source   string  `json:"source"`
}

// InvertedObjectsView 对齐 operations.yaml InvertedObjects 响应。
type InvertedObjectsView struct {
	TagRef      string   `json:"tagRef"`
	ObjectCount int      `json:"objectCount"`
	ObjectIds   []string `json:"objectIds"`
}

// TagDimensionView 对齐 operations.yaml ListDimensions 响应。
type TagDimensionView struct {
	Group       string `json:"group"`
	DimensionID string `json:"dimensionId"`
	Label       string `json:"label"`
	LabelEn     string `json:"labelEn"`
	MaxDepth    int    `json:"maxDepth"`
	PathPolicy  string `json:"pathPolicy"`
}

// TagSuggestionView 对齐 operations.yaml SuggestTags 响应。
type TagSuggestionView struct {
	TagRef     string `json:"tagRef"`
	Label      string `json:"label"`
	LabelEn    string `json:"labelEn"`
	MatchField string `json:"matchField"`
}

// TagValidationResultView 对齐 operations.yaml ValidateTagRefs 响应。
type TagValidationResultView struct {
	TaxonomyReleaseID string   `json:"taxonomyReleaseId"`
	Valid             []string `json:"valid"`
	Invalid           []string `json:"invalid"`
}

// TagService 提供交集核心与创作打标只读用例。
type TagService struct {
	nodes    ports.TagNodeReader
	objects  ports.ObjectTagIndexReader
	releases releaseports.ActiveReleaseReader
}

// NewTagService 注入只读存储依赖。
func NewTagService(
	nodes ports.TagNodeReader,
	objects ports.ObjectTagIndexReader,
	releases releaseports.ActiveReleaseReader,
) *TagService {
	return &TagService{nodes: nodes, objects: objects, releases: releases}
}

func (s *TagService) activeReleaseID(ctx context.Context) (string, bool, error) {
	return s.releases.ActiveReleaseID(ctx)
}

// Resolve 解析单个 tagRef → 标签定义；未命中返回 (nil, nil)。
func (s *TagService) Resolve(ctx context.Context, tagRef string) (*TagResolveView, error) {
	releaseID, found, err := s.activeReleaseID(ctx)
	if err != nil {
		return nil, err
	}
	if !found {
		return nil, nil
	}
	node, err := s.nodes.FindByReleaseAndTagRef(ctx, releaseID, tagRef)
	if err != nil {
		return nil, err
	}
	if node == nil || node.LifecycleStatus != "active" {
		return nil, nil
	}
	return &TagResolveView{
		TagRef:    node.TagRef,
		Group:     node.Group,
		Label:     node.Label,
		LabelEn:   node.LabelEn,
		Aliases:   node.Aliases,
		Ancestors: node.Ancestors,
	}, nil
}

// ListChildren 列出 active 直接子节点；parent 不存在时返回 ErrTagParentNotFound。
func (s *TagService) ListChildren(ctx context.Context, parentTagRef string, limit int) ([]TagChildView, error) {
	parentTagRef = strings.TrimSpace(parentTagRef)
	if parentTagRef == "" {
		return []TagChildView{}, nil
	}
	if limit <= 0 || limit > 500 {
		limit = 500
	}
	releaseID, found, err := s.activeReleaseID(ctx)
	if err != nil {
		return nil, err
	}
	if !found {
		return nil, ErrTagParentNotFound
	}
	parent, err := s.nodes.FindByReleaseAndTagRef(ctx, releaseID, parentTagRef)
	if err != nil {
		return nil, err
	}
	if parent == nil || parent.LifecycleStatus != "active" {
		return nil, ErrTagParentNotFound
	}
	children, err := s.nodes.ListChildrenInRelease(ctx, releaseID, parentTagRef, int64(limit))
	if err != nil {
		return nil, err
	}
	out := make([]TagChildView, 0, len(children))
	for _, child := range children {
		count, err := s.nodes.CountActiveChildrenInRelease(ctx, releaseID, child.TagRef)
		if err != nil {
			return nil, err
		}
		displayLabel := strings.TrimSpace(child.DisplayLabel)
		if displayLabel == "" {
			displayLabel = strings.TrimSpace(child.Label)
		}
		out = append(out, TagChildView{
			TagRef:          child.TagRef,
			Label:           child.Label,
			DisplayLabel:    displayLabel,
			LabelEn:         child.LabelEn,
			ParentTagRef:    child.ParentTagRef,
			Depth:           child.Depth,
			HasChildren:     count > 0,
			ReleaseID:       child.ReleaseID,
			LifecycleStatus: child.LifecycleStatus,
		})
	}
	return out, nil
}

// ListDimensions returns dimensions from the active immutable taxonomy
// snapshot, keeping control-plane metadata as the only catalog source.
func (s *TagService) ListDimensions(ctx context.Context) ([]TagDimensionView, error) {
	releaseID, found, err := s.activeReleaseID(ctx)
	if err != nil {
		return nil, err
	}
	if !found {
		return []TagDimensionView{}, nil
	}
	nodes, err := s.nodes.ListDimensionsInRelease(ctx, releaseID)
	if err != nil {
		return nil, err
	}
	out := make([]TagDimensionView, 0, len(nodes))
	for _, node := range nodes {
		out = append(out, TagDimensionView{
			Group:       node.Group,
			DimensionID: node.TagRef,
			Label:       node.Label,
			LabelEn:     node.LabelEn,
			MaxDepth:    node.MaxDepth,
			PathPolicy:  node.PathPolicy,
		})
	}
	return out, nil
}

// Suggest 根据关键词做标签建议；group 为空时跨组查询。
func (s *TagService) Suggest(ctx context.Context, query, group string, limit int) ([]TagSuggestionView, error) {
	query = strings.TrimSpace(query)
	group = strings.TrimSpace(group)
	if limit <= 0 {
		limit = 20
	}
	if query == "" {
		return []TagSuggestionView{}, nil
	}
	releaseID, found, err := s.activeReleaseID(ctx)
	if err != nil {
		return nil, err
	}
	if !found {
		return []TagSuggestionView{}, nil
	}
	nodes, err := s.nodes.ListAllInRelease(ctx, releaseID)
	if err != nil {
		return nil, err
	}
	queryLower := strings.ToLower(query)
	type rankedSuggestion struct {
		view TagSuggestionView
		rank int
	}
	matches := make([]rankedSuggestion, 0, len(nodes))
	for _, node := range nodes {
		if group != "" && node.Group != group {
			continue
		}
		if node.TagRef == "" || node.Label == "" {
			continue
		}
		if view, rank, ok := buildTagSuggestionView(node, query, queryLower); ok {
			matches = append(matches, rankedSuggestion{view: view, rank: rank})
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
	out := make([]TagSuggestionView, 0, len(matches))
	for _, match := range matches {
		out = append(out, match.view)
	}
	return out, nil
}

// ValidateTagRefs validates only active leaves in the caller's expected release.
// It preserves input order and queries every distinct, non-empty tagRef at most once.
func (s *TagService) ValidateTagRefs(
	ctx context.Context,
	expectedReleaseID string,
	tagRefs []string,
) (*TagValidationResultView, error) {
	valid := make([]string, 0, len(tagRefs))
	invalid := make([]string, 0)
	expectedReleaseID = strings.TrimSpace(expectedReleaseID)
	releaseID, activeFound, err := s.activeReleaseID(ctx)
	if err != nil {
		return nil, err
	}
	releaseMatches := activeFound && expectedReleaseID != "" && releaseID == expectedReleaseID
	cache := make(map[string]bool, len(tagRefs))
	for _, raw := range tagRefs {
		tagRef := strings.TrimSpace(raw)
		if tagRef == "" {
			invalid = append(invalid, raw)
			continue
		}
		if !releaseMatches {
			invalid = append(invalid, tagRef)
			continue
		}
		exists, ok := cache[tagRef]
		if !ok {
			exists, err = s.nodes.IsActiveLeaf(ctx, releaseID, tagRef)
			if err != nil {
				return nil, err
			}
			cache[tagRef] = exists
		}
		if exists {
			valid = append(valid, tagRef)
			continue
		}
		invalid = append(invalid, tagRef)
	}
	return &TagValidationResultView{
		TaxonomyReleaseID: releaseID,
		Valid:             valid,
		Invalid:           invalid,
	}, nil
}

// TagRefExists allows sibling command composition to validate against the
// current active snapshot without coupling TagNodeView to release infrastructure.
func (s *TagService) TagRefExists(ctx context.Context, tagRef string) (bool, error) {
	tagRef = strings.TrimSpace(tagRef)
	if tagRef == "" {
		return false, nil
	}
	releaseID, found, err := s.activeReleaseID(ctx)
	if err != nil || !found {
		return false, err
	}
	node, err := s.nodes.FindByReleaseAndTagRef(ctx, releaseID, tagRef)
	if err != nil {
		return false, err
	}
	return node != nil && node.LifecycleStatus == "active", nil
}

// SharedTags 计算两个对象共享的 tagRef（交集锚点 + 标签富化）。
func (s *TagService) SharedTags(ctx context.Context, aID, aType, bID, bType string, limit int) ([]SharedTagView, error) {
	releaseID, found, err := s.activeReleaseID(ctx)
	if err != nil {
		return nil, err
	}
	a, err := s.objects.FindByObject(ctx, aID, aType)
	if err != nil {
		return nil, err
	}
	b, err := s.objects.FindByObject(ctx, bID, bType)
	if err != nil {
		return nil, err
	}
	out := make([]SharedTagView, 0)
	if !found || a == nil || b == nil {
		return out, nil
	}
	bset := make(map[string]bool, len(b.TagRefs))
	for _, t := range b.TagRefs {
		bset[t] = true
	}
	for _, t := range a.TagRefs {
		if !bset[t] {
			continue
		}
		node, nodeErr := s.nodes.FindByReleaseAndTagRef(ctx, releaseID, t)
		if nodeErr != nil {
			return nil, nodeErr
		}
		if node == nil || node.LifecycleStatus != "active" {
			continue
		}
		view := SharedTagView{TagRef: t, Label: node.Label, Strength: 1, Source: "tagRef"}
		out = append(out, view)
	}
	sort.SliceStable(out, func(i, j int) bool { return out[i].TagRef < out[j].TagRef })
	if limit > 0 && len(out) > limit {
		out = out[:limit]
	}
	return out, nil
}

// Inverted 返回引用某 tagRef 的对象集合。includeDescendants=true 时按路径制
// 子孙标签展开聚合（省/市级 geo 标签反查含全部区县级叶子对象；查询侧展开，
// 存储不物化祖先链）。
func (s *TagService) Inverted(ctx context.Context, tagRef, objectType string, limit int, includeDescendants bool) (*InvertedObjectsView, error) {
	releaseID, found, err := s.activeReleaseID(ctx)
	if err != nil {
		return nil, err
	}
	if !found {
		return &InvertedObjectsView{TagRef: tagRef, ObjectIds: []string{}}, nil
	}
	node, err := s.nodes.FindByReleaseAndTagRef(ctx, releaseID, tagRef)
	if err != nil {
		return nil, err
	}
	if node == nil || node.LifecycleStatus != "active" {
		return &InvertedObjectsView{TagRef: tagRef, ObjectIds: []string{}}, nil
	}
	var idxs []model.ObjectTagIndex
	if includeDescendants {
		idxs, err = s.objects.FindObjectsByTagRefSubtree(ctx, tagRef, objectType, int64(limit))
	} else {
		idxs, err = s.objects.FindObjectsByTagRef(ctx, tagRef, objectType, int64(limit))
	}
	if err != nil {
		return nil, err
	}
	ids := make([]string, 0, len(idxs))
	seen := make(map[string]bool, len(idxs))
	for _, x := range idxs {
		if seen[x.ObjectID] {
			continue
		}
		seen[x.ObjectID] = true
		ids = append(ids, x.ObjectID)
	}
	return &InvertedObjectsView{TagRef: tagRef, ObjectCount: len(ids), ObjectIds: ids}, nil
}

func buildTagSuggestionView(node model.TagNode, query, queryLower string) (TagSuggestionView, int, bool) {
	label := strings.TrimSpace(node.Label)
	labelEn := strings.TrimSpace(node.LabelEn)
	tagRef := strings.TrimSpace(node.TagRef)
	aliases := splitTagAliases(node.Aliases)
	lowerLabel := strings.ToLower(label)
	lowerLabelEn := strings.ToLower(labelEn)
	lowerTagRef := strings.ToLower(tagRef)

	switch {
	case label == query:
		return TagSuggestionView{TagRef: tagRef, Label: label, LabelEn: labelEn, MatchField: "label"}, 0, true
	case strings.HasPrefix(lowerLabel, queryLower):
		return TagSuggestionView{TagRef: tagRef, Label: label, LabelEn: labelEn, MatchField: "label"}, 1, true
	case strings.Contains(lowerLabel, queryLower):
		return TagSuggestionView{TagRef: tagRef, Label: label, LabelEn: labelEn, MatchField: "label"}, 2, true
	case labelEn != "" && strings.EqualFold(labelEn, query):
		return TagSuggestionView{TagRef: tagRef, Label: label, LabelEn: labelEn, MatchField: "labelEn"}, 3, true
	case labelEn != "" && strings.HasPrefix(lowerLabelEn, queryLower):
		return TagSuggestionView{TagRef: tagRef, Label: label, LabelEn: labelEn, MatchField: "labelEn"}, 4, true
	case labelEn != "" && strings.Contains(lowerLabelEn, queryLower):
		return TagSuggestionView{TagRef: tagRef, Label: label, LabelEn: labelEn, MatchField: "labelEn"}, 5, true
	case tagRef == query:
		return TagSuggestionView{TagRef: tagRef, Label: label, LabelEn: labelEn, MatchField: "tagRef"}, 6, true
	case strings.HasPrefix(lowerTagRef, queryLower):
		return TagSuggestionView{TagRef: tagRef, Label: label, LabelEn: labelEn, MatchField: "tagRef"}, 7, true
	case strings.Contains(lowerTagRef, queryLower):
		return TagSuggestionView{TagRef: tagRef, Label: label, LabelEn: labelEn, MatchField: "tagRef"}, 8, true
	}

	for _, alias := range aliases {
		lowerAlias := strings.ToLower(alias)
		switch {
		case alias == query:
			return TagSuggestionView{TagRef: tagRef, Label: label, LabelEn: labelEn, MatchField: "alias"}, 9, true
		case strings.HasPrefix(lowerAlias, queryLower):
			return TagSuggestionView{TagRef: tagRef, Label: label, LabelEn: labelEn, MatchField: "alias"}, 10, true
		case strings.Contains(lowerAlias, queryLower):
			return TagSuggestionView{TagRef: tagRef, Label: label, LabelEn: labelEn, MatchField: "alias"}, 11, true
		}
	}
	return TagSuggestionView{}, 0, false
}

func splitTagAliases(raw []string) []string {
	aliases := make([]string, 0, len(raw))
	for _, alias := range raw {
		if normalized := strings.TrimSpace(alias); normalized != "" {
			aliases = append(aliases, normalized)
		}
	}
	return aliases
}
