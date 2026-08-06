// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-006
// readiness_case: resolve-tag-local
// readiness_case: list-tag-children-local
// readiness_case: shared-tags-local
// readiness_case: inverted-objects-local
// readiness_case: list-dimensions-local
// readiness_case: suggest-tags-local
// readiness_case: validate-tag-refs-local
// readiness_case: search-tags-local
// readiness_case: related-tags-local
// readiness_case: search-by-tags-local
// readiness_case: tag-cooccurrence-local
// readiness_case: related-objects-local
package local_contract

import (
	"context"
	"reflect"
	"strings"
	"testing"

	indexmodel "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/domain/model"
	application "quwoquan_service/services/tag-service/internal/tag/tag_node_view/application"
	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/lifecycle"
	model "quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/model"
)

type migratedTagNodeReader struct {
	nodes       map[string]*model.TagNode
	leafQueries map[string]int
}

func (r migratedTagNodeReader) FindByReleaseAndTagRef(_ context.Context, releaseID, tagRef string) (*model.TagNode, error) {
	node := r.nodes[tagRef]
	if node == nil || node.ReleaseID != releaseID {
		return nil, nil
	}
	return node, nil
}

func (r migratedTagNodeReader) ListChildrenInRelease(_ context.Context, releaseID, parentTagRef string, _ int64) ([]model.TagNode, error) {
	out := make([]model.TagNode, 0)
	for _, node := range r.nodes {
		if node.ReleaseID == releaseID && node.ParentTagRef == parentTagRef && lifecycle.IsUsable(node.LifecycleStatus) {
			out = append(out, *node)
		}
	}
	return out, nil
}

func (r migratedTagNodeReader) CountUsableChildrenInRelease(ctx context.Context, releaseID, parentTagRef string) (int64, error) {
	children, err := r.ListChildrenInRelease(ctx, releaseID, parentTagRef, 1)
	return int64(len(children)), err
}

func (r migratedTagNodeReader) ListDimensionsInRelease(
	_ context.Context,
	releaseID string,
) ([]model.TagNode, error) {
	out := make([]model.TagNode, 0)
	for _, node := range r.nodes {
		if node.ReleaseID == releaseID &&
			lifecycle.IsUsable(node.LifecycleStatus) &&
			node.NodeKind == "dimension" {
			out = append(out, *node)
		}
	}
	return out, nil
}

func (r migratedTagNodeReader) ListAllInRelease(_ context.Context, releaseID string) ([]model.TagNode, error) {
	out := make([]model.TagNode, 0, len(r.nodes))
	for _, node := range r.nodes {
		if node.ReleaseID == releaseID && lifecycle.IsUsable(node.LifecycleStatus) {
			out = append(out, *node)
		}
	}
	return out, nil
}

func (r migratedTagNodeReader) IsUsableLeaf(ctx context.Context, releaseID, tagRef string) (bool, error) {
	if r.leafQueries != nil {
		r.leafQueries[tagRef]++
	}
	node, err := r.FindByReleaseAndTagRef(ctx, releaseID, tagRef)
	if err != nil || node == nil || !lifecycle.IsUsable(node.LifecycleStatus) {
		return false, err
	}
	count, err := r.CountUsableChildrenInRelease(ctx, releaseID, tagRef)
	return count == 0, err
}

type migratedActiveReleaseReader struct {
	releaseID string
	found     bool
}

func (r migratedActiveReleaseReader) ActiveReleaseID(context.Context) (string, bool, error) {
	return r.releaseID, r.found, nil
}

type migratedObjectTagIndexReader struct {
	indexes []indexmodel.ObjectTagIndex
}

func (r migratedObjectTagIndexReader) FindByObject(
	_ context.Context,
	objectID string,
	objectType string,
) (*indexmodel.ObjectTagIndex, error) {
	for _, index := range r.indexes {
		if index.ObjectID == objectID && index.ObjectType == objectType {
			found := index
			return &found, nil
		}
	}
	return nil, nil
}

func (r migratedObjectTagIndexReader) FindObjectsByTagRef(
	_ context.Context,
	tagRef string,
	objectType string,
	limit int64,
) ([]indexmodel.ObjectTagIndex, error) {
	return r.findByTag(tagRef, objectType, limit, false), nil
}

func (r migratedObjectTagIndexReader) FindObjectsByTagRefSubtree(
	_ context.Context,
	tagRef string,
	objectType string,
	limit int64,
) ([]indexmodel.ObjectTagIndex, error) {
	return r.findByTag(tagRef, objectType, limit, true), nil
}

