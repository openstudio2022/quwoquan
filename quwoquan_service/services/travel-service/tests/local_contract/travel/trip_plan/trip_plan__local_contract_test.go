// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-plan-revision/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/ports"
	revisionmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/model"
	revisionports "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/ports"
)

func TestTripPlanCreateRevisionCASAndIdempotencyAreOneAtomicUnit(t *testing.T) {
	store := newMemoryTripStore()
	service := application.NewService(
		store, store, nil,
		&sequenceIDs{},
		func() time.Time { return time.Date(2026, 8, 2, 9, 0, 0, 0, time.UTC) },
	)
	create := application.CreateCommand{
		ActorPersonaID: "persona-organizer",
		IdempotencyKey: "trip-create-1",
		Title:          "杭州七日共同旅行",
		Items: []application.ItemInput{
			{ItemID: "item-hotel", DayIndex: 0, OrderInDay: 0, Kind: model.ItemStay, Title: "入住西湖边酒店"},
			{ItemID: "item-dinner", DayIndex: 0, OrderInDay: 1, Kind: model.ItemFood, Title: "晚餐"},
		},
	}
	created, err := service.Create(t.Context(), create)
	if err != nil {
		t.Fatalf("Create(): %v", err)
	}
	if created.CurrentRevisionNumber != 1 || created.Status != model.StatusPlanning {
		t.Fatalf("created=%+v", created)
	}
	assertAtomicCounts(t, store, 1, 1, 1, 1)

	replayed, err := service.Create(t.Context(), create)
	if err != nil || !replayed.IdempotentReplay || replayed.TripID != created.TripID {
		t.Fatalf("replay=%+v err=%v", replayed, err)
	}
	assertAtomicCounts(t, store, 1, 1, 1, 1)

	changedKey := create
	changedKey.Title = "复用同一键的不同请求"
	if _, err := service.Create(t.Context(), changedKey); !errors.Is(err, ports.ErrIdempotencyConflict) {
		t.Fatalf("idempotency conflict err=%v", err)
	}

	revisionCommands := []application.ReviseCommand{
		{
			ActorPersonaID: "persona-organizer", IdempotencyKey: "trip-revise-a", TripID: created.TripID,
			ExpectedRevisionNumber: 1, ChangeReason: "晚餐延后", Severity: revisionmodel.SeverityImportant,
			Items: []application.ItemInput{
				{ItemID: "item-hotel", DayIndex: 0, OrderInDay: 0, Kind: model.ItemStay, Title: "入住西湖边酒店"},
				{ItemID: "item-dinner", DayIndex: 0, OrderInDay: 1, Kind: model.ItemFood, Title: "晚餐改到八点"},
			},
		},
		{
			ActorPersonaID: "persona-organizer", IdempotencyKey: "trip-revise-b", TripID: created.TripID,
			ExpectedRevisionNumber: 1, ChangeReason: "晚餐换地点", Severity: revisionmodel.SeverityImportant,
			Items: []application.ItemInput{
				{ItemID: "item-hotel", DayIndex: 0, OrderInDay: 0, Kind: model.ItemStay, Title: "入住西湖边酒店"},
				{ItemID: "item-dinner", DayIndex: 0, OrderInDay: 1, Kind: model.ItemFood, Title: "晚餐改到河坊街"},
			},
		},
	}
	results := make(chan error, len(revisionCommands))
	for _, command := range revisionCommands {
		command := command
		go func() {
			_, reviseErr := service.Revise(context.Background(), command)
			results <- reviseErr
		}()
	}
	succeeded := 0
	conflicted := 0
	for range revisionCommands {
		err := <-results
		switch {
		case err == nil:
			succeeded++
		case errors.Is(err, model.ErrRevisionConflict):
			conflicted++
		default:
			t.Fatalf("unexpected revise error: %v", err)
		}
	}
	if succeeded != 1 || conflicted != 1 {
		t.Fatalf("succeeded=%d conflicted=%d", succeeded, conflicted)
	}
	assertAtomicCounts(t, store, 1, 2, 2, 2)
	plan, revision, err := service.Get(t.Context(), "persona-organizer", created.TripID)
	if err != nil || plan.CurrentRevisionNumber != 2 || revision.RevisionNumber != 2 || len(revision.Changes) != 1 {
		t.Fatalf("plan=%+v revision=%+v err=%v", plan, revision, err)
	}
}

