// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
package local_contract

import (
	"context"
	"testing"

	viewevents "quwoquan_service/services/circle-service/internal/circle_management/circle_search_item_view/adapters/inbound/events"
	viewapp "quwoquan_service/services/circle-service/internal/circle_management/circle_search_item_view/application"
)

type recordingIndex struct {
	upserts []viewapp.SearchItem
	deletes []string
}

func (index *recordingIndex) UpsertIfNewer(_ context.Context, item viewapp.SearchItem) (bool, error) {
	index.upserts = append(index.upserts, item)
	return true, nil
}
func (index *recordingIndex) DeleteIfNotOlder(_ context.Context, circleID string, _ int64) (bool, error) {
	index.deletes = append(index.deletes, circleID)
	return true, nil
}

type searchSnapshots struct {
	item    viewapp.SearchItem
	visible bool
}

func (source searchSnapshots) LoadSearchItem(context.Context, string) (viewapp.SearchItem, bool, error) {
	return source.item, source.visible, nil
}

type rebuildPage []viewapp.RebuildEntry

func (page rebuildPage) ListSearchItems(_ context.Context, after string, _ int) ([]viewapp.RebuildEntry, error) {
	if after != "" {
		return nil, nil
	}
	return page, nil
}

func TestCircleSearchItemViewOwnsTypedEventAndRebuildLifecycle(t *testing.T) {
	index := &recordingIndex{}
	projector := viewapp.NewProjector(index)
	sink := viewevents.NewSink(projector, searchSnapshots{
		visible: true,
		item:    viewapp.SearchItem{CircleID: "circle-1", DisplayName: "searchable", SourceVersion: 2},
	})
	if err := sink.Apply(context.Background(), viewapp.LifecycleEvent{
		Type: "CircleUpdated", CircleID: "circle-1", SourceVersion: 2,
	}); err != nil {
		t.Fatal(err)
	}
	if err := sink.Apply(context.Background(), viewapp.LifecycleEvent{
		Type: "CircleArchived", CircleID: "circle-1", SourceVersion: 3,
	}); err != nil {
		t.Fatal(err)
	}
	if len(index.upserts) != 1 || len(index.deletes) != 1 {
		t.Fatalf("typed lifecycle drifted: upserts=%d deletes=%d", len(index.upserts), len(index.deletes))
	}

	report, err := projector.Rebuild(context.Background(), rebuildPage{
		{Item: viewapp.SearchItem{CircleID: "circle-2", DisplayName: "visible", SourceVersion: 1}, Visible: true},
		{Item: viewapp.SearchItem{CircleID: "circle-3", DisplayName: "hidden", SourceVersion: 1}, Visible: false},
	}, 100)
	if err != nil || report.Total != 2 || report.Upserted != 1 || report.Deleted != 1 {
		t.Fatalf("rebuild report drifted: report=%+v err=%v", report, err)
	}
}
