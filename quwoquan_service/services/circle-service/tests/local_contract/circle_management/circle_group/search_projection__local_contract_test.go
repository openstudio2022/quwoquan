// spec_ref: specs/feature-tree/circle-community/spec.md#dom-001
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/design.md#dec-002
// readiness_case: project-circle-group-search-local
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	groupsearch "quwoquan_service/services/circle-service/internal/circle_management/circle_group/adapters/inbound/events"
	groupapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group/application"
	groupevent "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/event"
	groupmodel "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/model"
	groupports "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/ports"
	groupbackfill "quwoquan_service/services/circle-service/internal/circle_management/circle_group/infrastructure/searchindex"
)

func TestCircleGroupProjectorUsesSharedProjectionUnderGroupVersionAndRetriesFailures(
	t *testing.T,
) {
	group := publicSearchGroup("group-1")
	indexer := &recordingGroupIndexer{}
	projector := groupsearch.NewCircleGroupSearchIndexHandler(
		indexer,
		groupLoader{groups: map[string]groupmodel.CircleGroup{
			group.ID: group,
		}},
	)
	if err := projector.Apply(context.Background(), groupports.OutboxEvent{
		EventType:        groupevent.CircleGroupCreated,
		AggregateID:      group.ID,
		AggregateVersion: group.Version,
	}); err != nil {
		t.Fatalf("publish group create: %v", err)
	}
	if len(indexer.events) != 1 ||
		indexer.events[0].Op != es.OpUpsert ||
		indexer.events[0].Doc.ObjectType != rtsearch.ObjectTypeCircleGroup ||
		indexer.events[0].SourceVersion != group.Version {
		t.Fatalf("group projection events=%+v", indexer.events)
	}
	want := groupapp.ProjectCircleGroupToSearchDocument(group)
	if indexer.events[0].Doc.ObjectID != want.ObjectID ||
		indexer.events[0].Doc.Fields["circleId"] != want.Fields["circleId"] ||
		indexer.events[0].Doc.Fields["groupType"] != want.Fields["groupType"] {
		t.Fatalf(
			"group projection diverged: got=%+v want=%+v",
			indexer.events[0].Doc,
			want,
		)
	}

	indexer.err = errors.New("elasticsearch unavailable")
	if err := projector.Publish(context.Background(), groupports.OutboxEvent{
		EventType:        groupevent.CircleGroupUpdated,
		AggregateID:      group.ID,
		AggregateVersion: group.Version,
	}); err == nil {
		t.Fatal("index failure must keep CircleGroup outbox retryable")
	}
}

func TestCircleGroupProjectorTombstonesPrivateAndArchivedGroups(t *testing.T) {
	private := publicSearchGroup("group-private")
	private.Visibility = groupmodel.CircleGroupVisibilityPrivate
	private.Version = 3
	archived := publicSearchGroup("group-archived")
	archived.Status = groupmodel.CircleGroupStatusArchived
	archived.Version = 5
	indexer := &recordingGroupIndexer{}
	projector := groupsearch.NewCircleGroupSearchIndexHandler(
		indexer,
		groupLoader{groups: map[string]groupmodel.CircleGroup{
			private.ID:  private,
			archived.ID: archived,
		}},
	)
	for _, event := range []groupports.OutboxEvent{
		{
			EventType:        groupevent.CircleGroupUpdated,
			AggregateID:      private.ID,
			AggregateVersion: 3,
		},
		{
			EventType:        groupevent.CircleGroupArchived,
			AggregateID:      archived.ID,
			AggregateVersion: 5,
		},
		// The aggregate is unreadable: the outbox fact's version fences the tombstone.
		{
			EventType:        groupevent.CircleGroupArchived,
			AggregateID:      "group-vanished",
			AggregateVersion: 7,
		},
	} {
		if err := projector.Apply(context.Background(), event); err != nil {
			t.Fatalf("publish %s: %v", event.EventType, err)
		}
	}
	if len(indexer.events) != 3 {
		t.Fatalf("tombstone event count=%d want=3", len(indexer.events))
	}
	versions := map[string]int64{}
	for _, event := range indexer.events {
		if event.Op != es.OpDelete ||
			event.Doc.ObjectType != rtsearch.ObjectTypeCircleGroup {
			t.Fatalf("invalid tombstone event=%+v", event)
		}
		versions[event.Doc.ObjectID] = event.SourceVersion
	}
	if versions[private.ID] != 3 || versions[archived.ID] != 5 || versions["group-vanished"] != 7 {
		t.Fatalf("tombstone versions must come from the group or the outbox fact: %v", versions)
	}

	if err := projector.Apply(context.Background(), groupports.OutboxEvent{
		EventType:   groupevent.CircleGroupArchived,
		AggregateID: "group-vanished-unversioned",
	}); err == nil {
		t.Fatal("an unreadable group without an event version must fail closed")
	}
}

