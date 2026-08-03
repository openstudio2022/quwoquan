package local_contract

import (
	"context"
	"reflect"
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

type migratedObjectTagIndexReader struct{}

func (migratedObjectTagIndexReader) FindByObject(context.Context, string, string) (*indexmodel.ObjectTagIndex, error) {
	return nil, nil
}

func (migratedObjectTagIndexReader) FindObjectsByTagRef(
	context.Context,
	string,
	string,
	int64,
) ([]indexmodel.ObjectTagIndex, error) {
	return nil, nil
}

func (migratedObjectTagIndexReader) FindObjectsByTagRefSubtree(
	context.Context,
	string,
	string,
	int64,
) ([]indexmodel.ObjectTagIndex, error) {
	return nil, nil
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
			"Topic/legacy": {
				TagRef:          "Topic/legacy",
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

func TestValidateTagRefsAcceptsOnlyCurrentActiveLeaves(t *testing.T) {
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