func TestTripPlanLifecycleTransitionCreatesRevisionAndPreservesAuthorization(t *testing.T) {
	store := newMemoryTripStore()
	service := application.NewService(store, store, nil, &sequenceIDs{}, time.Now)
	created, err := service.Create(t.Context(), application.CreateCommand{
		ActorPersonaID: "organizer", IdempotencyKey: "create", Title: "西湖周末游",
		Items: []application.ItemInput{{ItemID: "west-lake", Kind: model.ItemSight, Title: "西湖", DayIndex: 0, OrderInDay: 0}},
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err := service.Get(t.Context(), "another-persona", created.TripID); !errors.Is(err, model.ErrPermissionDenied) {
		t.Fatalf("unauthorized Get err=%v", err)
	}
	transitioned, err := service.Transition(t.Context(), application.TransitionCommand{
		ActorPersonaID: "organizer", IdempotencyKey: "activate", TripID: created.TripID,
		ExpectedRevisionNumber: 1, TargetStatus: model.StatusActive,
	})
	if err != nil || transitioned.Status != model.StatusActive || transitioned.CurrentRevisionNumber != 2 {
		t.Fatalf("transitioned=%+v err=%v", transitioned, err)
	}
	_, revision, err := service.Get(t.Context(), "organizer", created.TripID)
	if err != nil || len(revision.Changes) != 1 || revision.Changes[0].Kind != revisionmodel.ChangeLifecycleChanged {
		t.Fatalf("revision=%+v err=%v", revision, err)
	}
	if _, err := service.Transition(t.Context(), application.TransitionCommand{
		ActorPersonaID: "organizer", IdempotencyKey: "invalid", TripID: created.TripID,
		ExpectedRevisionNumber: 2, TargetStatus: model.StatusPlanning,
	}); !errors.Is(err, model.ErrInvalidTransition) {
		t.Fatalf("invalid transition err=%v", err)
	}
	assertAtomicCounts(t, store, 1, 2, 2, 2)
}

type sequenceIDs struct{ value atomic.Int64 }

func (generator *sequenceIDs) NewTripPlanID() (string, error) {
	return fmt.Sprintf("trip_%d", generator.value.Add(1)), nil
}

func (generator *sequenceIDs) NewRevisionID() (string, error) {
	return fmt.Sprintf("trv_%d", generator.value.Add(1)), nil
}

func (generator *sequenceIDs) NewEventID() (string, error) {
	return fmt.Sprintf("tve_%d", generator.value.Add(1)), nil
}

type memoryTripStore struct {
	mu             sync.Mutex
	plans          map[string]model.Plan
	revisions      map[string]map[int64]revisionmodel.Revision
	receipts       map[string]ports.CommandReceipt
	events         []ports.OutboxEvent
	revisionEvents []ports.OutboxEvent
}

func newMemoryTripStore() *memoryTripStore {
	return &memoryTripStore{
		plans: map[string]model.Plan{}, revisions: map[string]map[int64]revisionmodel.Revision{}, receipts: map[string]ports.CommandReceipt{},
	}
}

func (store *memoryTripStore) GetPlan(_ context.Context, tripID string) (model.Plan, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	plan, found := store.plans[tripID]
	if !found {
		return model.Plan{}, ports.ErrNotFound
	}
	return plan, nil
}

func (store *memoryTripStore) ListPlans(_ context.Context, query ports.ListQuery) (ports.PlanPage, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if query.Cursor != "" {
		return ports.PlanPage{}, model.ErrInvalidInput
	}
	plans := make([]model.Plan, 0, len(store.plans))
	for _, plan := range store.plans {
		if plan.OrganizerPersonaID != query.OrganizerPersonaID ||
			(query.Status != "" && plan.Status != query.Status) {
			continue
		}
		plans = append(plans, plan)
	}
	sort.Slice(plans, func(i, j int) bool {
		if plans[i].UpdatedAt.Equal(plans[j].UpdatedAt) {
			return plans[i].TripID > plans[j].TripID
		}
		return plans[i].UpdatedAt.After(plans[j].UpdatedAt)
	})
	if len(plans) > query.Limit {
		plans = plans[:query.Limit]
	}
	return ports.PlanPage{Plans: plans}, nil
}

func (store *memoryTripStore) Get(_ context.Context, tripID string, number int64) (revisionmodel.Revision, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	revision, found := store.revisions[tripID][number]
	if !found {
		return revisionmodel.Revision{}, revisionports.ErrNotFound
	}
	return revision, nil
}

func (store *memoryTripStore) AppendInTripPlanTransaction(
	_ context.Context,
	revision revisionmodel.Revision,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if _, found := store.revisions[revision.TripID]; !found {
		store.revisions[revision.TripID] = map[int64]revisionmodel.Revision{}
	}
	if _, found := store.revisions[revision.TripID][revision.RevisionNumber]; found {
		return revisionports.ErrConflict
	}
	store.revisions[revision.TripID][revision.RevisionNumber] = revision
	return nil
}

func (store *memoryTripStore) FindReceipt(_ context.Context, key string) (ports.CommandReceipt, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	receipt, found := store.receipts[key]
	return receipt, found, nil
}

func (store *memoryTripStore) Commit(_ context.Context, commit ports.Commit) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if receipt, found := store.receipts[commit.Receipt.IdempotencyKey]; found {
		if receipt.CommandDigest != commit.Receipt.CommandDigest {
			return ports.ErrIdempotencyConflict
		}
		return ports.ErrCommitConflict
	}
	current, found := store.plans[commit.Plan.TripID]
	if commit.ExpectedPlanVersion == 0 {
		if found {
			return ports.ErrCommitConflict
		}
	} else if !found || current.Version != commit.ExpectedPlanVersion ||
		current.CurrentRevisionNumber != commit.ExpectedRevisionNumber {
		return ports.ErrCommitConflict
	}
	if _, found := store.revisions[commit.Plan.TripID]; !found {
		store.revisions[commit.Plan.TripID] = map[int64]revisionmodel.Revision{}
	}
	if _, duplicate := store.revisions[commit.Plan.TripID][commit.Revision.RevisionNumber]; duplicate {
		return ports.ErrCommitConflict
	}
	store.plans[commit.Plan.TripID] = commit.Plan
	store.revisions[commit.Plan.TripID][commit.Revision.RevisionNumber] = commit.Revision
	store.receipts[commit.Receipt.IdempotencyKey] = commit.Receipt
	store.events = append(store.events, commit.Event)
	store.revisionEvents = append(store.revisionEvents, commit.RevisionEvent)
	return nil
}

func assertAtomicCounts(t *testing.T, store *memoryTripStore, plans, revisions, receipts, events int) {
	t.Helper()
	store.mu.Lock()
	defer store.mu.Unlock()
	revisionCount := 0
	for _, values := range store.revisions {
		revisionCount += len(values)
	}
	if len(store.plans) != plans || revisionCount != revisions || len(store.receipts) != receipts || len(store.events) != events {
		t.Fatalf("counts plans=%d revisions=%d receipts=%d events=%d", len(store.plans), revisionCount, len(store.receipts), len(store.events))
	}
	if len(store.revisionEvents) != revisions {
		t.Fatalf("revision events=%d revisions=%d", len(store.revisionEvents), revisions)
	}
	for _, event := range store.revisionEvents {
		if event.EventType != "TripPlanRevisionAppended" || event.AggregateID == "" || event.AggregateVersion <= 0 {
			t.Fatalf("invalid revision event: %+v", event)
		}
	}
}