func TestCircleGroupBackfillReconcilesEveryVisibilityUnderGroupVersion(t *testing.T) {
	public := publicSearchGroup("group-public")
	private := publicSearchGroup("group-private")
	private.Visibility = groupmodel.CircleGroupVisibilityPrivate
	archived := publicSearchGroup("group-archived")
	archived.Status = groupmodel.CircleGroupStatusArchived
	indexer := &recordingGroupIndexer{}
	report, err := groupbackfill.Backfill(
		context.Background(),
		indexer,
		groupLister{groups: []groupmodel.CircleGroup{
			archived,
			private,
			public,
		}},
		2,
	)
	if err != nil {
		t.Fatalf("CircleGroup Backfill: %v", err)
	}
	if report.TotalGroups != 3 ||
		report.IndexedGroups != 1 ||
		report.TombstonedGroups != 2 ||
		report.StaleWrites != 0 ||
		report.BatchesRead != 2 {
		t.Fatalf("CircleGroup backfill report=%+v", report)
	}
	operations := map[string]es.ChangeOp{}
	for _, event := range indexer.events {
		if event.SourceVersion != 1 {
			t.Fatalf("backfill must write under the group's own version: %+v", event)
		}
		operations[event.Doc.ObjectID] = event.Op
	}
	if operations[public.ID] != es.OpUpsert ||
		operations[private.ID] != es.OpDelete ||
		operations[archived.ID] != es.OpDelete {
		t.Fatalf("CircleGroup backfill operations=%+v", operations)
	}

	// Replaying the same backfill is a stale/idempotent success, never a failure.
	replay, err := groupbackfill.Backfill(
		context.Background(),
		indexer,
		groupLister{groups: []groupmodel.CircleGroup{archived, private, public}},
		2,
	)
	if err != nil || replay.StaleWrites != 3 {
		t.Fatalf("replayed backfill report=%+v err=%v", replay, err)
	}

	unversioned := publicSearchGroup("group-unversioned")
	unversioned.Version = 0
	if _, err := groupbackfill.Backfill(
		context.Background(),
		indexer,
		groupLister{groups: []groupmodel.CircleGroup{unversioned}},
		2,
	); err == nil {
		t.Fatal("a group without a positive version must stop the backfill")
	}
}

func publicSearchGroup(id string) groupmodel.CircleGroup {
	return groupmodel.CircleGroup{
		ID:          id,
		Version:     1,
		CircleID:    "circle-1",
		GroupType:   groupmodel.CircleGroupTypePublicGroup,
		Name:        "骑行讨论",
		Description: "路线与装备交流",
		Visibility:  groupmodel.CircleGroupVisibilityPublic,
		Status:      groupmodel.CircleGroupStatusActive,
		UpdatedAt:   time.Date(2026, 7, 26, 0, 0, 0, 0, time.UTC),
	}
}

// recordingGroupIndexer is an es.VersionedChangeEvent recorder that enforces the
// provider's strictly-newer fence in memory (applied=false on replay).
type recordingGroupIndexer struct {
	events   []es.VersionedChangeEvent
	versions map[string]int64
	err      error
}

func (indexer *recordingGroupIndexer) ApplyVersioned(
	_ context.Context,
	event es.VersionedChangeEvent,
) (bool, error) {
	if indexer.err != nil {
		return false, indexer.err
	}
	if event.SourceVersion <= 0 {
		return false, errors.New("sourceVersion must be positive")
	}
	if indexer.versions == nil {
		indexer.versions = map[string]int64{}
	}
	indexer.events = append(indexer.events, event)
	id := es.IndexID(event.Doc)
	if indexer.versions[id] >= event.SourceVersion {
		return false, nil
	}
	indexer.versions[id] = event.SourceVersion
	return true, nil
}

type groupLoader struct {
	groups map[string]groupmodel.CircleGroup
	err    error
}

func (loader groupLoader) Load(
	_ context.Context,
	groupID string,
) (groupmodel.CircleGroup, bool, error) {
	if loader.err != nil {
		return groupmodel.CircleGroup{}, false, loader.err
	}
	group, found := loader.groups[groupID]
	return group, found, nil
}

type groupLister struct {
	groups []groupmodel.CircleGroup
}

func (lister groupLister) ListForSearch(
	_ context.Context,
	afterID string,
	limit int,
) ([]groupmodel.CircleGroup, error) {
	start := 0
	if afterID != "" {
		for index := range lister.groups {
			if lister.groups[index].ID == afterID {
				start = index + 1
				break
			}
		}
	}
	end := start + limit
	if end > len(lister.groups) {
		end = len(lister.groups)
	}
	return lister.groups[start:end], nil
}
