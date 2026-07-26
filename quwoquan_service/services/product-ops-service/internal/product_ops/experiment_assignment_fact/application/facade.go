package application

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/experiment/domain/model"
	"quwoquan_service/services/product-ops-service/internal/product_ops/experiment/domain/ports"
)

// Facade owns assignment-fact append and read use cases. Experiment is consulted
// only to resolve the current policy version and deterministic variant.
type Facade struct {
	experiments ports.AggregateStore
	sink        ports.AssignmentSink
	reader      ports.AssignmentReader
	now         func() time.Time
}

func NewFacade(experiments ports.AggregateStore, sink ports.AssignmentSink, reader ports.AssignmentReader) (*Facade, error) {
	if experiments == nil || sink == nil || reader == nil {
		return nil, fmt.Errorf("experiment store, assignment sink and reader are required")
	}
	return &Facade{experiments: experiments, sink: sink, reader: reader, now: time.Now}, nil
}

func (f *Facade) Assign(ctx context.Context, experimentID, subjectKey string) (model.AssignmentFact, bool, error) {
	experiment, err := f.experiments.Load(ctx, experimentID)
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
	return f.sink.Append(ctx, fact, model.Event{
		ID: fact.ID, Type: "ExperimentAssigned", AggregateID: fact.ID,
		AggregateType: "ExperimentAssignmentFact", Payload: payload,
		OccurredAt: f.now().UTC(),
	})
}

func (f *Facade) Get(ctx context.Context, experimentID, subjectKey string) (model.AssignmentFact, error) {
	experiment, err := f.experiments.Load(ctx, experimentID)
	if err != nil {
		return model.AssignmentFact{}, err
	}
	return f.reader.Get(ctx, experimentID, fmt.Sprintf("%d", experiment.Version), subjectKey)
}

func (f *Facade) Stats(ctx context.Context, experimentID string) (model.Experiment, ports.AssignmentStats, error) {
	experiment, err := f.experiments.Load(ctx, experimentID)
	if err != nil {
		return model.Experiment{}, ports.AssignmentStats{}, err
	}
	stats, err := f.reader.Stats(ctx, experimentID, fmt.Sprintf("%d", experiment.Version))
	return experiment, stats, err
}

func (f *Facade) StatsFor(ctx context.Context, experiment model.Experiment) (ports.AssignmentStats, error) {
	return f.reader.Stats(ctx, experiment.ID, fmt.Sprintf("%d", experiment.Version))
}
