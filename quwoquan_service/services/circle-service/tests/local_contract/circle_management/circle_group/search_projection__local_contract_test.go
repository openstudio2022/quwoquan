package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	groupapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group/application"
	groupevent "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/event"
	groupmodel "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/model"
	groupports "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/ports"
	groupsearch "quwoquan_service/services/circle-service/internal/circle_management/circle_group/infrastructure/searchindex"
)

func TestCircleGroupProjectorUsesSharedProjectionAndRetriesFailures(
	t *testing.T,
) {
	group := publicSearchGroup("group-1")
	indexer := &recordingGroupIndexer{}
	projector := groupsearch.NewProjector(
		indexer,
		groupLoader{groups: map[string]groupmodel.CircleGroup{
			group.ID: group,
		}},
	)
	if err := projector.Publish(context.Background(), groupports.OutboxEvent{
		EventType:   groupevent.CircleGroupCreated,
		AggregateID: group.ID,
	}); err != nil {
		t.Fatalf("publish group create: %v", err)
	}
	if len(indexer.events) != 1 ||
		indexer.events[0].Op != es.OpUpsert ||
		indexer.events[0].Doc.ObjectType != rtsearch.ObjectTypeCircleGroup {
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
		EventType:   groupevent.CircleGroupUpdated,
		AggregateID: group.ID,
	}); err == nil {
		t.Fatal("index failure must keep CircleGroup outbox retryable")
	}
}

func TestCircleGroupProjectorDeletesPrivateAndArchivedGroups(t *testing.T) {
	private := publicSearchGroup("group-private")
	private.Visibility = groupmodel.CircleGroupVisibilityPrivate
	indexer := &recordingGroupIndexer{}
	projector := groupsearch.NewProjector(
		indexer,
		groupLoader{groups: map[string]groupmodel.CircleGroup{
			private.ID: private,
		}},
	)
	for _, event := range []groupports.OutboxEvent{
		{
			EventType:   groupevent.CircleGroupUpdated,
			AggregateID: private.ID,
		},
		{
			EventType:   groupevent.CircleGroupArchived,
			AggregateID: "group-archived",
		},
	} {
		if err := projector.Publish(context.Background(), event); err != nil {
			t.Fatalf("publish %s: %v", event.EventType, err)
		}
	}
	if len(indexer.events) != 2 {
		t.Fatalf("delete event count=%d want=2", len(indexer.events))
	}
	for _, event := range indexer.events {
		if event.Op != es.OpDelete ||
			event.Doc.ObjectType != rtsearch.ObjectTypeCircleGroup {
			t.Fatalf("invalid delete event=%+v", event)
		}
	}
}

func TestCircleGroupBackfillReconcilesEveryVisibility(t *testing.T) {
	public := publicSearchGroup("group-public")
	private := publicSearchGroup("group-private")
	private.Visibility = groupmodel.CircleGroupVisibilityPrivate
	archived := publicSearchGroup("group-archived")
	archived.Status = groupmodel.CircleGroupStatusArchived
	indexer := &recordingGroupBulk{}
	report, err := groupsearch.Backfill(
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
	if !indexer.ensured ||
		report.TotalGroups != 3 ||
		report.IndexedGroups != 1 ||
		report.DeletedGroups != 2 ||
		report.BatchesPushed != 2 {
		t.Fatalf("CircleGroup backfill report=%+v", report)
	}
	operations := map[string]es.ChangeOp{}
	for _, event := range indexer.events {
		operations[event.Doc.ObjectID] = event.Op
	}
	if operations[public.ID] != es.OpUpsert ||
		operations[private.ID] != es.OpDelete ||
		operations[archived.ID] != es.OpDelete {
		t.Fatalf("CircleGroup backfill operations=%+v", operations)
	}
}

func publicSearchGroup(id string) groupmodel.CircleGroup {
	return groupmodel.CircleGroup{
		ID:          id,
		CircleID:    "circle-1",
		GroupType:   groupmodel.CircleGroupTypePublicGroup,
		Name:        "骑行讨论",
		Description: "路线与装备交流",
		Visibility:  groupmodel.CircleGroupVisibilityPublic,
		Status:      groupmodel.CircleGroupStatusActive,
		UpdatedAt:   time.Date(2026, 7, 26, 0, 0, 0, 0, time.UTC),
	}
}

type recordingGroupIndexer struct {
	events []es.ChangeEvent
	err    error
}

func (indexer *recordingGroupIndexer) Apply(
	_ context.Context,
	event es.ChangeEvent,
) error {
	if indexer.err != nil {
		return indexer.err
	}
	indexer.events = append(indexer.events, event)
	return nil
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

type recordingGroupBulk struct {
	ensured bool
	events  []es.ChangeEvent
}

func (indexer *recordingGroupBulk) EnsureIndex(context.Context) error {
	indexer.ensured = true
	return nil
}

func (indexer *recordingGroupBulk) Bulk(
	_ context.Context,
	_ string,
	events []es.ChangeEvent,
) error {
	indexer.events = append(indexer.events, events...)
	return nil
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
