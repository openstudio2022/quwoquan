package experiment

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/experiment/domain/model"
	"quwoquan_service/services/product-ops-service/internal/product_ops/experiment/domain/ports"
	assignmentapplication "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/application"
)

type Facade struct {
	store           ports.AggregateStore
	catalog         ports.CatalogReader
	assignments     ports.AssignmentSink
	reader          ports.AssignmentReader
	assignmentFacts *assignmentapplication.Facade
	now             func() time.Time
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
	assignmentFacts, err := assignmentapplication.NewFacade(store, assignments, reader)
	if err != nil {
		return nil, err
	}
	return &Facade{store: store, catalog: catalog, assignments: assignments, reader: reader, assignmentFacts: assignmentFacts, now: time.Now}, nil
}

func (f *Facade) AssignmentFacts() *assignmentapplication.Facade { return f.assignmentFacts }

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
	return f.assignmentFacts.Assign(ctx, experimentID, subjectKey)
}

func (f *Facade) GetAssignment(ctx context.Context, experimentID, subjectKey string) (model.AssignmentFact, error) {
	return f.assignmentFacts.Get(ctx, experimentID, subjectKey)
}

func (f *Facade) Stats(ctx context.Context, experimentID string) (model.Experiment, ports.AssignmentStats, error) {
	return f.assignmentFacts.Stats(ctx, experimentID)
}

// StatsFor 按目录已加载的实验（含当前 policyVersion）读取分配统计，
// 供列表页避免逐实验重复 Load 聚合（listExperiments N+1 收敛）。
func (f *Facade) StatsFor(
	ctx context.Context,
	experiment model.Experiment,
) (ports.AssignmentStats, error) {
	return f.assignmentFacts.StatsFor(ctx, experiment)
}
