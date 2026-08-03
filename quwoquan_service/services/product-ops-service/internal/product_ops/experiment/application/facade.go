package experiment

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/experiment/domain/model"
	"quwoquan_service/services/product-ops-service/internal/product_ops/experiment/domain/ports"
	assignmentapplication "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/application"
	assignmentdomain "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/domain"
)

type Facade struct {
	store           ports.AggregateStore
	catalog         ports.CatalogReader
	assignmentFacts *assignmentapplication.Facade
	now             func() time.Time
}

func NewFacade(
	store ports.AggregateStore,
	catalog ports.CatalogReader,
	assignments assignmentapplication.Sink,
	reader assignmentapplication.Reader,
) (*Facade, error) {
	if store == nil || catalog == nil || assignments == nil || reader == nil {
		return nil, fmt.Errorf("experiment aggregate store, catalog, assignment sink and reader are required")
	}
	assignmentFacts, err := assignmentapplication.NewFacade(store, assignments, reader)
	if err != nil {
		return nil, err
	}
	return &Facade{store: store, catalog: catalog, assignmentFacts: assignmentFacts, now: time.Now}, nil
}

func (f *Facade) AssignmentFacts() *assignmentapplication.Facade { return f.assignmentFacts }

func (f *Facade) Get(ctx context.Context, id string) (model.Experiment, error) {
	return f.store.Load(ctx, id)
}

func (f *Facade) List(ctx context.Context) ([]model.Experiment, error) {
	return f.catalog.List(ctx)
}

func (f *Facade) Create(
	ctx context.Context,
	id string,
	key string,
	status string,
	variants []model.Variant,
	audienceRule model.AudienceRule,
	startsAt string,
	endsAt string,
	idempotencyKey string,
) (ports.CommitReceipt, error) {
	id = strings.TrimSpace(id)
	key = strings.TrimSpace(key)
	status = strings.TrimSpace(status)
	startsAt = strings.TrimSpace(startsAt)
	endsAt = strings.TrimSpace(endsAt)
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	audienceRule.Kind = strings.TrimSpace(audienceRule.Kind)
	if id == "" || key == "" || idempotencyKey == "" {
		return ports.CommitReceipt{}, fmt.Errorf("%w: id, key and Idempotency-Key are required", model.ErrInvalidArgument)
	}
	commandPayload, err := json.Marshal(struct {
		ID           string             `json:"id"`
		Key          string             `json:"key"`
		Status       string             `json:"status"`
		Variants     []model.Variant    `json:"variants"`
		AudienceRule model.AudienceRule `json:"audienceRule"`
		StartsAt     string             `json:"startsAt,omitempty"`
		EndsAt       string             `json:"endsAt,omitempty"`
	}{id, key, status, variants, audienceRule, startsAt, endsAt})
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	commandDigest := fmt.Sprintf("%x", sha256.Sum256(commandPayload))
	if receipt, found, err := f.store.Replay(ctx, id, idempotencyKey, commandDigest); err != nil {
		return ports.CommitReceipt{}, err
	} else if found {
		return receipt, nil
	}
	now := f.now().UTC()
	experiment := model.Experiment{
		ID: id, Key: key, Version: 1, Status: status,
		Variants:     append([]model.Variant(nil), variants...),
		AudienceRule: audienceRule, StartsAt: startsAt, EndsAt: endsAt,
		CreatedAt: now.Format(time.RFC3339), UpdatedAt: now.Format(time.RFC3339),
	}
	if err := experiment.Validate(); err != nil {
		return ports.CommitReceipt{}, fmt.Errorf("%w: %v", model.ErrInvalidArgument, err)
	}
	event, err := newPolicyActivationEvent(experiment, idempotencyKey, now)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	return f.store.Commit(ctx, 0, ports.ChangeSet{
		Experiment: experiment, IdempotencyKey: idempotencyKey,
		CommandDigest: commandDigest, Events: []model.Event{event},
	})
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
		return ports.CommitReceipt{}, fmt.Errorf("%w: %v", model.ErrInvalidArgument, err)
	}
	event, err := newPolicyActivationEvent(next, idempotencyKey, now)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	return f.store.Commit(ctx, expectedVersion, ports.ChangeSet{
		Experiment: next, IdempotencyKey: idempotencyKey,
		CommandDigest: commandDigest, Events: []model.Event{event},
	})
}

func newPolicyActivationEvent(
	experiment model.Experiment,
	idempotencyKey string,
	now time.Time,
) (model.Event, error) {
	payload, err := json.Marshal(struct {
		ID           string             `json:"id"`
		Key          string             `json:"key"`
		Version      int64              `json:"version"`
		Status       string             `json:"status"`
		Variants     []model.Variant    `json:"variants"`
		AudienceRule model.AudienceRule `json:"audienceRule"`
		StartsAt     string             `json:"startsAt,omitempty"`
		EndsAt       string             `json:"endsAt,omitempty"`
		UpdatedAt    string             `json:"updatedAt"`
	}{
		ID: experiment.ID, Key: experiment.Key, Version: experiment.Version,
		Status: experiment.Status, Variants: experiment.Variants,
		AudienceRule: experiment.AudienceRule, StartsAt: experiment.StartsAt,
		EndsAt: experiment.EndsAt, UpdatedAt: experiment.UpdatedAt,
	})
	if err != nil {
		return model.Event{}, err
	}
	eventDigest := sha256.Sum256([]byte(experiment.ID + "\x00" + idempotencyKey))
	return model.Event{
		ID:   "experiment-policy-" + fmt.Sprintf("%x", eventDigest[:16]),
		Type: "ExperimentPolicyActivated", AggregateID: experiment.ID,
		AggregateType: "Experiment", Payload: payload, OccurredAt: now,
	}, nil
}

func (f *Facade) GetAssignment(ctx context.Context, experimentID, subjectKey string) (assignmentdomain.Fact, error) {
	return f.assignmentFacts.Get(ctx, experimentID, subjectKey)
}

func (f *Facade) Stats(ctx context.Context, experimentID string) (model.Experiment, assignmentdomain.Stats, error) {
	return f.assignmentFacts.Stats(ctx, experimentID)
}

// StatsFor 按目录已加载的实验（含当前 experimentRevision）读取分配统计，
// 供列表页避免逐实验重复 Load 聚合（listExperiments N+1 收敛）。
func (f *Facade) StatsFor(
	ctx context.Context,
	experiment model.Experiment,
) (assignmentdomain.Stats, error) {
	return f.assignmentFacts.StatsFor(ctx, experiment)
}