func (r migratedObjectTagIndexReader) findByTag(
	tagRef string,
	objectType string,
	limit int64,
	includeDescendants bool,
) []indexmodel.ObjectTagIndex {
	out := make([]indexmodel.ObjectTagIndex, 0)
	for _, index := range r.indexes {
		if objectType != "" && index.ObjectType != objectType {
			continue
		}
		matched := false
		for _, candidate := range index.TagRefs {
			if candidate == tagRef || (includeDescendants && strings.HasPrefix(candidate, tagRef+"/")) {
				matched = true
				break
			}
		}
		if matched {
			out = append(out, index)
			if limit > 0 && int64(len(out)) >= limit {
				break
			}
		}
	}
	return out
}

func TestTagNodeViewResolvesThroughApplicationPorts(t *testing.T) {
	service := application.NewTagService(
		migratedTagNodeReader{nodes: map[string]*model.TagNode{
			"Topic/旅行": {
				TagRef:          "Topic/旅行",
				Group:           "Topic",
				Label:           "旅行",
				LabelEn:         "Travel",
				ReleaseID:       "release-current",
				LifecycleStatus: "active",
			},
		}},
		migratedObjectTagIndexReader{},
		migratedActiveReleaseReader{
			releaseID: "release-current",
			found:     true,
		},
	)
	view, err := service.Resolve(context.Background(), "Topic/旅行")
	if err != nil || view == nil || view.Label != "旅行" {
		t.Fatalf("Resolve() = %#v, %v", view, err)
	}
}

