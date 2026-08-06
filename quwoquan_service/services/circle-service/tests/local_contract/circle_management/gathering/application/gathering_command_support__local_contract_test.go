package application_test

import (
	"context"
	"sync"
	"testing"

	"quwoquan_service/runtime/operation"
	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
)

type receiptRecord struct {
	digest    string
	gathering model.Gathering
}

type memoryStore struct {
	mu       sync.Mutex
	value    *model.Gathering
	receipts map[string]receiptRecord
}

func newMemoryStore() *memoryStore {
	return &memoryStore{receipts: map[string]receiptRecord{}}
}

func (store *memoryStore) Load(
	_ context.Context,
	gatheringID string,
) (model.Gathering, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.value == nil || store.value.ID != gatheringID {
		return model.Gathering{}, false, nil
	}
	return cloneGathering(*store.value), true, nil
}

func (store *memoryStore) Commit(
	_ context.Context,
	request ports.CommitRequest,
) (ports.CommitReceipt, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if receipt, ok := store.receipts[request.ReceiptKey]; ok {
		if receipt.digest != request.CommandDigest {
			return ports.CommitReceipt{}, gatheringerrors.ErrGatheringIdempotencyConflict
		}
		return ports.CommitReceipt{
			Gathering: cloneGathering(receipt.gathering),
			Replayed:  true,
		}, nil
	}
	var current *model.Gathering
	if store.value != nil {
		copy := cloneGathering(*store.value)
		current = &copy
	}
	next, err := request.Mutate(current)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	copy := cloneGathering(next)
	store.value = &copy
	store.receipts[request.ReceiptKey] = receiptRecord{
		digest:    request.CommandDigest,
		gathering: cloneGathering(next),
	}
	return ports.CommitReceipt{Gathering: cloneGathering(next)}, nil
}

func (store *memoryStore) mustLoad(t *testing.T) model.Gathering {
	t.Helper()
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.value == nil {
		t.Fatal("Gathering is missing")
	}
	return cloneGathering(*store.value)
}

func commandContext(personaID, key string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		OperationID:    "circle.gathering.command",
		RequestID:      "request-" + key,
		TraceID:        "trace-" + key,
		IdempotencyKey: key,
		Actor:          operation.ActorContext{PersonaID: personaID},
	})
}

func cloneGathering(value model.Gathering) model.Gathering {
	value.OrganizerAssignments = append(
		[]contract.OrganizerAssignment(nil),
		value.OrganizerAssignments...,
	)
	value.Participations = append(
		[]model.GatheringParticipation(nil),
		value.Participations...,
	)
	for index := range value.Participations {
		value.Participations[index].ApplicationAnswers = append(
			[]model.GatheringApplicationAnswer(nil),
			value.Participations[index].ApplicationAnswers...,
		)
	}
	value.Revisions = append([]contract.GatheringRevision(nil), value.Revisions...)
	value.AvailabilityWatches = append(
		[]contract.GatheringAvailabilityWatch(nil),
		value.AvailabilityWatches...,
	)
	return value
}

var _ ports.AggregateStore = (*memoryStore)(nil)
