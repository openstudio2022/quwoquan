// spec_ref: specs/feature-tree/circle-community/spec.md#dom-001
// readiness_case: project-circle-search-item-local
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

type lifecycleSource struct {
	events []viewapp.LifecycleEvent
}

func (source lifecycleSource) ReadAfter(_ context.Context, checkpoint string, _ int) ([]viewapp.LifecycleEvent, error) {
	if checkpoint != "" {
		return nil, nil
	}
	return source.events, nil
}

type memoryCheckpoint struct {
	value string
}

func (checkpoint *memoryCheckpoint) Load(context.Context, string) (string, error) {
	return checkpoint.value, nil
}

func (checkpoint *memoryCheckpoint) Save(_ context.Context, _ string, value string) error {
	checkpoint.value = value
	return nil
}

func TestCircleSearchItemViewOwnsTypedEventAndRebuildLifecycle(t *testing.T) {
	index := &recordingIndex{}
	projector := viewapp.NewProjector(index)
	sink := viewevents.NewSink(projector, searchSnapshots{
		visible: true,
		item:    viewapp.SearchItem{CircleID: "circle-1", DisplayName: "searchable", SourceVersion: 2},
	})
	checkpoint := &memoryCheckpoint{}
	relay := viewapp.NewRelay(lifecycleSource{events: []viewapp.LifecycleEvent{
		{EventID: "circle-updated-2", Type: "CircleUpdated", CircleID: "circle-1", SourceVersion: 2, Checkpoint: "2"},
		{EventID: "circle-archived-3", Type: "CircleArchived", CircleID: "circle-1", SourceVersion: 3, Checkpoint: "3"},
	}}, checkpoint, sink, "circle-search-local")
	if count, err := relay.Drain(context.Background(), 10); err != nil || count != 2 {
		t.Fatalf("drain count=%d err=%v", count, err)
	}
	if len(index.upserts) != 1 || len(index.deletes) != 1 {
		t.Fatalf("typed lifecycle drifted: upserts=%d deletes=%d", len(index.upserts), len(index.deletes))
	}
	if checkpoint.value != "3" {
		t.Fatalf("successful projection checkpoint=%q want=3", checkpoint.value)
	}

	report, err := projector.Rebuild(context.Background(), rebuildPage{
		{Item: viewapp.SearchItem{CircleID: "circle-2", DisplayName: "visible", SourceVersion: 1}, Visible: true},
		{Item: viewapp.SearchItem{CircleID: "circle-3", DisplayName: "hidden", SourceVersion: 1}, Visible: false},
	}, 100)
	if err != nil || report.Total != 2 || report.Upserted != 1 || report.Deleted != 1 {
		t.Fatalf("rebuild report drifted: report=%+v err=%v", report, err)
	}
}
