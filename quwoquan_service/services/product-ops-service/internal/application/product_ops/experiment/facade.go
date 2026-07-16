package experiment

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"time"

	"quwoquan_service/services/product-ops-service/internal/domain/product_ops/experiment/model"
	"quwoquan_service/services/product-ops-service/internal/domain/product_ops/experiment/ports"
)

type Facade struct {
	store       ports.AggregateStore
	catalog     ports.CatalogReader
	assignments ports.AssignmentSink
	reader      ports.AssignmentReader
	now         func() time.Time
}

func NewFacade(
	store ports.AggregateStore,
	catalog ports.CatalogReader,
	assignments ports.AssignmentSink,
	reader ports.AssignmentReader,
) (*Facade, error) {
	if store == nil || catalog == nil || assignments == nil || reader == nil {
		return nil, fmt.Errorf("experiment aggregate store, catalog, assignment sink and reader are required")
	}
	return &Facade{store: store, catalog: catalog, assignments: assignments, reader: reader, now: time.Now}, nil
}

func (f *Facade) Get(ctx context.Context, id string) (model.Experiment, error) {
	return f.store.Load(ctx, id)
}

func (f *Facade) List(ctx context.Context) ([]model.Experiment, error) {
	return f.catalog.List(ctx)
}

func (f *Facade) UpdateRollout(
	ctx context.Context,
	id string,
	expectedVersion int64,
	status string,
	variants []model.Variant,
	idempotencyKey string,
) (ports.CommitReceipt, error) {
	commandPayload, err := json.Marshal(struct {
		ExperimentID    string          `json:"experimentId"`
		ExpectedVersion int64           `json:"expectedVersion"`
		Status          string          `json:"status"`
		Variants        []model.Variant `json:"variants"`
	}{id, expectedVersion, status, variants})
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	commandDigest := fmt.Sprintf("%x", sha256.Sum256(commandPayload))
	if receipt, found, err := f.store.Replay(ctx, id, idempotencyKey, commandDigest); err != nil {
		return ports.CommitReceipt{}, err
	} else if found {
		return receipt, nil
	}
	current, err := f.store.Load(ctx, id)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	now := f.now().UTC()
	next, err := current.UpdateRollout(status, variants, now)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	payload, err := json.Marshal(struct {
		ID        string          `json:"id"`
		Key       string          `json:"key"`
		Version   int64           `json:"version"`
		Status    string          `json:"status"`
		Variants  []model.Variant `json:"variants"`
		StartsAt  string          `json:"startsAt,omitempty"`
		EndsAt    string          `json:"endsAt,omitempty"`
		UpdatedAt string          `json:"updatedAt"`
	}{
		ID: next.ID, Key: next.Key, Version: next.Version, Status: next.Status,
		Variants: next.Variants, StartsAt: next.StartsAt, EndsAt: next.EndsAt,
		UpdatedAt: next.UpdatedAt,
	})
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	eventDigest := sha256.Sum256([]byte(id + "\x00" + idempotencyKey))
	return f.store.Commit(ctx, expectedVersion, ports.ChangeSet{
		Experiment:     next,
		IdempotencyKey: idempotencyKey,
		CommandDigest:  commandDigest,
		Events: []model.Event{{
			ID: "experiment-rollout-" + fmt.Sprintf("%x", eventDigest[:16]), Type: "ExperimentRolloutUpdated",
			AggregateID: id, AggregateType: "Experiment", Payload: payload, OccurredAt: now,
		}},
	})
}

func (f *Facade) Assign(ctx context.Context, experimentID, subjectKey string) (model.AssignmentFact, bool, error) {
	experiment, err := f.store.Load(ctx, experimentID)
	if err != nil {
		return model.AssignmentFact{}, false, err
	}
	fact, err := experiment.Assign(subjectKey, f.now())
	if err != nil {
		return model.AssignmentFact{}, false, err
	}
	payload, err := json.Marshal(fact)
	if err != nil {
		return model.AssignmentFact{}, false, err
	}
	return f.assignments.Append(ctx, fact, model.Event{
		ID: fact.ID, Type: "ExperimentAssigned", AggregateID: fact.ID,
		AggregateType: "ExperimentAssignmentFact", Payload: payload,
		OccurredAt: f.now().UTC(),
	})
}

func (f *Facade) GetAssignment(ctx context.Context, experimentID, subjectKey string) (model.AssignmentFact, error) {
	experiment, err := f.store.Load(ctx, experimentID)
	if err != nil {
		return model.AssignmentFact{}, err
	}
	return f.reader.Get(ctx, experimentID, fmt.Sprintf("%d", experiment.Version), subjectKey)
}

func (f *Facade) Stats(ctx context.Context, experimentID string) (model.Experiment, ports.AssignmentStats, error) {
	experiment, err := f.store.Load(ctx, experimentID)
	if err != nil {
		return model.Experiment{}, ports.AssignmentStats{}, err
	}
	stats, err := f.reader.Stats(ctx, experimentID, fmt.Sprintf("%d", experiment.Version))
	return experiment, stats, err
}
