// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-plan-collaboration/spec.md#gwt-002
package gathering_plan_test

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"quwoquan_service/runtime/operation"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/ports"
)

func TestMemoryPlanStoreRejectsConflictingReceiptDigest(t *testing.T) {
	store := newMemoryPlanStore()
	store.receipts["receipt-1"] = memoryReceipt{digest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
	_, err := store.Commit(context.Background(), ports.CommitRequest{
		ReceiptKey:    "receipt-1",
		CommandDigest: "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		Authorize: func(context.Context) error {
			return nil
		},
	})
	if !errors.Is(err, model.ErrIdempotencyConflict) {
		t.Fatalf("conflicting receipt digest err=%v", err)
	}
}

type memoryReceipt struct {
	digest string
	result model.CommandResult
}

type memoryPlanStore struct {
	mu       sync.Mutex
	plans    map[string]model.GatheringPlan
	receipts map[string]memoryReceipt
	eventLog []ports.EventLogRecord
}

func newMemoryPlanStore() *memoryPlanStore {
	return &memoryPlanStore{plans: map[string]model.GatheringPlan{}, receipts: map[string]memoryReceipt{}}
}

func (store *memoryPlanStore) Load(_ context.Context, planID string) (model.GatheringPlan, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	value, found := store.plans[planID]
	return value, found, nil
}

func (store *memoryPlanStore) Commit(ctx context.Context, request ports.CommitRequest) (ports.CommitReceipt, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if err := request.Authorize(ctx); err != nil {
		return ports.CommitReceipt{}, err
	}
	if receipt, found := store.receipts[request.ReceiptKey]; found {
		if receipt.digest != request.CommandDigest {
			return ports.CommitReceipt{}, model.ErrIdempotencyConflict
		}
		result := receipt.result
		result.Replayed = true
		return ports.CommitReceipt{Result: result, Replayed: true}, nil
	}
	current, found := store.plans[request.PlanID]
	var currentPointer *model.GatheringPlan
	if found {
		copy := current
		currentPointer = &copy
	}
	next, event, err := request.Mutate(currentPointer)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if (!found && next.Version != 1) || (found && next.Version != current.Version+1) {
		return ports.CommitReceipt{}, model.ErrVersionConflict
	}
	store.plans[next.ID] = next
	var proposal *model.Proposal
	if event.ProposalID != "" {
		proposal = &model.Proposal{ProposalID: event.ProposalID, ProposalDigest: event.ProposalDigest}
	}
	result := model.CommandResultFromPlan(next, proposal, false)
	store.receipts[request.ReceiptKey] = memoryReceipt{digest: request.CommandDigest, result: result}
	store.eventLog = append(store.eventLog, ports.EventLogRecord{
		EventID: request.EventType, EventType: request.EventType,
		AggregateID: next.ID, AggregateVersion: next.Version,
		OccurredAt: event.OccurredAt, Sequence: int64(len(store.eventLog) + 1),
	})
	return ports.CommitReceipt{Result: result}, nil
}

func (store *memoryPlanStore) ReadByGathering(_ context.Context, gatheringID string) (model.GatheringPlan, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	for _, plan := range store.plans {
		if plan.GatheringID == gatheringID {
			return plan, true, nil
		}
	}
	return model.GatheringPlan{}, false, nil
}

func (store *memoryPlanStore) ReadByID(ctx context.Context, planID string) (model.GatheringPlan, bool, error) {
	return store.Load(ctx, planID)
}

func (store *memoryPlanStore) ListRevisions(ctx context.Context, planID, _ string, _ int) (model.RevisionPage, error) {
	plan, found, err := store.Load(ctx, planID)
	if err != nil {
		return model.RevisionPage{}, err
	}
	if !found {
		return model.RevisionPage{}, model.ErrNotFound
	}
	return model.RevisionPage{Items: plan.Revisions}, nil
}

type authorityState struct {
	mu     sync.Mutex
	values map[string]ports.GatheringAuthority
}

func newAuthorityState() *authorityState {
	return &authorityState{values: map[string]ports.GatheringAuthority{}}
}

func (state *authorityState) set(actor string, value ports.GatheringAuthority) {
	state.mu.Lock()
	defer state.mu.Unlock()
	state.values[actor] = value
}

func (state *authorityState) ReadGatheringAuthority(_ context.Context, gatheringID, actor string) (ports.GatheringAuthority, error) {
	state.mu.Lock()
	defer state.mu.Unlock()
	value := state.values[actor]
	if value.GatheringID == "" {
		value.GatheringID = gatheringID
	}
	return value, nil
}

func commandContext(actor, key string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		OperationID: "circle.gathering_plan.test", RequestID: "request-" + key,
		TraceID: "trace-" + key, IdempotencyKey: key, SessionID: "session-" + key,
		Actor: operation.ActorContext{AccountID: "account-" + actor, PersonaID: actor},
	})
}

func queryContext(actor string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		OperationID: "circle.gathering_plan.test.query", RequestID: "request-query",
		TraceID: "trace-query", SessionID: "session-query",
		Actor: operation.ActorContext{AccountID: "account-" + actor, PersonaID: actor},
	})
}

func agendaItems(content string) []model.PlanItem {
	return []model.PlanItem{{
		ItemID: "agenda-1", Kind: model.PlanItemKindAgenda, Order: 0,
		Agenda: &model.AgendaItem{Content: content}, SourceRefs: []model.SourceRef{},
	}}
}

func noAcknowledgement() model.AcknowledgementPolicy {
	return model.AcknowledgementPolicy{Mode: model.PlanAcknowledgementModeNone}
}

func fixedTime() time.Time {
	return time.Date(2026, 8, 6, 8, 30, 0, 0, time.UTC)
}

var (
	_ ports.AggregateStore           = (*memoryPlanStore)(nil)
	_ ports.GatheringPlanReader      = (*memoryPlanStore)(nil)
	_ ports.GatheringAuthorityReader = (*authorityState)(nil)
)
