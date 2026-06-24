package application

import (
	"context"
	"errors"
	"sort"
	"strings"

	model "quwoquan_service/services/tag-service/internal/domain/tag/model"
	"quwoquan_service/services/tag-service/internal/domain/tag/repository"
)

var ErrTagParentNotFound = errors.New("parent tagRef not found")

// TagResolveView 对齐 service.yaml ResolveTag 响应。
type TagResolveView struct {
	TagRef    string `json:"tagRef"`
	Group     string `json:"group"`
	Label     string `json:"label"`
	LabelEn   string `json:"labelEn"`
	Aliases   string `json:"aliases"`
	Ancestors string `json:"ancestors"`
}

// TagChildView 对齐 service.yaml ListTagChildren 响应。
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

// SharedTagView 对齐 service.yaml SharedTags 响应（交集锚点）。
type SharedTagView struct {
	TagRef   string  `json:"tagRef"`
	Label    string  `json:"label"`
	Strength float64 `json:"strength"`
	Source   string  `json:"source"`
}

// InvertedObjectsView 对齐 service.yaml InvertedObjects 响应。
type InvertedObjectsView struct {
	TagRef      string   `json:"tagRef"`
	ObjectCount int      `json:"objectCount"`
	ObjectIds   []string `json:"objectIds"`
}

// TagDimensionView 对齐 service.yaml ListDimensions 响应。
type TagDimensionView struct {
	Group       string `json:"group"`
	DimensionID string `json:"dimensionId"`
	Label       string `json:"label"`
	LabelEn     string `json:"labelEn"`
	MaxDepth    int    `json:"maxDepth"`
	PathPolicy  string `json:"pathPolicy"`
}

// TagSuggestionView 对齐 service.yaml SuggestTags 响应。
type TagSuggestionView struct {
	TagRef     string `json:"tagRef"`
	Label      string `json:"label"`
	LabelEn    string `json:"labelEn"`
	MatchField string `json:"matchField"`
}

// TagValidationResultView 对齐 service.yaml ValidateTagRefs 响应。
type TagValidationResultView struct {
	Valid   []string `json:"valid"`
	Invalid []string `json:"invalid"`
}

var tagDimensionCatalog = []TagDimensionView{
	{Group: "Topic", DimensionID: "Topic/主题", Label: "主题垂类", LabelEn: "Topic Vertical", MaxDepth: 4, PathPolicy: "any-depth"},
	{Group: "Topic", DimensionID: "Topic/场景", Label: "场景", LabelEn: "Scene", MaxDepth: 3, PathPolicy: "prefer-leaf"},
	{Group: "Topic", DimensionID: "Topic/事件话题", Label: "事件话题", LabelEn: "Trending Topics", MaxDepth: 3, PathPolicy: "any-depth"},
	{Group: "Topic", DimensionID: "Topic/时间", Label: "时间", LabelEn: "Time Dimension", MaxDepth: 3, PathPolicy: "prefer-leaf"},
	{Group: "Topic", DimensionID: "Topic/地理", Label: "地理", LabelEn: "Geography", MaxDepth: 5, PathPolicy: "any-depth"},
	{Group: "Audience", DimensionID: "Audience/用户", Label: "用户画像", LabelEn: "User Profile", MaxDepth: 4, PathPolicy: "leaf-only"},
	{Group: "Audience", DimensionID: "Audience/创作者", Label: "创作者", LabelEn: "Creator", MaxDepth: 3, PathPolicy: "any-depth"},
	{Group: "Audience", DimensionID: "Audience/商品", Label: "商品画像", LabelEn: "Product Profile", MaxDepth: 3, PathPolicy: "any-depth"},
	{Group: "Audience", DimensionID: "Audience/圈子", Label: "圈子画像", LabelEn: "Circle Profile", MaxDepth: 3, PathPolicy: "any-depth"},
	{Group: "Format", DimensionID: "Format/内容载体", Label: "内容载体", LabelEn: "Content Medium", MaxDepth: 3, PathPolicy: "prefer-leaf"},
	{Group: "Format", DimensionID: "Format/内容角度", Label: "内容角度", LabelEn: "Content Angle", MaxDepth: 3, PathPolicy: "any-depth"},
	{Group: "Format", DimensionID: "Format/表现手法", Label: "表现手法", LabelEn: "Production Technique", MaxDepth: 3, PathPolicy: "any-depth"},
	{Group: "Format", DimensionID: "Format/视觉风格", Label: "视觉风格", LabelEn: "Visual Style", MaxDepth: 3, PathPolicy: "any-depth"},
	{Group: "Entity", DimensionID: "Entity/地点", Label: "地点", LabelEn: "Place", MaxDepth: 3, PathPolicy: "any-depth"},
	{Group: "Entity", DimensionID: "Entity/机构", Label: "机构", LabelEn: "Organization", MaxDepth: 2, PathPolicy: "any-depth"},
	{Group: "Entity", DimensionID: "Entity/活动", Label: "活动", LabelEn: "Event", MaxDepth: 2, PathPolicy: "any-depth"},
	{Group: "Entity", DimensionID: "Entity/人物", Label: "人物", LabelEn: "Person", MaxDepth: 3, PathPolicy: "any-depth"},
	{Group: "Entity", DimensionID: "Entity/品牌", Label: "品牌", LabelEn: "Brand", MaxDepth: 3, PathPolicy: "any-depth"},
}