func TestListDimensionsUsesActiveTaxonomyProjection(t *testing.T) {
	service := application.NewTagService(
		migratedTagNodeReader{nodes: map[string]*model.TagNode{
			"Topic/旅行/玩法": {
				TagRef:          "Topic/旅行/玩法",
				Group:           "Topic",
				NodeKind:        "dimension",
				Label:           "玩法",
				LabelEn:         "Activities",
				MaxDepth:        2,
				PathPolicy:      "any-depth",
				ReleaseID:       "release-current",
				LifecycleStatus: "active",
			},
			"Topic/retired": {
				TagRef:          "Topic/retired",
				Group:           "Topic",
				NodeKind:        "dimension",
				Label:           "旧维度",
				ReleaseID:       "release-old",
				LifecycleStatus: "active",
			},
		}},
		migratedObjectTagIndexReader{},
		migratedActiveReleaseReader{
			releaseID: "release-current",
			found:     true,
		},
	)

	got, err := service.ListDimensions(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 ||
		got[0].DimensionID != "Topic/旅行/玩法" ||
		got[0].MaxDepth != 2 ||
		got[0].PathPolicy != "any-depth" {
		t.Fatalf("ListDimensions() = %#v", got)
	}
}

func TestValidateTagRefsAcceptsOnlyActiveLeaves(t *testing.T) {
	nodes := map[string]*model.TagNode{
		"Topic": {
			TagRef: "Topic", ReleaseID: "release-current", LifecycleStatus: "active",
		},
		"Topic/leaf": {
			TagRef: "Topic/leaf", ParentTagRef: "Topic", ReleaseID: "release-current", LifecycleStatus: "active",
		},
		"Topic/inactive": {
			TagRef: "Topic/inactive", ParentTagRef: "Topic", ReleaseID: "release-current", LifecycleStatus: "deprecated",
		},
		"Topic/old": {
			TagRef: "Topic/old", ParentTagRef: "Topic", ReleaseID: "release-old", LifecycleStatus: "active",
		},
	}
	reader := migratedTagNodeReader{nodes: nodes, leafQueries: map[string]int{}}
	service := application.NewTagService(
		reader,
		migratedObjectTagIndexReader{},
		migratedActiveReleaseReader{
			releaseID: "release-current",
			found:     true,
		},
	)

	view, err := service.ValidateTagRefs(context.Background(), "release-current", []string{
		" Topic/leaf ", "Topic", "Topic/inactive", "Topic/old", "Topic/missing", "Topic/leaf",
	})
	if err != nil {
		t.Fatalf("ValidateTagRefs() error = %v", err)
	}
	if view.TaxonomyReleaseID != "release-current" {
		t.Fatalf("taxonomy release = %q, want release-current", view.TaxonomyReleaseID)
	}
	if want := []string{"Topic/leaf", "Topic/leaf"}; !reflect.DeepEqual(view.Valid, want) {
		t.Fatalf("valid = %#v, want %#v", view.Valid, want)
	}
	if want := []string{"Topic", "Topic/inactive", "Topic/old", "Topic/missing"}; !reflect.DeepEqual(view.Invalid, want) {
		t.Fatalf("invalid = %#v, want %#v", view.Invalid, want)
	}
	if reader.leafQueries["Topic/leaf"] != 1 {
		t.Fatalf("duplicate tagRef queried %d times, want 1", reader.leafQueries["Topic/leaf"])
	}

	mismatch, err := service.ValidateTagRefs(context.Background(), "release-old", []string{"Topic/leaf"})
	if err != nil {
		t.Fatalf("ValidateTagRefs() mismatch error = %v", err)
	}
	if len(mismatch.Valid) != 0 || !reflect.DeepEqual(mismatch.Invalid, []string{"Topic/leaf"}) {
		t.Fatalf("release mismatch must fail closed, got %#v", mismatch)
	}
}

func TestTagNodeViewExercisesEveryCanonicalQueryFacade(t *testing.T) {
	const releaseID = "release-readiness"
	const food = "Topic/旅行/美食"
	const hiking = "Topic/旅行/徒步"
	nodes := map[string]*model.TagNode{
		"Topic/旅行": {
			TagRef: "Topic/旅行", Group: "Topic", Label: "旅行",
			ReleaseID: releaseID, LifecycleStatus: "active",
		},
		food: {
			TagRef: food, ParentTagRef: "Topic/旅行", Group: "Topic",
			Label: "美食", LabelEn: "Food", ReleaseID: releaseID,
			LifecycleStatus: "active",
		},
		hiking: {
			TagRef: hiking, ParentTagRef: "Topic/旅行", Group: "Topic",
			Label: "徒步", LabelEn: "Hiking", ReleaseID: releaseID,
			LifecycleStatus: "active",
		},
		"Topic/旅行/玩法": {
			TagRef: "Topic/旅行/玩法", ParentTagRef: "Topic/旅行", Group: "Topic",
			NodeKind: "dimension", Label: "玩法", LabelEn: "Activities",
			MaxDepth: 2, PathPolicy: "any-depth", ReleaseID: releaseID,
			LifecycleStatus: "active",
		},
	}
	objects := migratedObjectTagIndexReader{indexes: []indexmodel.ObjectTagIndex{
		{ObjectID: "post-a", ObjectType: "post", TagRefs: []string{food, hiking}},
		{ObjectID: "post-b", ObjectType: "post", TagRefs: []string{food}},
	}}
	service := application.NewTagService(
		migratedTagNodeReader{nodes: nodes},
		objects,
		migratedActiveReleaseReader{releaseID: releaseID, found: true},
	)
	ctx := context.Background()

	if got, err := service.Resolve(ctx, food); err != nil || got == nil {
		t.Fatalf("Resolve() = %+v, %v", got, err)
	}
	if got, err := service.ListChildren(ctx, "Topic/旅行", 10); err != nil || len(got) < 3 {
		t.Fatalf("ListChildren() = %+v, %v", got, err)
	}
	if got, err := service.SharedTags(ctx, "post-a", "post", "post-b", "post", 10); err != nil || len(got) != 1 {
		t.Fatalf("SharedTags() = %+v, %v", got, err)
	}
	if got, err := service.Inverted(ctx, food, "post", 10, false); err != nil || got.ObjectCount != 2 {
		t.Fatalf("Inverted() = %+v, %v", got, err)
	}
	if got, err := service.ListDimensions(ctx); err != nil || len(got) != 1 {
		t.Fatalf("ListDimensions() = %+v, %v", got, err)
	}
	if got, err := service.Suggest(ctx, "美食", "Topic", 10); err != nil || len(got) != 1 {
		t.Fatalf("Suggest() = %+v, %v", got, err)
	}
	if got, err := service.ValidateTagRefs(ctx, releaseID, []string{food}); err != nil || len(got.Valid) != 1 {
		t.Fatalf("ValidateTagRefs() = %+v, %v", got, err)
	}
	if got, err := service.SearchTags(ctx, "美食", "Topic", 10); err != nil || len(got) != 1 {
		t.Fatalf("SearchTags() = %+v, %v", got, err)
	}
	if got, err := service.RelatedTags(ctx, food, 10); err != nil || len(got) != 1 {
		t.Fatalf("RelatedTags() = %+v, %v", got, err)
	}
	if got, err := service.SearchByTags(ctx, []string{food, hiking}, "post", 10); err != nil || len(got) != 2 {
		t.Fatalf("SearchByTags() = %+v, %v", got, err)
	}
	if got, err := service.TagCooccurrence(ctx, food, 1, 10); err != nil || len(got) != 1 {
		t.Fatalf("TagCooccurrence() = %+v, %v", got, err)
	}
	if got, err := service.RelatedObjects(ctx, "post-a", "post", 10); err != nil || len(got) != 1 {
		t.Fatalf("RelatedObjects() = %+v, %v", got, err)
	}
}
