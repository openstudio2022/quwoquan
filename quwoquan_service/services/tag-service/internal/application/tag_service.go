package application

import (
	"context"
	"sort"

	"quwoquan_service/services/tag-service/internal/domain/tag/repository"
)

// TagResolveView 对齐 service.yaml ResolveTag 响应。
type TagResolveView struct {
	TagRef    string `json:"tagRef"`
	Group     string `json:"group"`
	Label     string `json:"label"`
	LabelEn   string `json:"labelEn"`
	Aliases   string `json:"aliases"`
	Ancestors string `json:"ancestors"`
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

// TagService 提供交集核心只读用例（resolve / shared-tags / inverted）。
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