// TagService 提供交集核心与创作打标只读用例。
type TagService struct {
	nodes   repository.TagNodeReader
	objects repository.ObjectTagIndexReader
}

// NewTagService 注入只读存储依赖。
func NewTagService(nodes repository.TagNodeReader, objects repository.ObjectTagIndexReader) *TagService {
	return &TagService{nodes: nodes, objects: objects}
}

// Resolve 解析单个 tagRef → 标签定义；未命中返回 (nil, nil)。
func (s *TagService) Resolve(ctx context.Context, tagRef string) (*TagResolveView, error) {
	node, err := s.nodes.FindByTagRef(ctx, tagRef)
	if err != nil {
		return nil, err
	}
	if node == nil {
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
	parent, err := s.nodes.FindByTagRef(ctx, parentTagRef)
	if err != nil {
		return nil, err
	}
	if parent == nil {
		return nil, ErrTagParentNotFound
	}
	children, err := s.nodes.ListChildren(ctx, parentTagRef, int64(limit))
	if err != nil {
		return nil, err
	}
	out := make([]TagChildView, 0, len(children))
	for _, child := range children {
		count, err := s.nodes.CountActiveChildren(ctx, child.TagRef)
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

// ListDimensions 返回创作标签面板的固定维度目录。
func (s *TagService) ListDimensions(ctx context.Context) ([]TagDimensionView, error) {
	_ = ctx
	out := make([]TagDimensionView, len(tagDimensionCatalog))
	copy(out, tagDimensionCatalog)
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
	nodes, err := s.nodes.ListAll(ctx)
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

// ValidateTagRefs 批量校验 tagRef 有效性；保持输入顺序。
func (s *TagService) ValidateTagRefs(ctx context.Context, tagRefs []string) (*TagValidationResultView, error) {
	valid := make([]string, 0, len(tagRefs))
	invalid := make([]string, 0)
	cache := make(map[string]bool, len(tagRefs))
	for _, raw := range tagRefs {
		tagRef := strings.TrimSpace(raw)
		if tagRef == "" {
			invalid = append(invalid, raw)
			continue
		}
		exists, ok := cache[tagRef]
		if !ok {
			node, err := s.nodes.FindByTagRef(ctx, tagRef)
			if err != nil {
				return nil, err
			}
			exists = node != nil
			cache[tagRef] = exists
		}
		if exists {
			valid = append(valid, tagRef)
			continue
		}
		invalid = append(invalid, tagRef)
	}
	return &TagValidationResultView{Valid: valid, Invalid: invalid}, nil
}

// SharedTags 计算两个对象共享的 tagRef（交集锚点 + 标签富化）。
func (s *TagService) SharedTags(ctx context.Context, aID, aType, bID, bType string, limit int) ([]SharedTagView, error) {
	a, err := s.objects.FindByObject(ctx, aID, aType)
	if err != nil {
		return nil, err
	}
	b, err := s.objects.FindByObject(ctx, bID, bType)
	if err != nil {
		return nil, err
	}
	out := make([]SharedTagView, 0)
	if a == nil || b == nil {
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
		view := SharedTagView{TagRef: t, Strength: 1, Source: "tagRef"}
		if node, _ := s.nodes.FindByTagRef(ctx, t); node != nil {
			view.Label = node.Label
		}
		out = append(out, view)
	}
	sort.SliceStable(out, func(i, j int) bool { return out[i].TagRef < out[j].TagRef })
	if limit > 0 && len(out) > limit {
		out = out[:limit]
	}
	return out, nil
}

// Inverted 返回引用某 tagRef 的对象集合。
func (s *TagService) Inverted(ctx context.Context, tagRef, objectType string, limit int) (*InvertedObjectsView, error) {
	idxs, err := s.objects.FindObjectsByTagRef(ctx, tagRef, objectType, int64(limit))
	if err != nil {
		return nil, err
	}
	ids := make([]string, 0, len(idxs))
	for _, x := range idxs {
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

func splitTagAliases(raw string) []string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil
	}
	return strings.FieldsFunc(raw, func(r rune) bool {
		switch r {
		case ',', ';', '|', '\n', '\t', '、':
			return true
		default:
			return false
		}
	})
}
