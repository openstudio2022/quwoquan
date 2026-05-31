package application

import (
	"context"
	"testing"

	model "quwoquan_service/services/tag-service/internal/domain/tag/model"
)

type fakeNodeReader struct{ nodes map[string]*model.TagNode }

func (f *fakeNodeReader) FindByTagRef(_ context.Context, tagRef string) (*model.TagNode, error) {
	return f.nodes[tagRef], nil
}

type fakeObjReader struct{ objs map[string]*model.ObjectTagIndex }

func (f *fakeObjReader) FindByObject(_ context.Context, id, typ string) (*model.ObjectTagIndex, error) {
	return f.objs[id+"|"+typ], nil
}

func (f *fakeObjReader) FindObjectsByTagRef(_ context.Context, tagRef, objectType string, _ int64) ([]model.ObjectTagIndex, error) {
	out := make([]model.ObjectTagIndex, 0)
	for _, o := range f.objs {
		for _, t := range o.TagRefs {
			if t == tagRef && (objectType == "" || o.ObjectType == objectType) {
				out = append(out, *o)
				break
			}
		}
	}
	return out, nil
}

func newServiceWithFixtures() *TagService {
	nodes := &fakeNodeReader{nodes: map[string]*model.TagNode{
		"Topic/旅行":            {TagRef: "Topic/旅行", Group: "Topic", Label: "旅行"},
		"Topic/摄影":            {TagRef: "Topic/摄影", Group: "Topic", Label: "摄影"},
		"Entity/机构/学校/北京大学": {TagRef: "Entity/机构/学校/北京大学", Group: "Entity", Label: "北京大学"},
	}}
	objs := &fakeObjReader{objs: map[string]*model.ObjectTagIndex{
		"u1|user": {ObjectID: "u1", ObjectType: "user", TagRefs: []string{"Topic/旅行", "Topic/摄影", "Entity/机构/学校/北京大学"}},
		"u2|user": {ObjectID: "u2", ObjectType: "user", TagRefs: []string{"Topic/摄影", "Entity/机构/学校/北京大学"}},
		"p1|post": {ObjectID: "p1", ObjectType: "post", TagRefs: []string{"Topic/旅行"}},
	}}
	return NewTagService(nodes, objs)
}

func TestResolve(t *testing.T) {
	svc := newServiceWithFixtures()
	view, err := svc.Resolve(context.Background(), "Topic/旅行")
	if err != nil {
		t.Fatalf("resolve error: %v", err)
	}
	if view == nil || view.Label != "旅行" {
		t.Fatalf("expected label 旅行, got %+v", view)
	}
	miss, err := svc.Resolve(context.Background(), "Topic/不存在")
	if err != nil {
		t.Fatalf("resolve miss error: %v", err)
	}
	if miss != nil {
		t.Fatalf("expected nil for unknown tagRef, got %+v", miss)
	}
}

func TestSharedTags(t *testing.T) {
	svc := newServiceWithFixtures()
	shared, err := svc.SharedTags(context.Background(), "u1", "user", "u2", "user", 0)
	if err != nil {
		t.Fatalf("shared error: %v", err)
	}
	// u1∩u2 = {摄影, 北京大学}
	if len(shared) != 2 {
		t.Fatalf("expected 2 shared tags, got %d: %+v", len(shared), shared)
	}
	got := map[string]bool{}
	for _, s := range shared {
		got[s.TagRef] = true
		if s.Source != "tagRef" {
			t.Fatalf("expected source tagRef, got %q", s.Source)
		}
	}
	if !got["Topic/摄影"] || !got["Entity/机构/学校/北京大学"] {
		t.Fatalf("shared set mismatch: %+v", got)
	}
	// 标签富化：label 非空
	for _, s := range shared {
		if s.Label == "" {
			t.Fatalf("expected enriched label for %s", s.TagRef)
		}
	}
}

func TestSharedTagsLimit(t *testing.T) {
	svc := newServiceWithFixtures()
	shared, err := svc.SharedTags(context.Background(), "u1", "user", "u2", "user", 1)
	if err != nil {
		t.Fatalf("shared error: %v", err)
	}
	if len(shared) != 1 {
		t.Fatalf("expected limit 1, got %d", len(shared))
	}
}

func TestInverted(t *testing.T) {
	svc := newServiceWithFixtures()
	view, err := svc.Inverted(context.Background(), "Topic/摄影", "", 0)
	if err != nil {
		t.Fatalf("inverted error: %v", err)
	}
	// 摄影 被 u1, u2 引用
	if view.ObjectCount != 2 {
		t.Fatalf("expected 2 objects for Topic/摄影, got %d: %+v", view.ObjectCount, view.ObjectIds)
	}
	// objectType 过滤
	postOnly, err := svc.Inverted(context.Background(), "Topic/旅行", "post", 0)
	if err != nil {
		t.Fatalf("inverted post error: %v", err)
	}
	if postOnly.ObjectCount != 1 || postOnly.ObjectIds[0] != "p1" {
		t.Fatalf("expected only p1 for Topic/旅行 post, got %+v", postOnly.ObjectIds)
	}
}
